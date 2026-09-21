# -*- coding: utf-8 -*-
"""Acesso à API do ServiceDesk Plus Cloud (SDP) v3, com OAuth Zoho.

Os segredos vêm de kbr_secrets (arquivo ~/.kbr/secrets.env ou 1Password) e NUNCA
são impressos. Toda saída é JSON em UTF-8, sem credenciais e sem cabeçalhos HTTP.
Nenhuma operação de escrita acontece sem a flag --confirmar.
"""
from __future__ import annotations

import argparse
import csv
import html as _html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kbr_secrets  # noqa: E402

CHAVE_CONFIG = "servicedesk"
ACEITA = "application/vnd.manageengine.sdp.v3+json"
MARGEM_RENOVACAO = 300  # segundos antes do vencimento em que já renovamos

PADRAO_CONFIG = {
    "tecnico_nome": "",
    "tecnico_email": "",
    "data_center": "us",
    "api_base": "https://sdpondemand.manageengine.com/api/v3",
    "token_url": "https://accounts.zoho.com/oauth/v2/token",
}

STATUS_DE_ESPERA = {"on hold", "aguardando aprovacao", "aguardando aprovação", "em observacao",
                    "em observação"}

ESCOPOS = ["SDPOnDemand.requests.READ", "SDPOnDemand.requests.CREATE",
           "SDPOnDemand.requests.UPDATE"]


class ErroSDP(Exception):
    """A mensagem já é o texto em PT-BR pronto para o usuário."""


# --------------------------------------------------------------------------- config

def _ler_json_do_arquivo(caminho: Path) -> dict:
    """Lê e decodifica o JSON de `caminho`; ausente ou corrompido vira dict vazio."""
    if not caminho.exists():
        return {}
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def ler_config() -> dict:
    caminho = kbr_secrets.caminho_config()
    dados = _ler_json_do_arquivo(caminho)
    config = dict(PADRAO_CONFIG)
    config.update(dados.get(CHAVE_CONFIG) or {})
    return config


def gravar_config(novos: dict) -> None:
    caminho = kbr_secrets.caminho_config()
    dados = _ler_json_do_arquivo(caminho)
    atual = dict(PADRAO_CONFIG)
    atual.update(dados.get(CHAVE_CONFIG) or {})
    atual.update(novos)
    dados[CHAVE_CONFIG] = atual
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")


# --------------------------------------------------------------------------- erros

_ZOHO = {
    "invalid_code": ("O código de autorização expirou ou já foi usado. Ele vale 10 minutos. "
                     "Gere outro no console (passo 013 do wizard) e cole de novo."),
    "invalid_client": ("Client ID ou Client Secret incorretos. Confira se copiou os dois "
                       "inteiros, sem espaços (passo 010 do wizard). Se o cliente foi criado "
                       "no console de outro país, refaça no americano: api-console.zoho.com."),
    "invalid_scope": ("O cliente não tem os escopos necessários. Gere um novo código com a "
                      "lista completa de escopos (passos 012 e 013 do wizard)."),
    "invalid_grant": ("O acesso foi revogado no 1Password ou na Zoho. Refaça os passos 013 a "
                      "016 do wizard para gerar um novo acesso."),
}

_HTTP = {
    401: ("O acesso foi revogado ou o token venceu. Refaça os passos 013 a 016 do wizard "
          "(/kbr-servicedesk:configurar)."),
    403: ("O cliente não tem permissão para esta operação. Gere um novo código com a lista "
          "completa de escopos (passos 012 e 013 do wizard)."),
    404: "O ServiceDesk não encontrou esse chamado. Confira o número.",
    429: "O ServiceDesk recusou por excesso de chamadas. Espere um minuto e tente de novo.",
}


def _mensagens_do_sdp(corpo: dict) -> str:
    """Extrai as mensagens de erro do corpo de resposta do SDP.

    O corpo vem de um `json.loads` sobre a resposta HTTP — o formato de
    `response_status` e `messages` não é garantido, então cada nível é
    validado antes de ser indexado; qualquer formato fora do esperado
    simplesmente não contribui com detalhe nenhum, em vez de quebrar.
    """
    response_status = corpo.get("response_status")
    if not isinstance(response_status, dict):
        return ""
    mensagens = response_status.get("messages")
    if not isinstance(mensagens, list):
        return ""
    textos = [str(item.get("message")) for item in mensagens
             if isinstance(item, dict) and item.get("message")]
    return " ".join(textos)


def traduzir(origem: str, corpo: dict, http: int = 0) -> str:
    """Transforma um erro da Zoho ou do SDP em texto acionável em PT-BR."""
    corpo = corpo if isinstance(corpo, dict) else {}
    if origem == "rede":
        return ("Não consegui falar com o ServiceDesk. Confira a conexão e a VPN, se você "
                "usa, e tente de novo.")
    if origem == "resposta_nao_json":
        return ("A resposta não veio em JSON — não parece ter sido o ServiceDesk quem "
                "respondeu. Isso costuma acontecer quando um proxy ou portal cativo intercepta "
                "a conexão. Confira a conexão e a VPN, se você usa, e tente de novo.")
    if origem == "zoho":
        erro_bruto = corpo.get("error")
        codigo = erro_bruto.strip() if isinstance(erro_bruto, str) else ""
        if codigo in _ZOHO:
            return _ZOHO[codigo]
        if codigo:
            return (f"A Zoho recusou a autenticação ({codigo}). Refaça os passos 009 a 016 do "
                    f"wizard (/kbr-servicedesk:configurar).")
        return ("A Zoho não devolveu um token de acesso. Refaça os passos 013 a 016 do wizard "
                "(/kbr-servicedesk:configurar).")
    if http in _HTTP:
        return _HTTP[http]
    detalhe = _mensagens_do_sdp(corpo)
    if detalhe:
        return f"O ServiceDesk recusou a operação (HTTP {http}): {detalhe}"
    return (f"O ServiceDesk respondeu HTTP {http} e não explicou o motivo. Tente de novo; "
            f"se persistir, abra o chamado pelo portal.")


