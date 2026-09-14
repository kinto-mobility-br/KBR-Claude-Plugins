# Fundação do marketplace + plugin ServiceDesk — Plano, parte 2 (Tasks 9-15)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Continuação de `2026-09-13-fundacao-servicedesk.md` — leia o cabeçalho e a seção **Global Constraints** daquele arquivo antes de começar; tudo lá vale aqui.

**Pré-requisito:** Tasks 1 a 8 concluídas. Em particular, `plugins/kbr-servicedesk/scripts/sdp_api.py` já tem `ler_config`, `gravar_config`, `PADRAO_CONFIG`, `ESCOPOS`, `STATUS_DE_ESPERA`, `ErroSDP`, `traduzir`, `_abrir`, `_postar_form`, `access_token` e `chamar`.

---

### Task 9: `sdp_api.py` — comandos de leitura (`testar`, `listar`, `detalhe`)

**Files:**
- Modify: `plugins/kbr-servicedesk/scripts/sdp_api.py`
- Modify: `plugins/kbr-servicedesk/tests/test_sdp_api.py`

**Interfaces:**
- Consumes: da Task 8 — `access_token()`, `chamar()`, `ler_config()`, `ErroSDP`, `traduzir`.
- Produces:
  - `achar_id(display_id: str, token: str) -> str | None` — resolve o nº de exibição para o id interno.
  - `limpo(bruto: str, limite: int = 3000) -> str` — HTML para texto.
  - `cmd_testar(args) -> int`, `cmd_listar(args) -> int`, `cmd_detalhe(args) -> int`.
  - `construir_parser() -> argparse.ArgumentParser`, `COMANDOS: dict`, `main(argumentos=None) -> int`.
  - Toda saída é `json.dumps(..., ensure_ascii=False, indent=2)` no stdout. Erro vira `{"erro": "<texto PT-BR>"}` com código de saída 1.

- [ ] **Step 1: Escrever os testes de leitura**

Acrescentar a `plugins/kbr-servicedesk/tests/test_sdp_api.py`:

```python
TOKEN_OK = {"access_token": "acc-1", "expires_in": 3600}

CHAMADO_LISTA = {
    "requests": [
        {"display_id": "4942", "id": "173861000000000001",
         "subject": "Writeback de KM no 2Z Fleet",
         "status": {"name": "In Progress"},
         "requester": {"name": "Beltrano", "email_id": "beltrano@kintomobility.com.br"},
         "urgency": {"name": "Alta"},
         "created_time": {"display_value": "May 29, 2026 11:26 AM"}},
    ],
    "list_info": {"has_more_rows": False},
}


class BaseComando(BaseSDP):
    def executar(self, *argumentos):
        captura = io.StringIO()
        with contextlib.redirect_stdout(captura):
            codigo = sdp_api.main(list(argumentos))
        return codigo, captura.getvalue()

    def json_da_saida(self, saida):
        return json.loads(saida)


class TesteListar(BaseComando):
    def test_devolve_os_campos_pedidos(self):
        self.rede(TOKEN_OK, CHAMADO_LISTA)
        codigo, saida = self.executar("listar")
        self.assertEqual(codigo, 0)
        dados = self.json_da_saida(saida)
        primeiro = dados["chamados"][0]
        self.assertEqual(primeiro["numero"], "4942")
        self.assertEqual(primeiro["assunto"], "Writeback de KM no 2Z Fleet")
        self.assertEqual(primeiro["solicitante"], "Beltrano")
        self.assertEqual(primeiro["status"], "In Progress")
        self.assertEqual(primeiro["urgencia"], "Alta")

    def test_nao_expoe_o_id_interno(self):
        self.rede(TOKEN_OK, CHAMADO_LISTA)
        _, saida = self.executar("listar")
        self.assertNotIn("173861000000000001", saida)

    def test_filtra_pelo_tecnico_do_config(self):
        rede = self.rede(TOKEN_OK, CHAMADO_LISTA)
        self.executar("listar")
        self.assertIn("Fulano+de+Tal", rede.chamadas[1]["url"])

    def test_exclui_status_finais_por_padrao(self):
        rede = self.rede(TOKEN_OK, CHAMADO_LISTA)
        self.executar("listar")
        url = urllib.parse.unquote_plus(rede.chamadas[1]["url"])
        self.assertIn("Resolved", url)
        self.assertIn("is not", url)

    def test_todos_nao_exclui_nada(self):
        rede = self.rede(TOKEN_OK, CHAMADO_LISTA)
        self.executar("listar", "--todos")
        url = urllib.parse.unquote_plus(rede.chamadas[1]["url"])
        self.assertNotIn("is not", url)

    def test_pagina_enquanto_houver_mais(self):
        pagina1 = {"requests": CHAMADO_LISTA["requests"],
                   "list_info": {"has_more_rows": True}}
        pagina2 = {"requests": CHAMADO_LISTA["requests"],
                   "list_info": {"has_more_rows": False}}
        self.rede(TOKEN_OK, pagina1, pagina2)
        _, saida = self.executar("listar")
        self.assertEqual(len(self.json_da_saida(saida)["chamados"]), 2)

    def test_manda_o_cabecalho_de_autorizacao(self):
        rede = self.rede(TOKEN_OK, CHAMADO_LISTA)
        self.executar("listar")
        cabecalhos = {k.lower(): v for k, v in rede.chamadas[1]["cabecalhos"].items()}
        self.assertEqual(cabecalhos["authorization"], "Zoho-oauthtoken acc-1")
        self.assertEqual(cabecalhos["accept"], sdp_api.ACEITA)

    def test_erro_http_vira_mensagem_em_portugues(self):
        self.rede(TOKEN_OK, urllib.error.HTTPError(
            "u", 403, "Forbidden", {}, io.BytesIO(b"{}")))
        codigo, saida = self.executar("listar")
        self.assertEqual(codigo, 1)
        self.assertIn("permissão", self.json_da_saida(saida)["erro"].lower())


class TesteDetalhe(BaseComando):
    BUSCA = {"requests": [{"id": "173861000000000001", "display_id": "4942"}]}
    DETALHE = {"request": {
        "display_id": "4942", "subject": "Assunto",
        "status": {"name": "In Progress"},
        "requester": {"name": "Beltrano", "email_id": "b@kintomobility.com.br"},
        "technician": {"name": "Fulano de Tal"}, "group": {"name": "IT Dados"},
        "category": {"name": "Dados"}, "urgency": {"name": "Alta"},
        "created_time": {"display_value": "May 29, 2026 11:26 AM"},
        "description": "<p>Primeira linha</p><p>Segunda &amp; linha</p>"}}
    NOTAS = {"notes": [{"description": "<p>uma nota</p>",
                        "created_by": {"name": "Fulano"},
                        "created_time": {"display_value": "Jun 1, 2026 09:00 AM"},
                        "show_to_requester": True}]}

    def test_converte_a_descricao_para_texto(self):
        self.rede(TOKEN_OK, self.BUSCA, self.DETALHE, self.NOTAS)
        _, saida = self.executar("detalhe", "4942")
        dados = self.json_da_saida(saida)
        self.assertIn("Primeira linha", dados["descricao"])
        self.assertIn("Segunda & linha", dados["descricao"])
        self.assertNotIn("<p>", dados["descricao"])

    def test_traz_as_notas(self):
        self.rede(TOKEN_OK, self.BUSCA, self.DETALHE, self.NOTAS)
        _, saida = self.executar("detalhe", "4942")
        notas = self.json_da_saida(saida)["notas"]
        self.assertEqual(notas[0]["autor"], "Fulano")
        self.assertEqual(notas[0]["texto"], "uma nota")

    def test_nao_expoe_o_id_interno(self):
        self.rede(TOKEN_OK, self.BUSCA, self.DETALHE, self.NOTAS)
        _, saida = self.executar("detalhe", "4942")
        self.assertNotIn("173861000000000001", saida)

    def test_chamado_inexistente(self):
        self.rede(TOKEN_OK, {"requests": []})
        codigo, saida = self.executar("detalhe", "9999")
        self.assertEqual(codigo, 1)
        self.assertIn("9999", self.json_da_saida(saida)["erro"])


class TesteTestar(BaseComando):
    def test_devolve_tecnico_e_contagem(self):
        self.rede(TOKEN_OK, CHAMADO_LISTA)
        codigo, saida = self.executar("testar")
        self.assertEqual(codigo, 0)
        dados = self.json_da_saida(saida)
        self.assertTrue(dados["conectado"])
        self.assertEqual(dados["tecnico"], "Fulano de Tal")
        self.assertEqual(dados["chamados_abertos"], 1)

    def test_sem_tecnico_no_config_avisa(self):
        sdp_api.gravar_config({"tecnico_nome": ""})
        codigo, saida = self.executar("testar")
        self.assertEqual(codigo, 1)
        self.assertIn("técnico", self.json_da_saida(saida)["erro"].lower())


class TesteLimpo(unittest.TestCase):
    def test_quebra_de_linha_e_entidades(self):
        texto = sdp_api.limpo("<p>um</p><br/><div>dois &amp; três</div>")
        self.assertIn("um", texto)
        self.assertIn("dois & três", texto)
        self.assertNotIn("<", texto)

    def test_vazio(self):
        self.assertEqual(sdp_api.limpo(""), "(vazio)")

    def test_corta_no_limite(self):
        self.assertTrue(sdp_api.limpo("x" * 500, limite=100).endswith("..."))
```

