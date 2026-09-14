# -*- coding: utf-8 -*-
"""Acesso à API do ServiceDesk Plus Cloud (SDP) v3, com OAuth Zoho.

Os segredos vêm de kbr_secrets (arquivo ~/.kbr/secrets.env ou 1Password) e NUNCA
são impressos. Toda saída é JSON em UTF-8, sem credenciais e sem cabeçalhos HTTP.
Nenhuma operação de escrita acontece sem a flag --confirmar.
"""
from __future__ import annotations

import argparse
import html as _html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
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
                     "Gere outro no console (passo 5 do wizard) e cole de novo."),
    "invalid_client": ("Client ID ou Client Secret incorretos. Confira se copiou os dois "
                       "inteiros, sem espaços (passo 4 do wizard). Se o cliente foi criado "
                       "no console de outro país, refaça no americano: api-console.zoho.com."),
    "invalid_scope": ("O cliente não tem os escopos necessários. Gere um novo código com a "
                      "lista completa de escopos (passo 5 do wizard)."),
    "invalid_grant": ("O acesso foi revogado no 1Password ou na Zoho. Refaça os passos 5 e 6 "
                      "do wizard para gerar um novo acesso."),
}

_HTTP = {
    401: ("O acesso foi revogado ou o token venceu. Refaça os passos 5 e 6 do wizard "
          "(/kbr-servicedesk:configurar)."),
    403: ("O cliente não tem permissão para esta operação. Gere um novo código com a lista "
          "completa de escopos (passo 5 do wizard)."),
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
            return (f"A Zoho recusou a autenticação ({codigo}). Refaça os passos 4 a 6 do "
                    f"wizard (/kbr-servicedesk:configurar).")
        return ("A Zoho não devolveu um token de acesso. Refaça os passos 5 e 6 do wizard "
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

STATUS_FINAIS = ["Resolved", "Closed", "Cancelled"]


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
    if status >= 300:
        raise ErroSDP(traduzir("sdp", corpo, http=status))
    encontrados = (corpo or {}).get("requests") or []
    return encontrados[0].get("id") if encontrados else None


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


def _buscar_chamados(token: str, status_pedido: str | None, todos: bool) -> list[dict]:
    tecnico = _exigir_tecnico()
    criterios: list[dict] = [
        {"field": "technician.name", "condition": "is", "value": tecnico}]
    if status_pedido:
        criterios.append({"field": "status.name", "condition": "is",
                          "value": status_pedido, "logical_operator": "AND"})
    elif not todos:
        # Não verificado contra o SDP real (Task 9, Step 5 — sem credenciais neste ambiente).
        # Se o SDP recusar "is not" com "values" (lista), trocar por três critérios
        # encadeados, um por status, com "value" (singular) cada:
        #     for final in STATUS_FINAIS:
        #         criterios.append({"field": "status.name", "condition": "is not",
        #                           "value": final, "logical_operator": "AND"})
        # e ajustar test_exclui_status_finais_por_padrao para conferir os três nomes na URL.
        criterios.append({"field": "status.name", "condition": "is not",
                          "values": STATUS_FINAIS, "logical_operator": "AND"})
    reunidos: list[dict] = []
    inicio = 1
    while True:
        pedido = {"list_info": {"row_count": 100, "start_index": inicio,
                                "get_total_count": True, "search_criteria": criterios}}
        status, corpo = chamar("GET", "/requests", pedido, token)
        if status >= 300:
            raise ErroSDP(traduzir("sdp", corpo, http=status))
        reunidos.extend((corpo or {}).get("requests") or [])
        if not campo(corpo or {}, "list_info", "has_more_rows"):
            break
        inicio += 100
    return reunidos


# --------------------------------------------------------------------------- comandos

def cmd_testar(_args) -> int:
    tecnico = _exigir_tecnico()
    token = access_token()
    abertos = _buscar_chamados(token, None, todos=False)
    _imprimir({"conectado": True, "tecnico": tecnico,
               "email": ler_config().get("tecnico_email"),
               "chamados_abertos": len(abertos)})
    return 0


def cmd_listar(args) -> int:
    token = access_token()
    brutos = _buscar_chamados(token, getattr(args, "status", None), getattr(args, "todos", False))
    _imprimir({"tecnico": _exigir_tecnico(), "total": len(brutos),
               "chamados": [_resumir(item) for item in brutos]})
    return 0


def cmd_detalhe(args) -> int:
    token = access_token()
    interno = _id_obrigatorio(args.numero, token)
    status, corpo = chamar("GET", f"/requests/{interno}", None, token)
    if status >= 300:
        raise ErroSDP(traduzir("sdp", corpo, http=status))
    bruto = (corpo or {}).get("request") or {}

    status_notas, corpo_notas = chamar(
        "GET", f"/requests/{interno}/notes", {"list_info": {"row_count": args.notas}}, token)
    notas = (corpo_notas or {}).get("notes") or [] if status_notas < 300 else []

    saida = _resumir(bruto)
    saida.update({
        "tecnico": campo(bruto, "technician", "name"),
        "grupo": campo(bruto, "group", "name"),
        "categoria": campo(bruto, "category", "name"),
        "email_solicitante": campo(bruto, "requester", "email_id"),
        "descricao": limpo(bruto.get("description")),
        "notas": [{
            "autor": campo(nota, "created_by", "name"),
            "quando": campo(nota, "created_time", "display_value"),
            "visivel_ao_solicitante": bool(nota.get("show_to_requester")),
            "texto": limpo(nota.get("description"), 800),
        } for nota in notas],
    })
    _imprimir(saida)
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

    return parser


COMANDOS = {"testar": cmd_testar, "listar": cmd_listar, "detalhe": cmd_detalhe}


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