# --------------------------------------------------------------------------- rede

def _abrir(requisicao, timeout=90):
    """Ponto único de rede — os testes substituem esta função."""
    return urllib.request.urlopen(requisicao, timeout=timeout)


def _postar_form(url: str, campos: dict) -> tuple[int, dict]:
    dados = urllib.parse.urlencode(campos).encode("utf-8")
    requisicao = urllib.request.Request(url, data=dados, method="POST")
    try:
        with _abrir(requisicao, timeout=60) as resposta:
            status = getattr(resposta, "status", 200)
            corpo_bruto = resposta.read()
    except urllib.error.HTTPError as erro:
        try:
            return erro.code, json.loads(erro.read())
        except (json.JSONDecodeError, ValueError):
            return erro.code, {}
    except urllib.error.URLError:
        raise ErroSDP(traduzir("rede", {})) from None
    # Resposta 200, mas o corpo não é JSON: proxy ou portal cativo respondeu no lugar do
    # ServiceDesk. Vira ErroSDP em vez de deixar o JSONDecodeError escapar cru.
    try:
        return status, json.loads(corpo_bruto)
    except json.JSONDecodeError:
        raise ErroSDP(traduzir("resposta_nao_json", {})) from None


def _caminho_cache_token() -> Path:
    return kbr_secrets.caminho_cache() / "sdp_access_token.json"


def _token_em_cache() -> str | None:
    """Lê o token cacheado. Qualquer cache que não dá para entender — arquivo ausente,
    JSON corrompido, JSON que não é objeto ou `expira_em` que não é número — vale como
    cache ausente: devolve None em vez de levantar, e quem chama busca um token novo."""
    caminho = _caminho_cache_token()
    if not caminho.exists():
        return None
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(dados, dict):
        return None
    try:
        expira_em = float(dados.get("expira_em", 0))
    except (TypeError, ValueError):
        return None
    if expira_em - time.time() < MARGEM_RENOVACAO:
        return None
    return dados.get("access_token") or None


def _guardar_token(token: str, expira_em_segundos: int) -> None:
    caminho = _caminho_cache_token()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps({
        "access_token": token,
        "expira_em": time.time() + max(int(expira_em_segundos or 3600), 60),
    }), encoding="utf-8")


def _segredo(nome: str) -> str:
    try:
        return kbr_secrets.obter(nome)
    except kbr_secrets.ErroSegredo as erro:
        raise ErroSDP(str(erro)) from None


def access_token(forcar: bool = False) -> str:
    if not forcar:
        guardado = _token_em_cache()
        if guardado:
            return guardado
    config = ler_config()
    status, corpo = _postar_form(config["token_url"], {
        "grant_type": "refresh_token",
        "client_id": _segredo("SDP_CLIENT_ID"),
        "client_secret": _segredo("SDP_CLIENT_SECRET"),
        "refresh_token": _segredo("SDP_REFRESH_TOKEN"),
    })
    token = (corpo or {}).get("access_token")
    if status >= 300 or not token:
        raise ErroSDP(traduzir("zoho", corpo or {}))
    _guardar_token(token, (corpo or {}).get("expires_in", 3600))
    return token


def chamar(metodo: str, caminho: str, input_data: dict | None, token: str) -> tuple[int, dict]:
    config = ler_config()
    url = config["api_base"] + caminho
    dados = None
    if metodo == "GET":
        if input_data:
            url += "?" + urllib.parse.urlencode(
                {"input_data": json.dumps(input_data, ensure_ascii=False)})
    else:
        dados = urllib.parse.urlencode(
            {"input_data": json.dumps(input_data or {}, ensure_ascii=False)}).encode("utf-8")
    requisicao = urllib.request.Request(url, data=dados, method=metodo)
    requisicao.add_header("Authorization", f"Zoho-oauthtoken {token}")
    requisicao.add_header("Accept", ACEITA)
    try:
        with _abrir(requisicao) as resposta:
            status = getattr(resposta, "status", 200)
            corpo_bruto = resposta.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as erro:
        try:
            return erro.code, json.loads(erro.read().decode("utf-8", "replace"))
        except (json.JSONDecodeError, ValueError):
            return erro.code, {}
    except urllib.error.URLError:
        raise ErroSDP(traduzir("rede", {})) from None
    # Resposta 200, mas o corpo não é JSON: proxy ou portal cativo respondeu no lugar do
    # ServiceDesk. Vira ErroSDP em vez de deixar o JSONDecodeError escapar cru.
    try:
        return status, json.loads(corpo_bruto)
    except json.JSONDecodeError:
        raise ErroSDP(traduzir("resposta_nao_json", {})) from None


# --------------------------------------------------------------------------- ajudantes

STATUS_FINAIS = ["Resolved", "Closed", "Canceled"]
# ^ "Canceled" (L simples, grafia americana), não "Cancelled" (L duplo, britânica).
# Verificado ao vivo em 2026-09-14: com "Cancelled" o filtro "is not" não dava erro,
# mas também não excluía nada — o ServiceDesk da KINTO usa a grafia americana (coerente
# com o data center US da Zoho), então nenhum chamado tinha esse status exato e o filtro
# vazava 335 chamados cancelados como se fossem "abertos" (total_count 517 vs 182 reais).
# Se um dia o SDP usar as duas grafias ao mesmo tempo, listar as duas aqui.