Acrescentar `import contextlib` e `import urllib.parse` aos imports do arquivo de teste.

- [ ] **Step 2: Rodar e ver falhar**

Run: `python scripts/testar.py`
Expected: FAIL — `AttributeError: module 'sdp_api' has no attribute 'main'`

- [ ] **Step 3: Implementar os comandos de leitura**

Acrescentar ao fim de `sdp_api.py`:

```python
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
    token = access_token()
    tecnico = _exigir_tecnico()
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
```

- [ ] **Step 4: Rodar os testes**

Run: `python scripts/testar.py`
Expected: PASS — 94 + 18 = 112 testes OK.

- [ ] **Step 5: Conferir o filtro de status contra o SDP de verdade**

⚠️ **Ponto a verificar com a API real.** Os scripts atuais do workspace só usaram
`search_criteria` com `value` (um valor). O filtro que exclui os status finais usa
`"condition": "is not"` com `"values"` (lista), o que é o documentado para múltiplos valores mas
**não foi exercitado na KINTO ainda**.

Com as credenciais já configuradas, rodar:

```bash
python plugins/kbr-servicedesk/scripts/sdp_api.py listar
python plugins/kbr-servicedesk/scripts/sdp_api.py listar --todos
```

Expected: o primeiro traz menos chamados que o segundo, e nenhum Resolved/Closed/Cancelled.

Se o SDP recusar a lista, trocar por três critérios encadeados, um por status:

```python
        for indice, final in enumerate(STATUS_FINAIS):
            criterios.append({"field": "status.name", "condition": "is not",
                              "value": final, "logical_operator": "AND"})
```

e ajustar `test_exclui_status_finais_por_padrao` para conferir os três nomes na URL.

- [ ] **Step 6: Commit**

```bash
git add plugins/kbr-servicedesk/scripts/sdp_api.py plugins/kbr-servicedesk/tests/test_sdp_api.py
git status --short
git commit -m "$(cat <<'MSG'
feat(kbr-servicedesk): comandos testar, listar e detalhe

Busca pelo técnico do config, exclui status finais por padrão e pagina
enquanto houver linhas. O id interno do SDP nunca aparece na saída: o
chamado é sempre identificado pelo número de exibição.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FxSq1YTHKimYYBJmKABcBa
MSG
)"
```

---

### Task 10: `sdp_api.py` — comandos de escrita (`nota`, `status`, `resolver`)

**Files:**
- Modify: `plugins/kbr-servicedesk/scripts/sdp_api.py`
- Modify: `plugins/kbr-servicedesk/tests/test_sdp_api.py`

**Interfaces:**
- Consumes: da Task 9 — `_id_obrigatorio`, `chamar`, `access_token`, `_imprimir`, `construir_parser`, `COMANDOS`, `STATUS_DE_ESPERA`.
- Produces: `entidades(texto: str) -> str` (não-ASCII para `&#NNN;`), `cmd_nota(args) -> int`, `cmd_status(args) -> int`, `cmd_resolver(args) -> int`. Os três exigem `--confirmar`; sem a flag imprimem `{"simulacao": true, "acao": ..., ...}` e saem com 0 **sem tocar na rede de escrita**. O conteúdo HTML entra por `--arquivo <caminho>`, nunca por argumento de linha de comando.

- [ ] **Step 1: Escrever os testes de escrita**