FUSO_BRASILIA = timezone(timedelta(hours=-3), name="UTC-03:00")
# UTC-3 fixo: o Brasil não usa mais horário de verão desde 2019, então não há transição
# sazonal para tratar. Deliberadamente NÃO usamos zoneinfo.ZoneInfo aqui — no Windows, sem
# o banco de dados IANA instalado pelo SO, isso exigiria "pip install tzdata", violando a
# regra do repositório de que nenhum plugin pode depender de instalação externa.


def _data_para_ms(data_iso: str) -> str:
    """Converte "AAAA-MM-DD" em milissegundos desde a época Unix, meia-noite em horário de
    Brasília (UTC-3 fixo, ver FUSO_BRASILIA).

    A forma do valor (ms desde a época, como string) é a mesma verificada ao vivo contra o
    SDP real da KINTO (spec de 2026-09-14, seção 2.2) — o servidor só compara os números que
    mandamos, então um deslocamento fixo de fuso não muda o mecanismo já validado, só o valor.
    A fronteira em horário de Brasília (em vez de UTC) é o que faz "setembro" no arquivo bater
    com "setembro" no calendário de quem pediu.
    """
    momento = datetime.strptime(data_iso, "%Y-%m-%d").replace(tzinfo=FUSO_BRASILIA)
    return str(int(momento.timestamp() * 1000))


def _exigir_data(rotulo: str, valor: str) -> str:
    try:
        return _data_para_ms(valor)
    except ValueError:
        raise ErroSDP(f'A data de "{rotulo}" precisa estar no formato AAAA-MM-DD '
                      f'(exemplo: 2026-09-01). Veio "{valor}".') from None


def limpo(bruto: str, limite: int = 3000) -> str:
    """HTML do SDP para texto legível."""
    if not bruto:
        return "(vazio)"
    texto = re.sub(r"<br\s*/?>", "\n", str(bruto))
    texto = re.sub(r"</(p|div|tr|li|h\d)>", "\n", texto)
    texto = re.sub(r"<[^>]+>", "", texto)
    texto = _html.unescape(texto)
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto).strip()
    return texto[:limite] + ("..." if len(texto) > limite else "")


def campo(origem: dict, *chaves: str):
    atual = origem
    for chave in chaves:
        if not isinstance(atual, dict):
            return None
        atual = atual.get(chave)
    return atual


def _extrair(corpo, chave: str, tipo: type):
    """Extrai `chave` de `corpo`, garantindo que veio no tipo esperado (`list` ou `dict`).

    `corpo` é o dicionário decodificado de uma resposta do SDP — o formato não é garantido
    pela API. Ausente ou falsy vira o vazio do tipo pedido (`[]`/`{}`), igual ao antigo
    `or []`/`or {}`: uma lista de chamados vazia continua parecendo lista vazia. A diferença é
    o caso que faltava — um valor presente e do tipo errado (um dict onde se esperava lista,
    uma string, um número) não passa mais direto para ser indexado ou iterado. Sem essa
    checagem esse valor de tipo errado também seria confundido com "não há chamados": o
    técnico acharia que a lista está vazia quando na verdade a resposta veio malformada. Aqui
    vira `ErroSDP` com mensagem em português, em vez de `TypeError`/`AttributeError` cru mais
    adiante.
    """
    corpo = corpo if isinstance(corpo, dict) else {}
    valor = corpo.get(chave)
    if not valor:
        return tipo()
    if not isinstance(valor, tipo):
        nome_tipo = "uma lista" if tipo is list else "um objeto"
        raise ErroSDP(
            f'O ServiceDesk devolveu "{chave}" num formato que eu não entendo (esperava '
            f'{nome_tipo}). Tente de novo; se persistir, abra o chamado pelo portal.')
    return valor


def _resultado(status: int, corpo, chave: str, tipo: type):
    """Confere o status HTTP e, se for sucesso, extrai `chave` de `corpo` com `_extrair`.

    As três chamadas que buscam chamados (`achar_id`, `_buscar_chamados`, o detalhe em
    `cmd_detalhe`) sempre fazem as duas coisas em sequência — por isso ficaram juntas aqui em
    vez de repetir o par status+forma três vezes. A busca de notas em `cmd_detalhe` é
    deliberadamente diferente (não levanta em HTTP de erro — ver comentário lá) e por isso usa
    `_extrair` sozinho, sem passar por aqui.
    """
    if status >= 300:
        raise ErroSDP(traduzir("sdp", corpo, http=status))
    return _extrair(corpo, chave, tipo)


def _exigir_tecnico() -> str:
    nome = (ler_config().get("tecnico_nome") or "").strip()
    if not nome:
        raise ErroSDP("Ainda não sei quem é o técnico. Rode /kbr-servicedesk:configurar "
                      "para informar seu nome e e-mail.")
    return nome


def achar_id(display_id: str, token: str) -> str | None:
    busca = {"list_info": {"row_count": 1, "search_criteria": [
        {"field": "display_id", "condition": "is", "value": str(display_id)}]}}
    status, corpo = chamar("GET", "/requests", busca, token)
    encontrados = _resultado(status, corpo, "requests", list)
    return campo(encontrados[0], "id") if encontrados else None


def _id_obrigatorio(display_id: str, token: str) -> str:
    interno = achar_id(display_id, token)
    if not interno:
        raise ErroSDP(f"Não encontrei o chamado {display_id} no ServiceDesk. Confira o número.")
    return interno


def _resumir(bruto: dict) -> dict:
    return {
        "numero": str(bruto.get("display_id") or ""),
        "assunto": bruto.get("subject"),
        "solicitante": campo(bruto, "requester", "name"),
        "status": campo(bruto, "status", "name"),
        "urgencia": campo(bruto, "urgency", "name"),
        "criado_em": campo(bruto, "created_time", "display_value"),
    }