```python
class TesteEscrita(BaseComando):
    BUSCA = {"requests": [{"id": "173861000000000001", "display_id": "4942"}]}
    OK = {"response_status": {"status": "success"}, "request_note": {"id": "n1"}}

    def arquivo_html(self, conteudo="<p>Olá, tudo certo.</p>"):
        caminho = Path(self.tmp.name) / "nota.html"
        caminho.write_text(conteudo, encoding="utf-8")
        return str(caminho)

    def test_nota_sem_confirmar_nao_escreve(self):
        rede = self.rede(TOKEN_OK, self.BUSCA)
        codigo, saida = self.executar("nota", "4942", "--arquivo", self.arquivo_html())
        self.assertEqual(codigo, 0)
        self.assertTrue(self.json_da_saida(saida)["simulacao"])
        self.assertTrue(all(c["metodo"] == "GET" for c in rede.chamadas[1:]))

    def test_nota_com_confirmar_posta(self):
        rede = self.rede(TOKEN_OK, self.BUSCA, self.OK)
        codigo, _ = self.executar("nota", "4942", "--arquivo", self.arquivo_html(),
                                  "--confirmar")
        self.assertEqual(codigo, 0)
        envio = rede.chamadas[-1]
        self.assertEqual(envio["metodo"], "POST")
        self.assertIn("/notes", envio["url"])
        payload = json.loads(urllib.parse.parse_qs(envio["corpo"])["input_data"][0])
        self.assertIn("request_note", payload)
        self.assertFalse(payload["request_note"]["show_to_requester"])

    def test_nota_visivel_ao_solicitante(self):
        rede = self.rede(TOKEN_OK, self.BUSCA, self.OK)
        self.executar("nota", "4942", "--arquivo", self.arquivo_html(),
                      "--visivel-solicitante", "--confirmar")
        payload = json.loads(
            urllib.parse.parse_qs(rede.chamadas[-1]["corpo"])["input_data"][0])
        self.assertTrue(payload["request_note"]["show_to_requester"])

    def test_acentos_viram_entidades(self):
        rede = self.rede(TOKEN_OK, self.BUSCA, self.OK)
        self.executar("nota", "4942", "--arquivo",
                      self.arquivo_html("<p>informação</p>"), "--confirmar")
        payload = json.loads(
            urllib.parse.parse_qs(rede.chamadas[-1]["corpo"])["input_data"][0])
        descricao = payload["request_note"]["description"]
        self.assertIn("&#231;", descricao)
        self.assertNotIn("ç", descricao)

    def test_arquivo_inexistente(self):
        self.rede(TOKEN_OK)
        codigo, saida = self.executar("nota", "4942", "--arquivo", "nao-existe.html",
                                      "--confirmar")
        self.assertEqual(codigo, 1)
        self.assertIn("não encontrei", self.json_da_saida(saida)["erro"].lower())

    def test_status_simples(self):
        rede = self.rede(TOKEN_OK, self.BUSCA, {"response_status": {"status": "success"}})
        self.executar("status", "4942", "In Progress", "--confirmar")
        envio = rede.chamadas[-1]
        self.assertEqual(envio["metodo"], "PUT")
        payload = json.loads(urllib.parse.parse_qs(envio["corpo"])["input_data"][0])
        self.assertEqual(payload["request"]["status"]["name"], "In Progress")
        self.assertNotIn("onhold_scheduler", payload["request"])

    def test_status_de_espera_exige_comentario(self):
        self.rede(TOKEN_OK, self.BUSCA)
        codigo, saida = self.executar("status", "4942", "On Hold", "--confirmar")
        self.assertEqual(codigo, 1)
        self.assertIn("comentário", self.json_da_saida(saida)["erro"].lower())

    def test_status_de_espera_com_comentario_manda_onhold(self):
        rede = self.rede(TOKEN_OK, self.BUSCA, {"response_status": {"status": "success"}})
        self.executar("status", "4942", "Aguardando Aprovação",
                      "--comentario", "esperando validação", "--confirmar")
        payload = json.loads(
            urllib.parse.parse_qs(rede.chamadas[-1]["corpo"])["input_data"][0])
        self.assertEqual(payload["request"]["onhold_scheduler"]["comments"],
                         "esperando validação")

    def test_resolver_manda_status_e_resolution(self):
        rede = self.rede(TOKEN_OK, self.BUSCA, {"response_status": {"status": "success"}})
        self.executar("resolver", "4942", "--arquivo", self.arquivo_html(), "--confirmar")
        payload = json.loads(
            urllib.parse.parse_qs(rede.chamadas[-1]["corpo"])["input_data"][0])
        self.assertEqual(payload["request"]["status"]["name"], "Resolved")
        self.assertIn("content", payload["request"]["resolution"])

    def test_resolver_sem_confirmar_nao_escreve(self):
        rede = self.rede(TOKEN_OK, self.BUSCA)
        codigo, saida = self.executar("resolver", "4942", "--arquivo", self.arquivo_html())
        self.assertEqual(codigo, 0)
        self.assertTrue(self.json_da_saida(saida)["simulacao"])
        self.assertTrue(all(c["metodo"] == "GET" for c in rede.chamadas[1:]))

    def test_erro_do_sdp_na_escrita_vira_portugues(self):
        self.rede(TOKEN_OK, self.BUSCA, urllib.error.HTTPError(
            "u", 400, "Bad", {},
            io.BytesIO(json.dumps({"response_status": {"messages": [
                {"message": "status inválido"}]}}).encode())))
        codigo, saida = self.executar("status", "4942", "Inexistente", "--confirmar")
        self.assertEqual(codigo, 1)
        self.assertIn("status inválido", self.json_da_saida(saida)["erro"])
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python scripts/testar.py`
Expected: FAIL — `invalid choice: 'nota'`

- [ ] **Step 3: Implementar a escrita**

Acrescentar a `sdp_api.py`, antes de `construir_parser`:

```python
def entidades(texto: str) -> str:
    """Converte não-ASCII em entidades numéricas.

    O SDP renderiza acento de forma inconsistente conforme o cliente; entidade
    numérica sempre aparece certo.
    """
    return "".join(letra if ord(letra) < 128 else f"&#{ord(letra)};" for letra in texto)


def _ler_html(caminho: str) -> str:
    arquivo = Path(caminho)
    if not arquivo.is_file():
        raise ErroSDP(f"Não encontrei o arquivo com o texto: {caminho}")
    conteudo = arquivo.read_text(encoding="utf-8").strip()
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
        corpo_request["onhold_scheduler"] = {"comments": args.comentario}
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
```

E registrar no parser e no despachante:

```python
    nota = sub.add_parser("nota", help="acrescenta uma nota ao chamado")
    nota.add_argument("numero")
    nota.add_argument("--arquivo", required=True, help="arquivo com o HTML da nota")
    nota.add_argument("--visivel-solicitante", action="store_true",
                      dest="visivel_solicitante")
    nota.add_argument("--confirmar", action="store_true")

    status_cmd = sub.add_parser("status", help="muda o status do chamado")
    status_cmd.add_argument("numero")
    status_cmd.add_argument("status")
    status_cmd.add_argument("--comentario", default="")
    status_cmd.add_argument("--confirmar", action="store_true")

    resolver = sub.add_parser("resolver", help="resolve o chamado com um texto de conclusão")
    resolver.add_argument("numero")
    resolver.add_argument("--arquivo", required=True, help="arquivo com o HTML da conclusão")
    resolver.add_argument("--confirmar", action="store_true")
```

```python
COMANDOS = {"testar": cmd_testar, "listar": cmd_listar, "detalhe": cmd_detalhe,
            "nota": cmd_nota, "status": cmd_status, "resolver": cmd_resolver}
```

- [ ] **Step 4: Rodar os testes**

Run: `python scripts/testar.py`
Expected: PASS — 112 + 12 = 124 testes OK.

- [ ] **Step 5: Commit**

```bash
git add plugins/kbr-servicedesk/scripts/sdp_api.py plugins/kbr-servicedesk/tests/test_sdp_api.py
git status --short
git commit -m "$(cat <<'MSG'
feat(kbr-servicedesk): comandos nota, status e resolver com --confirmar

Sem a flag, os três só simulam e mostram a prévia; nada sai para a rede.
O HTML entra por arquivo, nunca por argumento. Acentos viram entidades
numéricas. Status de espera exige comentário e vai em onhold_scheduler.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FxSq1YTHKimYYBJmKABcBa
MSG
)"
```

---

### Task 11: `sdp_api.py` — comando `autorizar` e `escopos`

**Files:**
- Modify: `plugins/kbr-servicedesk/scripts/sdp_api.py`
- Modify: `plugins/kbr-servicedesk/tests/test_sdp_api.py`

**Interfaces:**
- Consumes: da Task 8 — `_postar_form`, `ler_config`, `traduzir`, `_segredo`; do `kbr_secrets` — `gravar`, `obter`, `caminho_arquivo`.
- Produces: `cmd_autorizar(args) -> int` (troca `SDP_GRANT_CODE` por `SDP_REFRESH_TOKEN` via `kbr_secrets.gravar`, depois limpa o grant code) e `cmd_escopos(args) -> int` (imprime a lista de escopos para o wizard mostrar). `_limpar_grant_code() -> None`.

- [ ] **Step 1: Escrever os testes**

```python
class TesteAutorizar(BaseComando):
    def preparar(self, grant="codigo-de-autorizacao"):
        kbr_secrets.caminho_arquivo().write_text(
            "SDP_CLIENT_ID=cid\nSDP_CLIENT_SECRET=csec\n"
            f"SDP_GRANT_CODE={grant}\nSDP_REFRESH_TOKEN=\n", encoding="utf-8")

    def test_troca_o_grant_code_por_refresh_token(self):
        self.preparar()
        rede = self.rede({"refresh_token": "rt-novo", "access_token": "acc", "expires_in": 3600})
        codigo, saida = self.executar("autorizar")
        self.assertEqual(codigo, 0)
        self.assertTrue(self.json_da_saida(saida)["autorizado"])
        self.assertIn("grant_type=authorization_code", rede.chamadas[0]["corpo"])
        self.assertEqual(kbr_secrets.ler_arquivo()["SDP_REFRESH_TOKEN"], "rt-novo")

    def test_apaga_o_grant_code_depois(self):
        self.preparar()
        self.rede({"refresh_token": "rt-novo", "expires_in": 3600})
        self.executar("autorizar")
        self.assertEqual(kbr_secrets.ler_arquivo()["SDP_GRANT_CODE"], "")

    def test_nao_imprime_nenhum_token(self):
        self.preparar()
        self.rede({"refresh_token": "rt-super-secreto", "access_token": "acc-secreto",
                   "expires_in": 3600})
        _, saida = self.executar("autorizar")
        self.assertNotIn("rt-super-secreto", saida)
        self.assertNotIn("acc-secreto", saida)

    def test_codigo_expirado_traduzido(self):
        self.preparar()
        self.rede({"error": "invalid_code"})
        codigo, saida = self.executar("autorizar")
        self.assertEqual(codigo, 1)
        self.assertIn("10 minutos", self.json_da_saida(saida)["erro"])

    def test_grant_code_vazio_orienta_o_passo_5(self):
        self.preparar(grant="")
        codigo, saida = self.executar("autorizar")
        self.assertEqual(codigo, 1)
        self.assertIn("SDP_GRANT_CODE", self.json_da_saida(saida)["erro"])

    def test_resposta_sem_refresh_token(self):
        self.preparar()
        self.rede({"access_token": "acc"})
        codigo, saida = self.executar("autorizar")
        self.assertEqual(codigo, 1)
        self.assertIn("refresh", self.json_da_saida(saida)["erro"].lower())

    def test_grava_via_kbr_secrets_respeitando_op(self):
        kbr_secrets.caminho_arquivo().write_text(
            "SDP_CLIENT_ID=cid\nSDP_CLIENT_SECRET=csec\nSDP_GRANT_CODE=gc\n"
            "SDP_REFRESH_TOKEN=op://Cofre/Item/refresh-token\n", encoding="utf-8")
        falso = OpFalsoSDP(saida="ok")
        kbr_secrets._rodar_op = falso
        self.rede({"refresh_token": "rt-novo", "expires_in": 3600})
        self.executar("autorizar")
        texto = kbr_secrets.caminho_arquivo().read_text(encoding="utf-8")
        self.assertIn("op://Cofre/Item/refresh-token", texto)
        self.assertNotIn("rt-novo", texto)
        self.assertEqual(falso.chamadas[0][:2], ["item", "edit"])


class TesteEscopos(BaseComando):
    def test_lista_os_tres_escopos(self):
        codigo, saida = self.executar("escopos")
        self.assertEqual(codigo, 0)
        dados = self.json_da_saida(saida)
        self.assertEqual(dados["escopos"], sdp_api.ESCOPOS)
        self.assertIn("api-console.zoho.com", dados["console"])
```

Acrescentar no topo do arquivo de teste a cópia do duplo do 1Password (o mesmo da Task 2, aqui com outro nome para não depender do outro arquivo de teste):

```python
from types import SimpleNamespace


class OpFalsoSDP:
    def __init__(self, saida="", erro="", codigo=0):
        self.saida, self.erro, self.codigo = saida, erro, codigo
        self.chamadas = []

    def __call__(self, argumentos, **kwargs):
        self.chamadas.append(list(argumentos))
        return SimpleNamespace(returncode=self.codigo, stdout=self.saida, stderr=self.erro)
```

E no `tearDown` da `BaseSDP`, restaurar o `_rodar_op`:

```python
        kbr_secrets._rodar_op = self._rodar_op_original
```
com `self._rodar_op_original = kbr_secrets._rodar_op` no `setUp`.

- [ ] **Step 2: Rodar e ver falhar**

Run: `python scripts/testar.py`
Expected: FAIL — `invalid choice: 'autorizar'`

- [ ] **Step 3: Implementar**

```python
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
    grant = kbr_secrets.obter("SDP_GRANT_CODE", obrigatorio=False)
    if not grant:
        raise ErroSDP("O campo SDP_GRANT_CODE está vazio. Volte ao passo 5 do wizard, "
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
                      "outro código no passo 5 marcando a opção de acesso offline.")
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
```

No parser:

```python
    sub.add_parser("autorizar", help="troca o código de autorização por acesso permanente")
    sub.add_parser("escopos", help="mostra os escopos a marcar no console da Zoho")
```

No despachante, acrescentar `"autorizar": cmd_autorizar, "escopos": cmd_escopos`.

- [ ] **Step 4: Rodar os testes e conferir que nada vaza**

Run:
```bash
python scripts/testar.py
python plugins/kbr-servicedesk/scripts/sdp_api.py escopos
```
Expected: PASS — 124 + 9 = 133 testes OK. O `escopos` imprime os três escopos e o console americano.

- [ ] **Step 5: Commit**

```bash
git add plugins/kbr-servicedesk/scripts/sdp_api.py plugins/kbr-servicedesk/tests/test_sdp_api.py
git status --short
git commit -m "$(cat <<'MSG'
feat(kbr-servicedesk): comandos autorizar e escopos

autorizar troca o código de autorização pelo refresh token via
kbr_secrets.gravar (arquivo ou 1Password, conforme a chave) e apaga o
código, que é de uso único. Nenhum token aparece na saída.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FxSq1YTHKimYYBJmKABcBa
MSG
)"
```

---

### Task 12: Empacotar o `kbr-servicedesk` e escrever a skill `sdp`

**Files:**
- Create: `plugins/kbr-servicedesk/.claude-plugin/plugin.json`
- Create: `plugins/kbr-servicedesk/skills/sdp/SKILL.md`
- Create: `plugins/kbr-servicedesk/README.md`

**Interfaces:**
- Consumes: das Tasks 9-11 — os oito subcomandos de `sdp_api.py`.
- Produces: plugin `kbr-servicedesk` versão `0.1.0`, dependente de `kbr-core`, com a skill `/kbr-servicedesk:sdp`.

- [ ] **Step 1: Escrever o `plugin.json`**

```json
{
  "name": "kbr-servicedesk",
  "displayName": "KINTO — ServiceDesk",
  "version": "0.1.0",
  "description": "Gestor de chamados do ServiceDesk Plus Cloud por menu, com wizard de configuração para quem nunca mexeu com OAuth.",
  "author": { "name": "KINTO Brasil — TI" },
  "dependencies": ["kbr-core"],
  "keywords": ["servicedesk", "sdp", "chamados", "kinto", "manageengine"]
}
```