TAMANHO_PAGINA = 100  # linhas por página pedida ao SDP (list_info.row_count)

# Teto de páginas de _buscar_chamados. Só existe para estancar o laço se o SDP nunca zerar
# has_more_rows — inclusive se vier truthy e não booleano (a string "false", por exemplo, é
# truthy em Python) — nunca para limitar uma consulta real. Com TAMANHO_PAGINA=100,
# LIMITE_PAGINAS=100 é um teto de 10 mil chamados numa única busca (vale até para --todos, que
# inclui o histórico inteiro do técnico). Nenhum técnico da KINTO acumula perto disso em toda
# a carreira no ServiceDesk — o teto é folga, não limite de uso.
LIMITE_PAGINAS = 100


def _buscar_chamados(token: str, status_pedido: str | None,
                     todos: bool) -> tuple[list[dict], bool]:
    """Busca os chamados do técnico, paginando enquanto o SDP disser que há mais linhas.

    Devolve `(chamados, truncado)`. `truncado` só vira True se o laço bateu no teto de
    páginas sem o SDP nunca zerar `has_more_rows` — nesse caso devolvemos o que já foi
    coletado em vez de continuar batendo na API (ou de levantar e esconder o que já achamos);
    quem chama decide como sinalizar isso na saída, porque uma lista incompleta apresentada
    como se fosse completa faria o técnico achar que não tem mais chamados.
    """
    tecnico = _exigir_tecnico()
    criterios: list[dict] = [
        {"field": "technician.name", "condition": "is", "value": tecnico}]
    if status_pedido:
        criterios.append({"field": "status.name", "condition": "is",
                          "value": status_pedido, "logical_operator": "AND"})
    elif not todos:
        # Verificado contra o SDP real da KINTO em 2026-09-14: "is not" com "values"
        # (lista) funciona sem erro — mas a forma NÃO é o único jeito de errar aqui.
        criterios.append({"field": "status.name", "condition": "is not",
                          "values": STATUS_FINAIS, "logical_operator": "AND"})
    reunidos: list[dict] = []
    inicio = 1
    truncado = True
    for _ in range(LIMITE_PAGINAS):
        pedido = {"list_info": {"row_count": TAMANHO_PAGINA, "start_index": inicio,
                                "get_total_count": True, "search_criteria": criterios}}
        status, corpo = chamar("GET", "/requests", pedido, token)
        reunidos.extend(_resultado(status, corpo, "requests", list))
        if not campo(corpo, "list_info", "has_more_rows"):
            truncado = False
            break
        inicio += TAMANHO_PAGINA
    return reunidos, truncado


CAMPOS_QUERY = ["id", "display_id", "subject", "status", "requester", "technician",
               "group", "category", "subcategory", "urgency", "priority",
               "created_time", "resolved_time"]


COLUNAS_QUERY = ["numero", "assunto", "solicitante", "tecnico", "grupo", "categoria",
                 "subcategoria", "status", "urgencia", "prioridade", "criado_em",
                 "resolvido_em"]


def _resumir_query(bruto: dict) -> dict:
    return {
        "numero": str(bruto.get("display_id") or ""),
        "assunto": bruto.get("subject"),
        "solicitante": campo(bruto, "requester", "name"),
        "tecnico": campo(bruto, "technician", "name"),
        "grupo": campo(bruto, "group", "name"),
        "categoria": campo(bruto, "category", "name"),
        "subcategoria": campo(bruto, "subcategory", "name"),
        "status": campo(bruto, "status", "name"),
        "urgencia": campo(bruto, "urgency", "name"),
        "prioridade": campo(bruto, "priority", "name"),
        "criado_em": campo(bruto, "created_time", "display_value"),
        "resolvido_em": campo(bruto, "resolved_time", "display_value"),
    }


def _escrever_csv(caminho: Path, chamados: list[dict]) -> None:
    try:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        with caminho.open("w", newline="", encoding="utf-8-sig") as arquivo:
            escritor = csv.DictWriter(arquivo, fieldnames=COLUNAS_QUERY, delimiter=";")
            escritor.writeheader()
            for bruto in chamados:
                escritor.writerow(_resumir_query(bruto))
    except OSError as erro:
        raise ErroSDP(f'Não consegui gravar o arquivo "{caminho}" — {erro.strerror or erro}. '
                      'Se ele estiver aberto no Excel ou outro programa, feche e tente de '
                      'novo.') from None


def _arquivo_padrao(de: str | None, ate: str | None) -> Path:
    if de and ate:
        return Path(f"chamados_{de}_a_{ate}.csv")
    return Path("chamados.csv")


def _buscar_query(token: str, de_ms: str | None, ate_ms: str | None, campo_data: str,
                  status: str | None, abertos: bool) -> tuple[list[dict], bool]:
    """Busca chamados de toda a operação (todos os técnicos) para /kbr-servicedesk:query.

    Ao contrário de `_buscar_chamados`: não filtra por técnico, o filtro de data é opcional
    (a query pronta "abertos agora" não usa nenhum), e quando há filtro de status ele é ou
    um valor exato (`status`) ou a exclusão dos finais (`abertos`) — nunca os dois juntos,
    quem chama já garante isso.
    """
    criterios: list[dict] = []
    if de_ms and ate_ms:
        criterios.append({"field": campo_data, "condition": "between",
                          "values": [de_ms, ate_ms]})
    extra: dict | None = None
    if abertos:
        extra = {"field": "status.name", "condition": "is not", "values": STATUS_FINAIS}
    elif status:
        extra = {"field": "status.name", "condition": "is", "value": status}
    if extra:
        if criterios:
            extra["logical_operator"] = "AND"
        criterios.append(extra)
    reunidos: list[dict] = []
    inicio = 1
    truncado = True
    for _ in range(LIMITE_PAGINAS):
        pedido = {"list_info": {"row_count": TAMANHO_PAGINA, "start_index": inicio,
                                "get_total_count": True, "search_criteria": criterios,
                                "fields_required": CAMPOS_QUERY}}
        status_http, corpo = chamar("GET", "/requests", pedido, token)
        reunidos.extend(_resultado(status_http, corpo, "requests", list))
        if not campo(corpo, "list_info", "has_more_rows"):
            truncado = False
            break
        inicio += TAMANHO_PAGINA
    return reunidos, truncado