- [ ] **Step 2: Escrever a skill `sdp`**

`plugins/kbr-servicedesk/skills/sdp/SKILL.md`:

```markdown
---
name: sdp
description: Painel conversacional dos chamados do ServiceDesk Plus da KINTO — lista os seus chamados, mostra o detalhe de um, adiciona nota, muda status e resolve, sempre com confirmação antes de gravar. Use quando o usuário pedir "meus chamados", "abrir o ServiceDesk", "ver o chamado 4942", "responder o solicitante", "resolver o chamado", "SDP", ou invocar /kbr-servicedesk:sdp.
---

# Gestor de chamados — ServiceDesk KINTO

Você opera como um **painel conversacional**. A cada turno você executa a ação pedida (ou pede
confirmação) e **termina SEMPRE com o menu**. O usuário escolhe pelo número ou digita texto
livre.

## Regras duras (não violar)

- 🔢 **Sempre termine com o bloco de menu.** Nunca deixe o usuário sem próximos passos.
- ⌨️ **Aceite texto livre.** "mostra o 4942" é a opção 2 no chamado 4942. Se ficar ambíguo,
  ofereça as duas ou três leituras mais prováveis em vez de adivinhar.
- 🛑 **Nunca grave sem confirmação explícita no mesmo turno.** Mostre exatamente o que vai
  enviar e pergunte "confirmar? (s/n)". Só depois do "s" chame o script com `--confirmar`.
- 🔒 **Segredo nunca no chat.** Não peça, não mostre, não repita valor de `SDP_*`. Se faltar
  credencial, leve para a opção 6.
- 🔢 **Chamado é sempre pelo número de exibição** (4942). O id interno do SDP não aparece.
- 🇧🇷 Tudo em PT-BR, com acentuação correta.

## Como chamar o script

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/sdp_api.py" <subcomando> [...]
```

A saída é sempre JSON. Se vier `{"erro": "..."}`, **mostre o texto do erro como está** — ele já
foi escrito em PT-BR para o usuário — e ofereça o próximo passo.

| Ação | Comando |
|---|---|
| Confirmar acesso | `testar` |
| Listar | `listar` · `listar --status "On Hold"` · `listar --todos` |
| Detalhe | `detalhe <nº>` · `detalhe <nº> --notas 20` |
| Nota | `nota <nº> --arquivo <html> [--visivel-solicitante] [--confirmar]` |
| Status | `status <nº> "<status>" [--comentario "<motivo>"] [--confirmar]` |
| Resolver | `resolver <nº> --arquivo <html> [--confirmar]` |

**Sem `--confirmar` os três últimos só simulam** e devolvem a prévia. Use isso para montar a
confirmação: rode sem a flag, mostre a prévia, pergunte, e repita com a flag.

## O menu

Rode `testar` no começo da conversa para preencher o cabeçalho. Se ele falhar por credencial,
vá direto para o passo 6.

```
🗂️  GESTOR DE CHAMADOS — ServiceDesk KINTO
    Técnico: <nome> · chamados abertos: <N>

1. Meus chamados abertos          4. Mudar status de um chamado
2. Ver detalhe de um chamado      5. Resolver chamado
3. Adicionar nota a um chamado    6. Configurar acesso ao ServiceDesk
0. Sair
```

## Cada opção

1. **Listar** — `listar`, e apresente uma tabela com número, assunto, solicitante, status,
   criado em e urgência. Ofereça filtrar por status ou incluir os finalizados.
2. **Detalhe** — peça o número se não veio. `detalhe <nº>`. Mostre assunto, solicitante,
   status, datas, descrição e as últimas notas. Ofereça as ações 3, 4 e 5 sobre esse chamado.
3. **Nota** — pergunte o que dizer e **se o solicitante deve ver**. Redija o HTML, grave no
   diretório temporário da sessão, rode sem `--confirmar`, mostre a prévia em texto, pergunte,
   e só então repita com `--confirmar`. Apague o arquivo depois.
4. **Status** — ofereça os status usados na KINTO: Open, In Progress, On Hold, Aguardando
   Aprovação, Resolved, Closed. **On Hold** e **Aguardando Aprovação** exigem `--comentario`
   com o motivo — pergunte antes. Confirme e envie.
5. **Resolver** — peça o texto de conclusão, redija o HTML, simule, mostre, confirme, envie.
6. **Configurar** — invoque a skill `configurar` deste mesmo plugin.

## Como escrever nota e conclusão

- HTML simples: `<p>`, `<ul>`/`<li>`, `<b>`, `<code>`. Nada de CSS, tabela ou imagem.
- **Primeira pessoa do singular** ("verifiquei", "encontrei", "ajustei"), nunca "identificamos".
- Tom cordial e direto. Ao falar de dado que parece errado, use hedge: "aparentemente",
  "ao que tudo indica", "provavelmente". Não afirme erro categórico.
- Escreva o arquivo no diretório temporário da sessão, não na pasta do projeto.
- Não se preocupe com acentuação no HTML: o script converte para entidades sozinho.

## Quando algo dá errado

| O que o script diz | O que fazer |
|---|---|
| Menciona `/kbr-servicedesk:configurar` | Credencial ausente ou inválida: leve para a opção 6 |
| "O acesso foi revogado ou o token venceu" | Opção 6, passos 5 e 6 do wizard |
| "Não encontrei o chamado" | Confirme o número com o usuário |
| "é de espera: o ServiceDesk exige um comentário" | Pergunte o motivo e repita com `--comentario` |
| "Não consegui falar com o ServiceDesk" | Rede ou VPN; ofereça tentar de novo |
```

- [ ] **Step 3: Escrever o `README.md` do plugin**

```markdown
# kbr-servicedesk

Gestor de chamados do ServiceDesk Plus Cloud da KINTO, dentro do Claude Code.

## Skills

- **`/kbr-servicedesk:sdp`** — o painel: lista seus chamados, mostra detalhe, adiciona nota,
  muda status e resolve. Nada é gravado sem você confirmar.
- **`/kbr-servicedesk:configurar`** — o wizard de 8 passos que configura seu acesso. Feito para
  quem nunca ouviu falar de OAuth.

## Primeira vez

Abra `/kbr-servicedesk:sdp` e escolha a opção 6. O wizard leva uns 15 minutos e você precisa
de: acesso ao portal do ServiceDesk, um navegador e o Bloco de Notas.

Ao final você terá um **Self Client** individual na Zoho — uma chave só sua, que pode ser
revogada a qualquer momento sem afetar ninguém.

## O que ele guarda, e onde

| Onde | O quê |
|---|---|
| `~/.kbr/secrets.env` | `SDP_CLIENT_ID`, `SDP_CLIENT_SECRET`, `SDP_REFRESH_TOKEN` — protegidos pelo `kbr-core` |
| `~/.kbr/config.json` | seu nome e e-mail de técnico, e os endereços da API — não são segredo |
| `~/.kbr/cache/` | o token de acesso de 1 hora, renovado sozinho |

Nada disso entra em repositório nenhum.

## Escopos OAuth

O wizard manda marcar exatamente estes três, e nenhum a mais:

```
SDPOnDemand.requests.READ,SDPOnDemand.requests.CREATE,SDPOnDemand.requests.UPDATE
```

`python scripts/sdp_api.py escopos` imprime a lista pronta para copiar.

## Pré-requisitos