# --------------------------------------------------------------------------- comandos

def cmd_testar(_args) -> int:
    tecnico = _exigir_tecnico()
    token = access_token()
    abertos, truncado = _buscar_chamados(token, None, todos=False)
    _imprimir({"conectado": True, "tecnico": tecnico,
               "email": ler_config().get("tecnico_email"),
               "chamados_abertos": len(abertos),
               "truncado": truncado})
    return 0


def cmd_listar(args) -> int:
    # Confere o técnico antes de buscar o token: a mesma ordem trocada, em cmd_testar, fazia
    # um teste sem self.rede(...) bater numa chamada HTTP real contra a Zoho (Task 9). Aqui
    # abria a mesma porta — ver TesteListar.test_sem_tecnico_falha_antes_de_qualquer_chamada_
    # de_rede, que existe justamente para travar se essa ordem regredir de novo.
    tecnico = _exigir_tecnico()
    token = access_token()
    brutos, truncado = _buscar_chamados(
        token, getattr(args, "status", None), getattr(args, "todos", False))
    _imprimir({"tecnico": tecnico, "total": len(brutos),
               "chamados": [_resumir(item) for item in brutos],
               "truncado": truncado})
    return 0


def cmd_detalhe(args) -> int:
    token = access_token()
    interno = _id_obrigatorio(args.numero, token)
    status, corpo = chamar("GET", f"/requests/{interno}", None, token)
    bruto = _resultado(status, corpo, "request", dict)

    status_notas, corpo_notas = chamar(
        "GET", f"/requests/{interno}/notes", {"list_info": {"row_count": args.notas}}, token)
    if status_notas >= 300:
        # Swallow deliberado: um token que venceu entre as duas chamadas, ou falta de
        # permissão só para notas, não pode derrubar o chamado inteiro — ele ainda vale a
        # pena mostrar sem as notas. Mas o swallow tem que aparecer na saída
        # (`notas_indisponiveis`), senão essa falha fica indistinguível de um chamado que
        # realmente não tem nota nenhuma.
        notas_brutas: list = []
        notas_indisponiveis = True
    else:
        notas_brutas = _extrair(corpo_notas, "notes", list)
        for nota in notas_brutas:
            if not isinstance(nota, dict):
                raise ErroSDP(
                    "O ServiceDesk devolveu uma nota num formato que eu não entendo (a busca "
                    "funcionou, mas o conteúdo não é o esperado). Tente de novo; se "
                    "persistir, abra o chamado pelo portal.")
        notas_indisponiveis = False

    saida = _resumir(bruto)
    saida.update({
        "tecnico": campo(bruto, "technician", "name"),
        "grupo": campo(bruto, "group", "name"),
        "categoria": campo(bruto, "category", "name"),
        "email_solicitante": campo(bruto, "requester", "email_id"),
        "descricao": limpo(bruto.get("description")),
        "notas_indisponiveis": notas_indisponiveis,
        "notas": [{
            "autor": campo(nota, "created_by", "name"),
            "quando": campo(nota, "created_time", "display_value"),
            "visivel_ao_solicitante": bool(campo(nota, "show_to_requester")),
            "texto": limpo(campo(nota, "description"), 800),
        } for nota in notas_brutas],
    })
    _imprimir(saida)
    return 0


def entidades(texto: str) -> str:
    """Converte não-ASCII em entidades numéricas.

    O SDP renderiza acento de forma inconsistente conforme o cliente; entidade
    numérica sempre aparece certo.
    """
    return "".join(letra if ord(letra) < 128 else f"&#{ord(letra)};" for letra in texto)


def _ler_html(caminho: str) -> str:
    """Lê o arquivo com o texto da nota/resolução e devolve o conteúdo já sem espaços nas
    pontas.

    Qualquer falha vira `ErroSDP` — é o contrato do módulo (ver docstring do arquivo): nada
    além disso pode escapar para o técnico como traceback cru.

    A decodificação é sempre UTF-8, sem `errors="replace"` nem outra codificação de
    reserva: esse texto vai para o corpo de um chamado que pessoas de verdade leem, e um
    acento decodificado errado silenciosamente (um "ã" virando outro caractere qualquer)
    é um erro visível na tela do solicitante — pior do que pedir para o técnico salvar o
    arquivo de novo em UTF-8, o que custa uma tentativa.
    """
    arquivo = Path(caminho)
    if not arquivo.exists():
        raise ErroSDP(f"Não encontrei o arquivo com o texto: {caminho}")
    if arquivo.is_dir():
        raise ErroSDP(f"O caminho informado não é um arquivo, é uma pasta: {caminho}")
    if not arquivo.is_file():
        raise ErroSDP(f"O caminho informado não é um arquivo: {caminho}")
    try:
        conteudo = arquivo.read_text(encoding="utf-8").strip()
    except UnicodeDecodeError:
        raise ErroSDP(
            f"O arquivo {caminho} não está salvo em UTF-8 — parece ter sido salvo no "
            "codepage padrão do Windows (o que o PowerShell e o Bloco de Notas fazem por "
            "padrão). Abra o arquivo, salve de novo escolhendo UTF-8 como codificação e "
            "repita o comando."
        ) from None
    except OSError as erro:
        detalhe = erro.strerror or str(erro)
        raise ErroSDP(
            f"Não consegui ler o arquivo {caminho}: {detalhe}. Confira se ele ainda existe "
            "e se você tem permissão para abri-lo, e tente de novo."
        ) from None
    if not conteudo:
        raise ErroSDP("O arquivo com o texto está vazio.")
    return conteudo


def _simular(acao: str, numero: str, **extras) -> int:
    _imprimir({"simulacao": True, "acao": acao, "chamado": numero,
               "aviso": "nada foi enviado ao ServiceDesk; repita com --confirmar", **extras})
    return 0


def _enviar(metodo: str, caminho: str, payload: dict, token: str, acao: str,
            numero: str) -> int:
    status, corpo = chamar(metodo, caminho, payload, token)
    if status >= 300:
        raise ErroSDP(traduzir("sdp", corpo, http=status))
    _imprimir({"enviado": True, "acao": acao, "chamado": numero,
               "resposta": campo(corpo or {}, "response_status", "status") or "ok"})
    return 0


def cmd_nota(args) -> int:
    conteudo = _ler_html(args.arquivo)
    token = access_token()
    interno = _id_obrigatorio(args.numero, token)
    visivel = bool(args.visivel_solicitante)
    if not args.confirmar:
        return _simular("adicionar nota", args.numero,
                        visivel_ao_solicitante=visivel,
                        previa=limpo(conteudo, 600))
    payload = {"request_note": {
        "description": entidades(conteudo),
        "show_to_requester": visivel,
        "mark_first_response": False,
        "add_to_linked_requests": False,
    }}
    return _enviar("POST", f"/requests/{interno}/notes", payload, token,
                   "adicionar nota", args.numero)


def _enderecos(valor) -> list[str]:
    """Normaliza um campo de e-mail do chamado numa lista de endereços.

    O SDP é inconsistente nesses campos: `email_cc` ora vem como lista de strings, ora como
    lista de objetos (`{"email_id": ...}`), ora como string solta. Tratar os três aqui evita
    que um formato inesperado derrube o envio — ou, pior, que um destinatário desapareça em
    silêncio e o solicitante fique sem o e-mail.
    """
    itens = valor if isinstance(valor, list) else ([valor] if valor else [])
    saida = []
    for item in itens:
        if isinstance(item, dict):
            item = item.get("email_id") or item.get("email")
        if isinstance(item, str) and item.strip():
            saida.append(item.strip())
    return saida


def _sem_repetir(enderecos: list[str], excluir=()) -> list[str]:
    """A mesma lista, na ordem, sem repetição e sem os endereços de `excluir`.

    A comparação ignora a caixa: o SDP guarda o mesmo endereço às vezes em maiúsculas, e
    mandar duas vezes para a mesma pessoa é visível na caixa de entrada dela.
    """
    fora = {endereco.lower() for endereco in excluir if endereco}
    vistos: set[str] = set()
    saida = []
    for endereco in enderecos:
        chave = endereco.lower()
        if chave in vistos or chave in fora:
            continue
        vistos.add(chave)
        saida.append(endereco)
    return saida


def _enderecos_do_argumento(valores) -> list[str]:
    """Quebra os `--para`/`--cc` em endereços — a flag pode repetir e aceitar lista separada
    por vírgula, ponto e vírgula ou espaço."""
    partes: list[str] = []
    for valor in valores or []:
        partes.extend(re.split(r"[,;\s]+", valor))
    return _sem_repetir([parte.strip() for parte in partes if parte.strip()])


def destinatarios(pedido: dict, tecnico: str = "") -> tuple[list[str], list[str]]:
    """Monta o (para, cc) do "responder a todos" a partir do chamado.

    No Para vão o solicitante e quem estiver em `email_to`; no Cc, as cópias do chamado —
    `email_cc` e `email_ids_to_notify`, que é onde o portal guarda quem foi posto em cópia
    depois da abertura. O próprio técnico sai das duas listas: responder para si mesmo só
    enche a própria caixa de entrada.
    """
    para = _sem_repetir(_enderecos(campo(pedido, "requester", "email_id"))
                        + _enderecos(pedido.get("email_to")), excluir=[tecnico])
    cc = _sem_repetir(_enderecos(pedido.get("email_cc"))
                      + _enderecos(pedido.get("email_ids_to_notify")),
                      excluir=[tecnico, *para])
    return para, cc


def _respostas_gravadas(interno: str, token: str) -> set[str] | None:
    """Ids das respostas (`REQREPLY`) já registradas no chamado; `None` se não deu para ler.

    Serve de antes-e-depois do envio: é assim que o comando confirma que a resposta entrou
    no chamado de verdade, em vez de confiar apenas no HTTP 200 do POST. O endpoint de
    resposta não está na documentação pública da API v3 — ele foi descoberto na instância
    da KINTO —, então a confirmação não é luxo: é o que separa "enviado" de "aceitou e não
    fez nada".
    """
    status, corpo = chamar("GET", f"/requests/{interno}/notifications",
                           {"list_info": {"row_count": 50}}, token)
    if status >= 300 or not isinstance(corpo, dict):
        return None
    itens = corpo.get("notifications")
    if not isinstance(itens, list):
        return None
    return {str(item.get("id")) for item in itens if isinstance(item, dict)
            and "reply" in str(item.get("type") or "").lower()}


AVISO_SEM_CONFIRMACAO = (
    "O ServiceDesk aceitou o envio, mas a resposta ainda não apareceu na aba Conversas do "
    "chamado. NÃO reenvie antes de abrir o chamado e olhar: pode ser só demora do servidor, "
    "e um reenvio manda o mesmo e-mail duas vezes para o solicitante."
)