Python 3.10 ou superior no `PATH` e o plugin `kbr-core` (instalado junto, por dependência).

## Fora de escopo nesta versão

Documentação local de chamados em `tasks/`, anexos, criação de chamado, e qualquer data center
da Zoho fora do americano.
```

- [ ] **Step 4: Validar**

Run:
```bash
python scripts/testar.py
python scripts/validar.py
```
Expected: 133 testes PASS; os **dois** plugins validados, sem aviso de plugin pulado.

- [ ] **Step 5: Commit**

```bash
git add plugins/kbr-servicedesk/.claude-plugin/plugin.json plugins/kbr-servicedesk/skills/sdp/SKILL.md plugins/kbr-servicedesk/README.md
git status --short
git commit -m "$(cat <<'MSG'
feat(kbr-servicedesk): empacotar o plugin e a skill sdp

Painel conversacional com menu de 6 opções, texto livre aceito e
confirmação obrigatória antes de qualquer escrita no ServiceDesk.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FxSq1YTHKimYYBJmKABcBa
MSG
)"
```

---

### Task 13: Skill `configurar` — o wizard de 8 passos

**Files:**
- Create: `plugins/kbr-servicedesk/skills/configurar/SKILL.md`

**Interfaces:**
- Consumes: do `kbr-core` — `kbr_secrets.py` com `init`, `registrar`, `status`, `editar`; deste plugin — `sdp_api.py` com `escopos`, `autorizar`, `testar`; da Task 14 — o guia em `${CLAUDE_PLUGIN_ROOT}/guia/index.html` (a skill já o referencia; se ainda não existir, o passo 3 avisa e segue só pelo chat).
- Produces: skill `/kbr-servicedesk:configurar`, invocável direto ou pela opção 6 do menu.

- [ ] **Step 1: Escrever a skill**

```markdown
---
name: configurar
description: Wizard passo a passo que configura o acesso de uma pessoa ao ServiceDesk Plus da KINTO — cria o Self Client na Zoho, guarda as credenciais no arquivo de segredos e testa a conexão. Escrito para quem nunca ouviu falar de OAuth. Use quando o usuário pedir "configurar o ServiceDesk", "não consigo acessar os chamados", escolher a opção 6 do gestor, ou quando qualquer comando do ServiceDesk reclamar de credencial ausente ou inválida.
---

# Wizard — configurar o acesso ao ServiceDesk

Quem está do outro lado **usa o ServiceDesk pelo navegador e nunca mexeu com OAuth, terminal ou
Python**. Sabe abrir um site, copiar e colar, e abrir o Bloco de Notas. Escreva para essa pessoa.

## Regras duras

- 🐢 **Um passo por turno.** Nunca despeje dois passos de uma vez.
- 🔒 **Nunca peça um segredo no chat.** Client ID, Client Secret e código de autorização vão
  **direto para o arquivo**, pelo editor. Se a pessoa colar um no chat mesmo assim: avise que
  aquele valor ficou registrado na conversa, e que o certo é **apagar o Self Client na Zoho e
  criar outro**. Não siga fingindo que não viu.
- 🗣️ **Sem jargão.** Não diga "OAuth", "grant", "endpoint", "token" sem explicar. Prefira
  "chave de acesso", "código temporário", "permissões".
- ✅ **Verifique cada passo antes de avançar.** Nunca diga "deve ter funcionado".
- 🔁 **Rodar de novo não estraga nada.** Ao iniciar, rode a verificação e pule para o primeiro
  passo pendente, avisando o que já estava pronto.
- 🇧🇷 Tudo em PT-BR.

## O mini-menu

Cada turno termina assim:

```
1. Feito, próximo passo   2. Explicar de novo   3. Estou com erro   0. Sair (dá para voltar depois)
```

- **2** — reescreva o passo de outro jeito, mais devagar, com outra analogia.
- **3** — abra o diagnóstico do passo atual (tabela no fim desta skill) e **volte ao mesmo passo**.
- **0** — diga onde parou e que `/kbr-servicedesk:configurar` retoma daqui.

## Comandos

```bash
# do kbr-core
python "${CLAUDE_PLUGIN_ROOT}/../kbr-core/scripts/kbr_secrets.py" <init|registrar|status|editar>
# deste plugin
python "${CLAUDE_PLUGIN_ROOT}/scripts/sdp_api.py" <escopos|autorizar|testar>
```

Se o caminho relativo para o `kbr-core` não funcionar na instalação, use a skill
`/kbr-core:secrets` em vez do caminho direto — ela faz o mesmo.

---

## Passo 1 — Ver se a máquina está pronta

**Diga:** antes de tudo vou conferir se o computador tem o que precisa. Isso é rápido e você
não faz nada agora.

**Execute:** `python --version` e o `status` do kbr-core.

- Python 3.10 ou maior: siga.
- Python ausente ou antigo: **pare** e ensine a instalar pela Microsoft Store (procure
  "Python 3.12", botão Obter). Depois peça para **fechar e reabrir o Claude Code** e rodar o
  wizard de novo.

**Confirme também** que a pessoa consegue entrar no portal do ServiceDesk pelo navegador. Sem
isso, nada adiante.

## Passo 2 — Entender o que vai acontecer

Sem comando nenhum. Explique, nessa ordem:

1. O ServiceDesk exige uma **chave de acesso individual** para programas — é diferente da sua
   senha, e serve só para esta máquina.
2. Vamos criar essa chave no site da Zoho, que é a empresa que hospeda o ServiceDesk.
3. A chave fica guardada **num arquivo seu**, numa pasta protegida do seu usuário. Eu não
   consigo ler esse arquivo; os programas leem por dentro.
4. **Nada de secreto vai ser digitado aqui na conversa.** Você cola tudo no Bloco de Notas.
5. Se um dia quiser cancelar, é só apagar a chave no site da Zoho. Não afeta mais ninguém.

Pergunte se ficou claro antes de seguir.

## Passo 3 — Criar o arquivo de segredos

**Execute:**
```bash
python ".../kbr_secrets.py" init
python ".../kbr_secrets.py" registrar --plugin kbr-servicedesk --chaves SDP_CLIENT_ID,SDP_CLIENT_SECRET,SDP_GRANT_CODE,SDP_REFRESH_TOKEN
```

**Abra o guia** no navegador: `${CLAUDE_PLUGIN_ROOT}/guia/index.html`. Ele tem a foto de cada
tela que vem a seguir. Se o arquivo não existir, avise que vai ser só pelo texto e siga.

**Verifique:** `status --plugin kbr-servicedesk` deve listar as quatro chaves como vazias.

## Passo 4 — Criar a chave no site da Zoho

**Diga o que fazer, nesta ordem** (figuras 4.1 a 4.4 do guia):

1. Abra **https://api-console.zoho.com** e entre com o mesmo login do ServiceDesk.
2. Clique em **ADD CLIENT**.
3. Escolha o tipo **Self Client** — é o terceiro cartão. Confirme em **CREATE**.
4. Aparecem duas linhas longas: **Client ID** e **Client Secret**.

**Execute:** `editar` — isso abre o arquivo no Bloco de Notas.

**Peça:** cole o Client ID depois de `SDP_CLIENT_ID=` e o Client Secret depois de
`SDP_CLIENT_SECRET=`, sem espaço antes nem depois do `=`. Salve (Ctrl+S) e feche.

⚠️ **Deixe a aba da Zoho aberta**, ela é usada no passo seguinte.

**Verifique:** `status --plugin kbr-servicedesk` deve mostrar as duas como preenchidas.

## Passo 5 — Gerar o código temporário

**Execute primeiro:** `sdp_api.py escopos`, e mostre a linha única de escopos para copiar.

**Diga o que fazer** (figuras 5.1 e 5.2):

1. Na mesma tela da Zoho, abra a aba **Generate Code**.
2. Em **Scope**, cole a linha de permissões que acabei de mostrar.
3. Em **Time Duration**, escolha **10 minutes**.
4. Em **Scope Description**, escreva qualquer coisa, por exemplo "Claude Code KINTO".
5. **CREATE** → escolha seu portal se ele perguntar → copie o código que aparece.

⏱️ **Avise:** esse código vale **10 minutos**. Se demorar, é só gerar outro.

**Execute:** `editar`. **Peça:** cole em `SDP_GRANT_CODE=`, salve e feche.

**Verifique:** `status` mostra `SDP_GRANT_CODE` preenchida.

## Passo 6 — Trocar o código pelo acesso permanente

**Diga:** agora eu troco esse código temporário por um acesso que não expira. Você não faz nada.

**Execute:** `sdp_api.py autorizar`.

- Sucesso: o refresh token foi gravado e o código temporário apagado (ele é de uso único).
- Erro: **mostre o texto do erro como veio** — ele já explica o que fazer — e volte ao passo
  indicado.

**Verifique:** `status` mostra `SDP_REFRESH_TOKEN` preenchida e `SDP_GRANT_CODE` vazia.

## Passo 7 — Dizer quem você é, e testar

**Pergunte:** seu nome completo **exatamente como aparece no ServiceDesk** (é assim que os
chamados são procurados) e seu e-mail corporativo. Isso não é segredo, pode digitar aqui.

**Execute:** grave no `~/.kbr/config.json` em `servicedesk.tecnico_nome` e
`servicedesk.tecnico_email`, preservando o resto do arquivo. Depois rode `sdp_api.py testar`.

- Sucesso: "Conectado como **Fulano de Tal**. Você tem **N** chamados atribuídos."
- Zero chamados **não** é erro: a conexão funcionou.
- "Ainda não sei quem é o técnico": o nome não foi gravado; refaça.
- Nome diferente do cadastrado: `testar` conecta mas conta zero. Se a pessoa esperava ter
  chamados, peça para conferir a grafia exata no portal.

## Passo 8 — Proteger e encerrar

**Execute:** `status`. Se a proteção estiver ausente, **pergunte** se pode ativá-la e explique
em uma frase: é uma regra que impede qualquer sessão do Claude Code de abrir o arquivo de
segredos. Só depois do "sim", rode `proteger`.

**Feche com um resumo:**

- o que ficou pronto (chave criada, acesso gravado, conexão testada, proteção ativa);
- como usar daqui pra frente: `/kbr-servicedesk:sdp`;
- que para trocar de credencial é só rodar este wizard de novo;
- que a chave é individual e pode ser revogada no site da Zoho quando quiser.

---

## Diagnóstico — "estou com erro"

| Passo | Sintoma | Resposta |
|---|---|---|
| 1 | `python` não é reconhecido | Instale pela Microsoft Store e **reabra o Claude Code** |
| 1 | Python 3.9 ou menor | Instale a versão nova pela Store; as duas convivem |
| 4 | Não acho o **ADD CLIENT** | Confira se entrou em api-console.zoho.com, não no portal do ServiceDesk |
| 4 | Só aparece Client ID | Clique no olho ao lado do Client Secret para revelá-lo |
| 4 | `status` diz vazia depois de colar | O arquivo não foi salvo, ou colou antes do `=`. Rode `editar` de novo |
| 5 | A aba Generate Code não existe | Ela só aparece em cliente do tipo **Self Client**. Refaça o passo 4 |
| 5 | "Invalid Scope" ao criar | Algum espaço ou quebra na linha colada. Copie de novo do `escopos` |
| 5 | Pediu para escolher o portal | Normal. Escolha o portal da KINTO |
| 6 | "O código expirou ou já foi usado" | Volte ao passo 5 e gere outro; ele vale 10 minutos |
| 6 | "Client ID ou Client Secret incorretos" | Volte ao 4; provavelmente faltou um pedaço ao copiar |
| 6 | Menciona console de outro país | O cliente foi criado em `.eu` ou `.in`. Apague e refaça em api-console.zoho.com |
| 6 | "não devolveu um refresh token" | Gere o código de novo marcando acesso offline |
| 7 | Conecta mas conta zero | Ou não há chamados seus, ou o nome está escrito diferente do portal |
| 7 | "O acesso foi revogado" | O Self Client foi apagado na Zoho. Refaça do passo 4 |
| qualquer | "Não consegui falar com o ServiceDesk" | Rede ou VPN. Tente de novo em um minuto |
```

- [ ] **Step 2: Validar**

Run: `python scripts/validar.py`
Expected: os dois plugins validados, agora com duas skills no `kbr-servicedesk`.

- [ ] **Step 3: Commit**

```bash
git add plugins/kbr-servicedesk/skills/configurar/SKILL.md
git status --short
git commit -m "$(cat <<'MSG'
feat(kbr-servicedesk): wizard de configuração em 8 passos

Um passo por turno, mini-menu com "explicar de novo" e "estou com erro",
verificação automática a cada etapa e tabela de diagnóstico. Nenhum
segredo passa pelo chat: tudo vai para o arquivo pelo editor.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FxSq1YTHKimYYBJmKABcBa
MSG
)"
```

---

### Task 14: Guia HTML com as capturas do console da Zoho

**Files:**
- Create: `plugins/kbr-servicedesk/guia/index.html` (mais `assets/` e `img/`)

**Interfaces:**
- Consumes: da Task 13 — o texto dos 8 passos, que o guia espelha; a numeração das figuras (4.1 a 4.4, 5.1 e 5.2) é a mesma citada na skill.
- Produces: `${CLAUDE_PLUGIN_ROOT}/guia/index.html`, abrível por `file://` sem servidor e sem gerar nada na máquina de quem usa.

⚠️ **Esta task precisa do Fábio logado no console da Zoho.** As capturas não podem ser
inventadas. Se ele não estiver disponível, **pare** e avise: as outras tasks não dependem desta,
e a skill `configurar` já funciona só pelo chat.

- [ ] **Step 1: Capturar as telas**

Com o Fábio logado em `https://api-console.zoho.com`, capturar, com a área de clicar destacada
e qualquer segredo borrado:

| Arquivo | Tela |
|---|---|
| `img/04-1-console-inicial.png` | Console recém-aberto, com o botão ADD CLIENT |
| `img/04-2-escolher-self-client.png` | Os cartões de tipo, com Self Client destacado |
| `img/04-3-client-criado.png` | Client ID e Client Secret (**borrados**), com o ícone de revelar |
| `img/04-4-copiar-credenciais.png` | Detalhe do botão de copiar |
| `img/05-1-aba-generate-code.png` | Aba Generate Code com Scope, Time Duration e Description preenchidos |
| `img/05-2-codigo-gerado.png` | O código temporário (**borrado**), com o prazo visível |

Salvar em `plugins/kbr-servicedesk/guia/img/`. PNG, largura máxima 1200px.

- [ ] **Step 2: Gerar o esqueleto pelo design system**