def cmd_responder(args) -> int:
    """Responde ao solicitante por e-mail — o "Reply All" do portal.

    É a diferença que importa em relação à nota: a nota fica no portal e não avisa ninguém
    (nem com `show_to_requester`, que só a torna visível para quem entrar lá), enquanto a
    resposta sai como e-mail para o solicitante e para as cópias do chamado.
    """
    conteudo = _ler_html(args.arquivo)
    token = access_token()
    interno = _id_obrigatorio(args.numero, token)
    status, corpo = chamar("GET", f"/requests/{interno}", None, token)
    pedido = _resultado(status, corpo, "request", dict)
    do_chamado_para, do_chamado_cc = destinatarios(
        pedido, ler_config().get("tecnico_email", ""))
    para = _enderecos_do_argumento(args.para) or do_chamado_para
    if args.so_solicitante:
        cc: list[str] = []
    else:
        cc = _sem_repetir(_enderecos_do_argumento(args.cc) or do_chamado_cc, excluir=para)
    if not para:
        raise ErroSDP("Não achei para quem responder neste chamado: ele não tem solicitante "
                      "com e-mail nem endereço em cópia. Informe o destinatário em --para.")
    # O assunto vai cru, sem `entidades()`: assunto de e-mail não é HTML, e uma entidade
    # numérica ali apareceria literal ("informa&#231;&#227;o") na caixa do solicitante.
    assunto = (args.assunto or pedido.get("subject") or f"Chamado {args.numero}").strip()
    if not args.confirmar:
        return _simular("responder ao solicitante", args.numero, para=para, cc=cc,
                        assunto=assunto, previa=limpo(conteudo, 600))

    antes = _respostas_gravadas(interno, token)
    payload = {"notification": {"to": para, "cc": cc, "subject": assunto,
                                "description": entidades(conteudo)}}
    status, corpo = chamar("POST", f"/requests/{interno}/_reply", payload, token)
    if status >= 300:
        raise ErroSDP(traduzir("sdp", corpo, http=status))
    depois = _respostas_gravadas(interno, token)
    confirmado = bool(antes is not None and depois is not None and (depois - antes))
    saida = {"enviado": True, "acao": "responder ao solicitante", "chamado": args.numero,
             "para": para, "cc": cc, "assunto": assunto, "confirmado": confirmado}
    if not confirmado:
        saida["aviso"] = AVISO_SEM_CONFIRMACAO
    _imprimir(saida)
    return 0


def cmd_status(args) -> int:
    novo = args.status
    espera = novo.strip().lower() in STATUS_DE_ESPERA
    if espera and not (args.comentario or "").strip():
        raise ErroSDP(f"O status \"{novo}\" é de espera: o ServiceDesk exige um comentário "
                      f"dizendo o motivo. Passe --comentario.")
    token = access_token()
    interno = _id_obrigatorio(args.numero, token)
    if not args.confirmar:
        return _simular("mudar status", args.numero, novo_status=novo,
                        comentario=args.comentario)
    corpo_request: dict = {"status": {"name": novo}}
    if espera:
        # Mesmo campo de texto livre que a nota (`description`) e a resolução
        # (`resolution.content`): passa por `entidades()` pela mesma razão — o SDP
        # renderiza acento cru de forma inconsistente conforme o cliente.
        corpo_request["onhold_scheduler"] = {"comments": entidades(args.comentario)}
    return _enviar("PUT", f"/requests/{interno}", {"request": corpo_request}, token,
                   "mudar status", args.numero)


def cmd_resolver(args) -> int:
    conteudo = _ler_html(args.arquivo)
    token = access_token()
    interno = _id_obrigatorio(args.numero, token)
    if not args.confirmar:
        return _simular("resolver chamado", args.numero, previa=limpo(conteudo, 600))
    payload = {"request": {"status": {"name": "Resolved"},
                           "resolution": {"content": entidades(conteudo)}}}
    return _enviar("PUT", f"/requests/{interno}", payload, token,
                   "resolver chamado", args.numero)


def _limpar_grant_code() -> None:
    """Esvazia o SDP_GRANT_CODE no arquivo: ele é de uso único."""
    caminho = kbr_secrets.caminho_arquivo()
    if not caminho.exists():
        return
    linhas = caminho.read_text(encoding="utf-8").splitlines()
    padrao = re.compile(r"^\s*SDP_GRANT_CODE\s*=")
    for indice, linha in enumerate(linhas):
        if padrao.match(linha):
            linhas[indice] = "SDP_GRANT_CODE="
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")


def cmd_autorizar(_args) -> int:
    try:
        grant = kbr_secrets.obter("SDP_GRANT_CODE", obrigatorio=False)
    except kbr_secrets.ErroSegredo as erro:
        # Defeito do plano original: se SDP_GRANT_CODE apontar para o 1Password
        # (op://...) e a leitura falhar, ErroSegredo escapava cru de cmd_autorizar —
        # main() só captura ErroSDP. Mesmo tratamento que _segredo() já dá a
        # SDP_CLIENT_ID/SDP_CLIENT_SECRET logo abaixo.
        raise ErroSDP(str(erro)) from None
    if not grant:
        raise ErroSDP("O campo SDP_GRANT_CODE está vazio. Volte ao passo 013 do wizard, "
                      "gere um código no console da Zoho e cole no arquivo de segredos. "
                      "Lembre que ele vale 10 minutos.")
    config = ler_config()
    status, corpo = _postar_form(config["token_url"], {
        "grant_type": "authorization_code",
        "code": grant,
        "client_id": _segredo("SDP_CLIENT_ID"),
        "client_secret": _segredo("SDP_CLIENT_SECRET"),
    })
    refresh = (corpo or {}).get("refresh_token")
    if status >= 300 or (corpo or {}).get("error"):
        raise ErroSDP(traduzir("zoho", corpo or {}))
    if not refresh:
        raise ErroSDP("A Zoho aceitou o código mas não devolveu um refresh token. Gere "
                      "outro código no passo 013 marcando a opção de acesso offline.")
    try:
        kbr_secrets.gravar("SDP_REFRESH_TOKEN", refresh)
    except kbr_secrets.ErroSegredo as erro:
        raise ErroSDP(str(erro)) from None
    _limpar_grant_code()
    _imprimir({"autorizado": True,
               "mensagem": "Acesso permanente gravado. O código de autorização foi apagado "
                           "porque é de uso único."})
    return 0