A skill `docs-html` do workspace produz o HTML no padrão KINTO. Rodar a partir da raiz do
repositório de plugins, com a marca do projeto apontando para os logos da KINTO em
`E:\Projetos\Kinto Brasil\assets\design-system\`:

```bash
python ~/.claude/skills/docs-init/scripts/descobrir.py .
# conferir o resultado, ajustar o .docs-brand.yml e então:
python ~/.claude/skills/docs-html/scripts/aplicar_marca.py plugins/kbr-servicedesk/guia --raiz=.
```

**Regra da casa:** ao escrever qualquer componente (callout, card, tabela, steps), **copie a
marcação de `~/.claude/skills/docs-html/referencia/componentes.html`** e troque só o texto.
Callout é um grid de duas colunas: `<span class="ico">` mais um `<div>` com o conteúdo. Filho
solto dentro dele quebra o layout em silêncio.

- [ ] **Step 3: Escrever o conteúdo**

Uma seção por passo do wizard, na mesma ordem e com os mesmos títulos. Cada seção do console
leva a figura numerada com legenda. Incluir:

- No topo, um callout de informação: para que serve o guia e que ele acompanha o chat.
- Um bloco de copiar com a linha única de escopos:
  `SDPOnDemand.requests.READ,SDPOnDemand.requests.CREATE,SDPOnDemand.requests.UPDATE`
- Um callout de aviso no passo 5 sobre os 10 minutos de validade do código.
- Um callout de perigo no passo 4: não colar Client ID nem Secret no chat.
- A tabela de diagnóstico da skill, ao final.

- [ ] **Step 4: Abrir no navegador e olhar**

Run: abrir `plugins/kbr-servicedesk/guia/index.html` no navegador.

Conferir de verdade, nos dois temas (claro e escuro): as imagens aparecem; nenhum callout está
com texto sobreposto; a tabela não estoura a largura; os links funcionam. **HTML que valida pode
estar visualmente quebrado, e quem vê primeiro não pode ser o Fábio.**

- [ ] **Step 5: Commit**

```bash
git add plugins/kbr-servicedesk/guia
git status --short
git commit -m "$(cat <<'MSG'
docs(kbr-servicedesk): guia HTML do wizard com as telas do console Zoho

Uma seção por passo, no design system KINTO, com captura de cada tela e a
área de clicar destacada. Abre por file://, sem servidor.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FxSq1YTHKimYYBJmKABcBa
MSG
)"
```

---

### Task 15: Roteiro manual, publicação e fechamento

**Files:**
- Create: `docs/roteiro-teste-manual.md`
- Modify: `README.md` (seção de estado, se algo mudou)

**Interfaces:**
- Consumes: tudo das Tasks 1-14.
- Produces: as tags `kbr-core--v0.1.0` e `kbr-servicedesk--v0.1.0`, e o repositório com remote no GitHub.

- [ ] **Step 1: Escrever o roteiro de teste manual**

`docs/roteiro-teste-manual.md`:

```markdown
# Roteiro de teste manual — antes da primeira publicação

Rodar **num perfil de Windows limpo** (ou numa conta de usuário nova), com Claude Code e
Python instalados e nada de `~/.kbr`. O objetivo é provar que uma pessoa que nunca viu isso
consegue chegar ao fim sozinha.

## 1. Instalação

- [ ] `/plugin marketplace add kinto-mobility-br/KBR-Claude-Plugins` funciona com as
      credenciais git da pessoa
- [ ] `/plugin install kbr-servicedesk@kinto-brasil` instala **também** o `kbr-core`, por dependência
- [ ] `/help` mostra `/kbr-servicedesk:sdp`, `/kbr-servicedesk:configurar` e `/kbr-core:secrets`

## 2. Wizard

- [ ] `/kbr-servicedesk:sdp` detecta a falta de credencial e leva à opção 6
- [ ] O guia HTML abre no navegador e as imagens aparecem
- [ ] Os 8 passos foram concluídos **usando só o guia**, sem ninguém explicar por fora
- [ ] O passo 7 responde "Conectado como <nome>" com a contagem certa
- [ ] Cronometrar: a meta é 15 minutos

## 3. Proteção

- [ ] `cat ~/.kbr/secrets.env` é **negado**, com explicação em PT-BR
- [ ] `Read` do mesmo arquivo é negado
- [ ] `grep -r SDP_ ~/.kbr` é negado
- [ ] `~/.kbr/config.json` **pode** ser lido
- [ ] Reler o transcript inteiro: **nenhum** valor de Client Secret, código ou token aparece
- [ ] `/kbr-core:secrets status` mostra tudo preenchido sem revelar valor

## 4. Operação

- [ ] Opção 1 lista os chamados com número, assunto, solicitante, status e urgência
- [ ] Opção 2 mostra o detalhe e as notas de um chamado real
- [ ] Opção 3 num **chamado de teste**: a prévia aparece antes; responder "n" **não** envia nada;
      responder "s" posta a nota e ela aparece no portal
- [ ] Opção 4 para "On Hold" pede o comentário antes de deixar seguir
- [ ] Texto livre funciona: "mostra o 4942" abre o detalhe

## 5. Erros

- [ ] Com a rede desligada, a mensagem fala de conexão e VPN, sem despejar traceback
- [ ] Com `SDP_REFRESH_TOKEN` apagado à mão, a mensagem aponta o wizard

## 6. Repositório

- [ ] `git status` em qualquer repo **nunca** mostra `secrets.env`
- [ ] `python scripts/testar.py` passa
- [ ] `python scripts/validar.py` passa
- [ ] `python scripts/verificar_shared.py` passa
- [ ] A CI está verde no GitHub
```

- [ ] **Step 2: Rodar a suíte inteira uma última vez**

Run:
```bash
python scripts/verificar_shared.py
python scripts/testar.py
python scripts/validar.py
```
Expected: os três passam. Se qualquer um falhar, **pare** e corrija antes de publicar.

- [ ] **Step 3: Executar o roteiro manual**

Percorrer `docs/roteiro-teste-manual.md` de ponta a ponta e marcar cada caixa. Itens que
falharem viram correção agora, não depois da tag.

- [ ] **Step 4: Criar o repositório remoto e dar push**

```bash
gh repo create kinto-mobility-br/KBR-Claude-Plugins --private --source=. --remote=origin
git push -u origin main
```

Se a organização exigir aprovação para criar repositório, criar pelo site e então:

```bash
git remote add origin https://github.com/kinto-mobility-br/KBR-Claude-Plugins.git
git push -u origin main
```

- [ ] **Step 5: Publicar a versão 0.1.0 dos dois plugins**

```bash
python scripts/criar_tag.py kbr-core --push
python scripts/criar_tag.py kbr-servicedesk --push
git tag --list
```
Expected: `kbr-core--v0.1.0` e `kbr-servicedesk--v0.1.0` no remote.

- [ ] **Step 6: Commit do roteiro**

```bash
git add docs/roteiro-teste-manual.md
git status --short
git commit -m "$(cat <<'MSG'
docs: roteiro de teste manual antes da primeira publicação

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FxSq1YTHKimYYBJmKABcBa
MSG
)"
git push
```

---

## Depois desta fatia

As fatias 2 (`kbr-docs`) e 3 (`kbr-dynamics-bc`) têm specs próprias, ainda não escritas. Voltar
ao `superpowers:brainstorming` para cada uma.