def cmd_escopos(_args) -> int:
    _imprimir({
        "console": "https://api-console.zoho.com",
        "escopos": ESCOPOS,
        "escopos_em_uma_linha": ",".join(ESCOPOS),
        "duracao_recomendada": "10 minutos",
    })
    return 0


def cmd_query(args) -> int:
    de, ate = args.de, args.ate
    if bool(de) != bool(ate):
        raise ErroSDP('Informe "--de" e "--ate" juntos, ou nenhum dos dois.')
    de_ms = _exigir_data("--de", de) if de else None
    ate_ms = _exigir_data("--ate", ate) if ate else None
    token = access_token()
    brutos, truncado = _buscar_query(
        token, de_ms, ate_ms, args.campo_data, args.status, args.abertos)
    caminho = Path(args.arquivo) if args.arquivo else _arquivo_padrao(de, ate)
    _escrever_csv(caminho, brutos)
    _imprimir({"arquivo": str(caminho.resolve()), "linhas": len(brutos),
               "truncado": truncado})
    return 0


# --------------------------------------------------------------------------- entrada

def _imprimir(dados: dict) -> None:
    print(json.dumps(dados, ensure_ascii=False, indent=2))


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="comando", required=True)

    sub.add_parser("testar", help="confirma o acesso e conta os chamados do técnico")

    listar = sub.add_parser("listar", help="lista os chamados do técnico")
    listar.add_argument("--status", default=None, help="filtra por um status exato")
    listar.add_argument("--todos", action="store_true", help="inclui os já finalizados")

    detalhe = sub.add_parser("detalhe", help="mostra um chamado e suas notas")
    detalhe.add_argument("numero")
    detalhe.add_argument("--notas", type=int, default=8)

    nota = sub.add_parser("nota", help="acrescenta uma nota ao chamado")
    nota.add_argument("numero")
    nota.add_argument("--arquivo", required=True, help="arquivo com o HTML da nota")
    nota.add_argument("--visivel-solicitante", action="store_true",
                      dest="visivel_solicitante")
    nota.add_argument("--confirmar", action="store_true")

    responder = sub.add_parser(
        "responder", help="responde ao solicitante por e-mail (o Reply All do portal)")
    responder.add_argument("numero")
    responder.add_argument("--arquivo", required=True, help="arquivo com o HTML da resposta")
    responder.add_argument("--para", action="append", default=None,
                           help="substitui os destinatários vindos do chamado; pode repetir "
                                "ou separar por vírgula")
    responder.add_argument("--cc", action="append", default=None,
                           help="substitui as cópias vindas do chamado; pode repetir ou "
                                "separar por vírgula")
    responder.add_argument("--so-solicitante", action="store_true", dest="so_solicitante",
                           help="responde só ao solicitante, sem as cópias do chamado")
    responder.add_argument("--assunto", default=None,
                           help="assunto do e-mail; por padrão, o assunto do chamado")
    responder.add_argument("--confirmar", action="store_true")

    status_cmd = sub.add_parser("status", help="muda o status do chamado")
    status_cmd.add_argument("numero")
    status_cmd.add_argument("status")
    status_cmd.add_argument("--comentario", default="")
    status_cmd.add_argument("--confirmar", action="store_true")

    resolver = sub.add_parser("resolver", help="resolve o chamado com um texto de conclusão")
    resolver.add_argument("numero")
    resolver.add_argument("--arquivo", required=True, help="arquivo com o HTML da conclusão")
    resolver.add_argument("--confirmar", action="store_true")

    sub.add_parser("autorizar", help="troca o código de autorização por acesso permanente")
    sub.add_parser("escopos", help="mostra os escopos a marcar no console da Zoho")

    query = sub.add_parser(
        "query", help="extrai chamados de toda a operação para CSV (sem filtro de técnico)")
    query.add_argument("--de", default=None, help="data inicial, AAAA-MM-DD (inclusiva)")
    query.add_argument("--ate", default=None, help="data final, AAAA-MM-DD (exclusiva)")
    query.add_argument("--campo-data", dest="campo_data", default="created_time",
                       choices=["created_time", "resolved_time"],
                       help="qual data usar no filtro de período: quando o chamado foi "
                            "criado ou quando foi resolvido")
    grupo_status = query.add_mutually_exclusive_group()
    grupo_status.add_argument("--status", default=None, help="filtra por um status exato")
    grupo_status.add_argument("--abertos", action="store_true",
                              help="só os chamados ainda não finalizados")
    query.add_argument("--arquivo", default=None, help="caminho do CSV de saída")

    return parser


COMANDOS = {"testar": cmd_testar, "listar": cmd_listar, "detalhe": cmd_detalhe,
            "nota": cmd_nota, "responder": cmd_responder, "status": cmd_status,
            "resolver": cmd_resolver,
            "autorizar": cmd_autorizar, "escopos": cmd_escopos, "query": cmd_query}


def main(argumentos: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = construir_parser().parse_args(argumentos)
    try:
        return COMANDOS[args.comando](args)
    except ErroSDP as erro:
        _imprimir({"erro": str(erro)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
