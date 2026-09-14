# `/kbr-servicedesk:query` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar o subcomando `query` a `sdp_api.py` e a skill `/kbr-servicedesk:query`, que extraem chamados de **toda a operação** do ServiceDesk (todos os técnicos) filtrados por período em um CSV local, para análise fora do chat.

**Architecture:** Um novo subcomando de leitura (`query`) em `plugins/kbr-servicedesk/scripts/sdp_api.py`, reaproveitando `access_token()`, `chamar()`, `campo()`, `_extrair()`/`_resultado()`, `LIMITE_PAGINAS`/`TAMANHO_PAGINA` já existentes. Uma skill nova (`skills/query/SKILL.md`) traduz linguagem natural e as 6 opções de menu em flags do comando e apresenta o resultado. Nenhuma chamada de escrita (`PUT`/`POST`) é alcançável a partir deste comando.

**Tech Stack:** Python ≥ 3.10, biblioteca padrão apenas (`csv`, `datetime`, `argparse`, `pathlib`).

## Global Constraints

- PT-BR em tudo — mensagens de script, comentários, SKILL.md, commits. Identificadores de código e termos técnicos ficam no original.
- Python ≥ 3.10, só biblioteca padrão — nenhum plugin pode exigir `pip install`.
- Todo script mantém `def main() -> int` + `raise SystemExit(main())` (já existe em `sdp_api.py`; não muda).
- Portável, Windows primeiro — `pathlib` sempre, nunca barra fixa.
- Caminhos em skills sempre via `${CLAUDE_PLUGIN_ROOT}`.
- Segredo nunca é impresso por script nenhum, nem em mensagem de erro.
- **`query` nunca grava no ServiceDesk.** Só `GET`. Não existe flag `--confirmar` porque não existe nada a confirmar — isso é verificado por teste (nenhuma chamada de rede em `query` usa outro método que não `GET`).
- **Regra dura de filtro de data — já mordeu este projeto uma vez:** o filtro por período é **sempre** uma única condição `{"field": <campo>, "condition": "between", "values": [inicio_ms, fim_ms]}`. **Nunca** duas condições `greater than`/`less than` encadeadas — verificado ao vivo em 2026-09-14 que essa forma não filtra nada e devolve a base inteira sem erro. Todo teste desta feature que toca em data confere isso.
- `query`, ao contrário de `listar`, **não filtra por técnico por padrão** (é para a operação inteira) e **não exclui os status finais por padrão** (dado histórico quer os resolvidos/fechados também, a menos que `--abertos` seja pedido).
- Colunas do CSV, nesta ordem exata: `numero`, `assunto`, `solicitante`, `tecnico`, `grupo`, `categoria`, `subcategoria`, `status`, `urgencia`, `prioridade`, `criado_em`, `resolvido_em`. O id interno do SDP (`id`) nunca aparece no CSV nem no JSON de saída — só o `display_id`.
- Cuidado com `: ` (dois-pontos + espaço) num valor sem aspas na `description` do frontmatter YAML de um SKILL.md — quebra o parse silenciosamente. Use travessão "—".
- Nunca `git add -A`. Nomeie os caminhos e confira `git status --short` antes de cada commit.
- Runner de teste do repositório: `python scripts/testar.py` roda tudo; para rodar só este arquivo durante o desenvolvimento, use `cd plugins/kbr-servicedesk/tests && python -m unittest test_sdp_api.<Classe>.<teste> -v` (comando confirmado nesta sessão).

## Nota sobre dois pontos em que este plano ajusta a spec

A spec `docs/superpowers/specs/2026-09-14-query-analytics-design.md`, ao redigir a seção 4 (assinatura do comando) e a tabela da seção 5 (opção 5, "todos os chamados ainda abertos"), descreve duas coisas que não fecham entre si ao pé da letra — achado ao reler o código atual de `sdp_api.py` para fundamentar este plano:

1. **`--de`/`--ate` viram opcionais, não obrigatórios.** A assinatura da seção 4 os mostra sem colchetes (obrigatórios), mas a opção 5 do menu ("todos os chamados ainda abertos") precisa rodar **sem filtro de data nenhum** — não dá para expressar isso com `--de`/`--ate` obrigatórios sem inventar uma data arbitrária, o que seria pior (uma data inventada no código é exatamente o tipo de suposição não verificada que este projeto já foi mordido por antes). Este plano torna os dois opcionais, exigindo que venham **juntos ou nenhum dos dois** (erro claro se só um vier).
2. **Uma flag nova, `--abertos`, cobre a opção 5.** A tabela da seção 5 diz que a opção 5 usa `--status` com `is not` Resolved/Closed/Canceled — mas a seção 4 define `--status` como filtro por **um nome exato** (`is`), a mesma semântica de `listar --status`. As duas coisas não cabem na mesma flag. Este plano acrescenta `--abertos` (booleana, mutuamente exclusiva com `--status`) que replica exatamente a exclusão por `STATUS_FINAIS` que `_buscar_chamados` já usa em `listar`. `--status` continua fazendo só filtro por valor exato.

Nenhuma outra decisão da spec muda. Ambos os ajustes são registrados aqui, não escondidos.

---

## Task 1: `_data_para_ms` — conversão de data e a regra dura do `between`

**Files:**
- Modify: `plugins/kbr-servicedesk/scripts/sdp_api.py`
- Test: `plugins/kbr-servicedesk/tests/test_sdp_api.py`

**Interfaces:**
- Produces: `sdp_api._data_para_ms(data_iso: str) -> str` — converte `"AAAA-MM-DD"` em milissegundos desde a época Unix, meia-noite UTC, como string. Usado pelas Tasks 2 e 4.

- [ ] **Step 1: Escrever o teste que falha**

Abra `plugins/kbr-servicedesk/tests/test_sdp_api.py` e acrescente, logo depois da classe `TesteConfig` (antes de `class TesteToken(BaseSDP):`):

```python
class TesteDataParaMs(BaseSDP):
    def test_meia_noite_utc(self):
        # Verificado ao vivo em 2026-09-14 (spec, seção 2.2): 1756684800000 ms é
        # 2025-09-01T00:00:00 UTC — a mesma forma usada na busca real contra o SDP.
        self.assertEqual(sdp_api._data_para_ms("2025-09-01"), "1756684800000")

    def test_um_mes_depois(self):
        self.assertEqual(sdp_api._data_para_ms("2025-10-01"), "1759276800000")
```

- [ ] **Step 2: Rodar e confirmar que falha**

```bash
cd plugins/kbr-servicedesk/tests && python -m unittest test_sdp_api.TesteDataParaMs -v
```
Esperado: `AttributeError: module 'sdp_api' has no attribute '_data_para_ms'`.

- [ ] **Step 3: Implementar**

Em `plugins/kbr-servicedesk/scripts/sdp_api.py`, no topo, troque:
```python
import argparse
import html as _html
import json
import re
import sys
import time
```
por:
```python
import argparse
import html as _html
import json
import re
import sys
import time
from datetime import datetime, timezone
```

Depois, logo após a definição de `STATUS_FINAIS` e seu comentário (antes de `def limpo(bruto: str, limite: int = 3000) -> str:`), acrescente:

```python
def _data_para_ms(data_iso: str) -> str:
    """Converte "AAAA-MM-DD" em milissegundos desde a época Unix, meia-noite UTC.

    É a mesma forma verificada ao vivo contra o SDP real da KINTO (spec de 2026-09-14,
    seção 2.2): um único campo de data em ms, como string. Não ajusta fuso horário local —
    o teste que fixou este comportamento usa os mesmos valores que a busca real confirmou.
    """
    momento = datetime.strptime(data_iso, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return str(int(momento.timestamp() * 1000))
```

- [ ] **Step 4: Rodar e confirmar que passa**

```bash
cd plugins/kbr-servicedesk/tests && python -m unittest test_sdp_api.TesteDataParaMs -v
```
Esperado: `OK` (2 testes).

- [ ] **Step 5: Commit**

```bash
git add plugins/kbr-servicedesk/scripts/sdp_api.py plugins/kbr-servicedesk/tests/test_sdp_api.py
git commit -m "$(cat <<'EOF'
feat(kbr-servicedesk): converter data ISO para ms UTC, base do filtro de período da query

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FxSq1YTHKimYYBJmKABcBa
EOF
)"
```

---

## Task 2: `_buscar_query` — busca sem filtro de técnico, com `between`, `--abertos`/`--status` e `fields_required`

**Files:**
- Modify: `plugins/kbr-servicedesk/scripts/sdp_api.py`
- Test: `plugins/kbr-servicedesk/tests/test_sdp_api.py`

**Interfaces:**
- Consumes: `_data_para_ms` (Task 1); `chamar`, `campo`, `_resultado`, `STATUS_FINAIS`, `TAMANHO_PAGINA`, `LIMITE_PAGINAS` (já existentes).
- Produces: `sdp_api.CAMPOS_QUERY: list[str]` (para `fields_required`); `sdp_api._buscar_query(token: str, de_ms: str | None, ate_ms: str | None, campo_data: str, status: str | None, abertos: bool) -> tuple[list[dict], bool]`. Usado pela Task 4 (`cmd_query`).

- [ ] **Step 1: Escrever os testes que falham**

No fim de `plugins/kbr-servicedesk/tests/test_sdp_api.py`, depois da fixture `CHAMADO_LISTA` e antes de `class BaseComando(BaseSDP):`, acrescente uma fixture mais completa (usada por esta task e pelas seguintes):

```python
CHAMADO_QUERY = {
    "requests": [
        {"display_id": "5001", "id": "173861000000000099",
         "subject": "Erro ao gerar nota fiscal",
         "status": {"name": "Closed"},
         "requester": {"name": "Ciclana", "email_id": "ciclana@kintomobility.com.br"},
         "technician": {"name": "Fulano de Tal"},
         "group": {"name": "Financeiro"},
         "category": {"name": "Sistemas"},
         "subcategory": {"name": "Faturamento"},
         "urgency": {"name": "Alta"},
         "priority": {"name": "Alta"},
         "created_time": {"display_value": "Sep 1, 2025 08:00 AM"},
         "resolved_time": {"display_value": "Sep 5, 2025 09:00 AM"}},
    ],
    "list_info": {"has_more_rows": False},
}
```

Depois, no fim do arquivo (após a última classe de teste existente), acrescente:

```python
class TesteBuscarQuery(BaseSDP):
    def test_periodo_usa_uma_unica_condicao_between(self):
        rede = self.rede(TOKEN_OK, CHAMADO_QUERY)
        sdp_api._buscar_query(
            "acc-1", sdp_api._data_para_ms("2026-09-01"), sdp_api._data_para_ms("2026-10-01"),
            "created_time", None, False)
        entrada = json.loads(urllib.parse.parse_qs(
            rede.chamadas[0]["url"].split("?", 1)[1])["input_data"][0])
        criterios = entrada["list_info"]["search_criteria"]
        condicoes = [c["condition"] for c in criterios]
        self.assertIn("between", condicoes)
        self.assertNotIn("greater than", condicoes)
        self.assertNotIn("less than", condicoes)

    def test_sem_periodo_nao_manda_criterio_de_data(self):
        rede = self.rede(TOKEN_OK, CHAMADO_QUERY)
        sdp_api._buscar_query("acc-1", None, None, "created_time", None, True)
        entrada = json.loads(urllib.parse.parse_qs(
            rede.chamadas[0]["url"].split("?", 1)[1])["input_data"][0])
        campos = [c["field"] for c in entrada["list_info"]["search_criteria"]]
        self.assertNotIn("created_time", campos)
        self.assertNotIn("resolved_time", campos)

    def test_campo_data_resolved_time(self):
        rede = self.rede(TOKEN_OK, CHAMADO_QUERY)
        sdp_api._buscar_query(
            "acc-1", sdp_api._data_para_ms("2026-09-01"), sdp_api._data_para_ms("2026-10-01"),
            "resolved_time", None, False)
        entrada = json.loads(urllib.parse.parse_qs(
            rede.chamadas[0]["url"].split("?", 1)[1])["input_data"][0])
        criterio = entrada["list_info"]["search_criteria"][0]
        self.assertEqual(criterio["field"], "resolved_time")

    def test_abertos_exclui_status_finais(self):
        rede = self.rede(TOKEN_OK, CHAMADO_QUERY)
        sdp_api._buscar_query("acc-1", None, None, "created_time", None, True)
        entrada = json.loads(urllib.parse.parse_qs(
            rede.chamadas[0]["url"].split("?", 1)[1])["input_data"][0])
        criterio = entrada["list_info"]["search_criteria"][0]
        self.assertEqual(criterio["condition"], "is not")
        self.assertEqual(criterio["values"], sdp_api.STATUS_FINAIS)

    def test_status_filtra_valor_exato(self):
        rede = self.rede(TOKEN_OK, CHAMADO_QUERY)
        sdp_api._buscar_query("acc-1", None, None, "created_time", "On Hold", False)
        entrada = json.loads(urllib.parse.parse_qs(
            rede.chamadas[0]["url"].split("?", 1)[1])["input_data"][0])
        criterio = entrada["list_info"]["search_criteria"][0]
        self.assertEqual(criterio["condition"], "is")
        self.assertEqual(criterio["value"], "On Hold")

    def test_sem_status_nem_abertos_nao_filtra_status(self):
        rede = self.rede(TOKEN_OK, CHAMADO_QUERY)
        sdp_api._buscar_query(
            "acc-1", sdp_api._data_para_ms("2026-09-01"), sdp_api._data_para_ms("2026-10-01"),
            "created_time", None, False)
        entrada = json.loads(urllib.parse.parse_qs(
            rede.chamadas[0]["url"].split("?", 1)[1])["input_data"][0])
        campos = [c["field"] for c in entrada["list_info"]["search_criteria"]]
        self.assertNotIn("status.name", campos)

    def test_nao_filtra_por_tecnico(self):
        rede = self.rede(TOKEN_OK, CHAMADO_QUERY)
        sdp_api._buscar_query(
            "acc-1", sdp_api._data_para_ms("2026-09-01"), sdp_api._data_para_ms("2026-10-01"),
            "created_time", None, False)
        entrada = json.loads(urllib.parse.parse_qs(
            rede.chamadas[0]["url"].split("?", 1)[1])["input_data"][0])
        campos = [c["field"] for c in entrada["list_info"]["search_criteria"]]
        self.assertNotIn("technician.name", campos)

    def test_fields_required_cobre_todas_as_colunas_do_csv(self):
        rede = self.rede(TOKEN_OK, CHAMADO_QUERY)
        sdp_api._buscar_query(
            "acc-1", sdp_api._data_para_ms("2026-09-01"), sdp_api._data_para_ms("2026-10-01"),
            "created_time", None, False)
        entrada = json.loads(urllib.parse.parse_qs(
            rede.chamadas[0]["url"].split("?", 1)[1])["input_data"][0])
        pedidos = set(entrada["list_info"]["fields_required"])
        # As colunas do CSV vêm de: display_id, subject, requester, technician, group,
        # category, subcategory, status, urgency, priority, created_time, resolved_time.
        necessarios = {"display_id", "subject", "requester", "technician", "group",
                       "category", "subcategory", "status", "urgency", "priority",
                       "created_time", "resolved_time"}
        self.assertTrue(necessarios.issubset(pedidos))

    def test_pagina_enquanto_houver_mais(self):
        pagina1 = {"requests": CHAMADO_QUERY["requests"], "list_info": {"has_more_rows": True}}
        pagina2 = {"requests": CHAMADO_QUERY["requests"], "list_info": {"has_more_rows": False}}
        self.rede(TOKEN_OK, pagina1, pagina2)
        chamados, truncado = sdp_api._buscar_query(
            "acc-1", sdp_api._data_para_ms("2026-09-01"), sdp_api._data_para_ms("2026-10-01"),
            "created_time", None, False)
        self.assertEqual(len(chamados), 2)
        self.assertFalse(truncado)

    def test_paginacao_tem_teto_e_sinaliza_truncamento(self):
        sempre_mais = {"requests": CHAMADO_QUERY["requests"], "list_info": {"has_more_rows": True}}
        rede = self.rede(*([sempre_mais] * sdp_api.LIMITE_PAGINAS))
        chamados, truncado = sdp_api._buscar_query(
            "acc-1", sdp_api._data_para_ms("2026-09-01"), sdp_api._data_para_ms("2026-10-01"),
            "created_time", None, False)
        self.assertTrue(truncado)
        self.assertEqual(len(chamados), sdp_api.LIMITE_PAGINAS)
        self.assertEqual(len(rede.chamadas), sdp_api.LIMITE_PAGINAS)
```

Note que `_buscar_query` recebe o `token` diretamente (`"acc-1"`) em vez de passar por `access_token()` — por isso não há a chamada extra de token nas contagens de `rede.chamadas` aqui, diferente de `TesteListar` que passa por `cmd_listar` (comando completo).

- [ ] **Step 2: Rodar e confirmar que falha**

```bash
cd plugins/kbr-servicedesk/tests && python -m unittest test_sdp_api.TesteBuscarQuery -v
```
Esperado: `AttributeError: module 'sdp_api' has no attribute '_buscar_query'` (ou `CAMPOS_QUERY`).

- [ ] **Step 3: Implementar**

Em `plugins/kbr-servicedesk/scripts/sdp_api.py`, logo depois de `_buscar_chamados` (antes do comentário `# --------------------------------------------------------------------------- comandos`), acrescente:

```python
CAMPOS_QUERY = ["id", "display_id", "subject", "status", "requester", "technician",
               "group", "category", "subcategory", "urgency", "priority",
               "created_time", "resolved_time"]


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
```

- [ ] **Step 4: Rodar e confirmar que passa**

```bash
cd plugins/kbr-servicedesk/tests && python -m unittest test_sdp_api.TesteBuscarQuery -v
```
Esperado: `OK` (9 testes).

- [ ] **Step 5: Commit**

```bash
git add plugins/kbr-servicedesk/scripts/sdp_api.py plugins/kbr-servicedesk/tests/test_sdp_api.py
git commit -m "$(cat <<'EOF'
feat(kbr-servicedesk): buscar chamados de toda a operação para a query, sem filtro de técnico

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FxSq1YTHKimYYBJmKABcBa
EOF
)"
```

---

## Task 3: `_resumir_query` e `_escrever_csv` — colunas do CSV e o arquivo

**Files:**
- Modify: `plugins/kbr-servicedesk/scripts/sdp_api.py`
- Test: `plugins/kbr-servicedesk/tests/test_sdp_api.py`

**Interfaces:**
- Consumes: `campo` (já existente); `CHAMADO_QUERY` (fixture da Task 2).
- Produces: `sdp_api.COLUNAS_QUERY: list[str]`; `sdp_api._resumir_query(bruto: dict) -> dict`; `sdp_api._escrever_csv(caminho: Path, chamados: list[dict]) -> None`. Usados pela Task 4 (`cmd_query`).

- [ ] **Step 1: Escrever os testes que falham**

No fim de `plugins/kbr-servicedesk/tests/test_sdp_api.py`, acrescente:

```python
class TesteResumirQuery(unittest.TestCase):
    def test_mapeia_todas_as_colunas(self):
        resumo = sdp_api._resumir_query(CHAMADO_QUERY["requests"][0])
        self.assertEqual(resumo, {
            "numero": "5001",
            "assunto": "Erro ao gerar nota fiscal",
            "solicitante": "Ciclana",
            "tecnico": "Fulano de Tal",
            "grupo": "Financeiro",
            "categoria": "Sistemas",
            "subcategoria": "Faturamento",
            "status": "Closed",
            "urgencia": "Alta",
            "prioridade": "Alta",
            "criado_em": "Sep 1, 2025 08:00 AM",
            "resolvido_em": "Sep 5, 2025 09:00 AM",
        })

    def test_nao_expoe_id_interno(self):
        resumo = sdp_api._resumir_query(CHAMADO_QUERY["requests"][0])
        self.assertNotIn("id", resumo)
        self.assertNotIn("173861000000000099", json.dumps(resumo))

    def test_campo_ausente_vira_none_sem_estourar(self):
        # priority ausente é um caso real, visto ao vivo (spec, seção 2.4): não pode
        # estourar KeyError/AttributeError, tem que virar coluna vazia no CSV.
        bruto = {k: v for k, v in CHAMADO_QUERY["requests"][0].items() if k != "priority"}
        resumo = sdp_api._resumir_query(bruto)
        self.assertIsNone(resumo["prioridade"])


class TesteEscreverCsv(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_escreve_cabecalho_e_uma_linha_por_chamado(self):
        caminho = Path(self.tmp.name) / "saida.csv"
        sdp_api._escrever_csv(caminho, CHAMADO_QUERY["requests"])
        with caminho.open(encoding="utf-8", newline="") as arquivo:
            leitor = csv.reader(arquivo)
            linhas = list(leitor)
        self.assertEqual(linhas[0], sdp_api.COLUNAS_QUERY)
        self.assertEqual(len(linhas), 2)
        self.assertEqual(linhas[1][0], "5001")

    def test_colunas_na_ordem_da_spec(self):
        self.assertEqual(sdp_api.COLUNAS_QUERY, [
            "numero", "assunto", "solicitante", "tecnico", "grupo", "categoria",
            "subcategoria", "status", "urgencia", "prioridade", "criado_em", "resolvido_em"])

    def test_id_interno_nunca_aparece_no_arquivo(self):
        caminho = Path(self.tmp.name) / "saida.csv"
        sdp_api._escrever_csv(caminho, CHAMADO_QUERY["requests"])
        conteudo = caminho.read_text(encoding="utf-8")
        self.assertNotIn("173861000000000099", conteudo)

    def test_cria_a_pasta_se_nao_existir(self):
        caminho = Path(self.tmp.name) / "subpasta" / "saida.csv"
        sdp_api._escrever_csv(caminho, CHAMADO_QUERY["requests"])
        self.assertTrue(caminho.is_file())
```

Acrescente `import csv` ao topo de `test_sdp_api.py` (junto aos outros imports, em ordem alfabética):
```python
import contextlib
import csv
import io
```

- [ ] **Step 2: Rodar e confirmar que falha**

```bash
cd plugins/kbr-servicedesk/tests && python -m unittest test_sdp_api.TesteResumirQuery test_sdp_api.TesteEscreverCsv -v
```
Esperado: `AttributeError: module 'sdp_api' has no attribute '_resumir_query'` (ou `COLUNAS_QUERY`/`_escrever_csv`).

- [ ] **Step 3: Implementar**

Em `plugins/kbr-servicedesk/scripts/sdp_api.py`, acrescente `import csv` ao topo (ordem alfabética, antes de `html`):
```python
import argparse
import csv
import html as _html
import json
```

Logo depois de `CAMPOS_QUERY` (definido na Task 2, antes de `_buscar_query`), acrescente:

```python
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
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", newline="", encoding="utf-8") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=COLUNAS_QUERY)
        escritor.writeheader()
        for bruto in chamados:
            escritor.writerow(_resumir_query(bruto))
```

- [ ] **Step 4: Rodar e confirmar que passa**

```bash
cd plugins/kbr-servicedesk/tests && python -m unittest test_sdp_api.TesteResumirQuery test_sdp_api.TesteEscreverCsv -v
```
Esperado: `OK` (7 testes).

- [ ] **Step 5: Commit**

```bash
git add plugins/kbr-servicedesk/scripts/sdp_api.py plugins/kbr-servicedesk/tests/test_sdp_api.py
git commit -m "$(cat <<'EOF'
feat(kbr-servicedesk): escrever o CSV da query com as 12 colunas da spec, sem id interno

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FxSq1YTHKimYYBJmKABcBa
EOF
)"
```

---

## Task 4: `cmd_query` — o comando completo, ligado ao `argparse`

**Files:**
- Modify: `plugins/kbr-servicedesk/scripts/sdp_api.py`
- Test: `plugins/kbr-servicedesk/tests/test_sdp_api.py`

**Interfaces:**
- Consumes: `access_token`, `_data_para_ms` (Task 1), `_buscar_query` (Task 2), `_escrever_csv`, `COLUNAS_QUERY` (Task 3), `_imprimir`, `ErroSDP`.
- Produces: `sdp_api._arquivo_padrao(de: str | None, ate: str | None) -> Path`; `sdp_api.cmd_query(args) -> int`; subcomando `query` em `construir_parser()`; entrada `"query": cmd_query` em `COMANDOS`.

- [ ] **Step 1: Escrever os testes que falham**

No fim de `plugins/kbr-servicedesk/tests/test_sdp_api.py`, acrescente:

```python
class TesteArquivoPadrao(unittest.TestCase):
    def test_com_periodo(self):
        caminho = sdp_api._arquivo_padrao("2026-09-01", "2026-10-01")
        self.assertEqual(caminho.name, "chamados_2026-09-01_a_2026-10-01.csv")

    def test_sem_periodo(self):
        caminho = sdp_api._arquivo_padrao(None, None)
        self.assertEqual(caminho.name, "chamados.csv")


class TesteCmdQuery(BaseComando):
    def test_periodo_grava_csv_e_devolve_json(self):
        self.rede(TOKEN_OK, CHAMADO_QUERY)
        destino = Path(self.tmp.name) / "saida.csv"
        codigo, saida = self.executar(
            "query", "--de", "2026-09-01", "--ate", "2026-10-01", "--arquivo", str(destino))
        self.assertEqual(codigo, 0)
        dados = self.json_da_saida(saida)
        self.assertEqual(dados["arquivo"], str(destino.resolve()))
        self.assertEqual(dados["linhas"], 1)
        self.assertFalse(dados["truncado"])
        self.assertTrue(destino.is_file())

    def test_de_sem_ate_e_erro(self):
        codigo, saida = self.executar("query", "--de", "2026-09-01")
        self.assertEqual(codigo, 1)
        erro = self.json_da_saida(saida)["erro"]
        self.assertIn("--de", erro)
        self.assertIn("--ate", erro)

    def test_ate_sem_de_e_erro(self):
        codigo, saida = self.executar("query", "--ate", "2026-10-01")
        self.assertEqual(codigo, 1)

    def test_abertos_e_status_sao_mutuamente_exclusivos(self):
        captura = io.StringIO()
        with contextlib.redirect_stderr(captura), self.assertRaises(SystemExit) as ctx:
            sdp_api.main(["query", "--abertos", "--status", "On Hold"])
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("not allowed with argument", captura.getvalue())

    def test_sem_periodo_nem_abertos_nem_status_funciona(self):
        self.rede(TOKEN_OK, CHAMADO_QUERY)
        destino = Path(self.tmp.name) / "saida.csv"
        codigo, saida = self.executar("query", "--arquivo", str(destino))
        self.assertEqual(codigo, 0)
        self.assertEqual(self.json_da_saida(saida)["linhas"], 1)

    def test_nenhuma_chamada_de_escrita_e_alcancavel(self):
        destino = Path(self.tmp.name) / "saida.csv"
        rede = self.rede(TOKEN_OK, CHAMADO_QUERY)
        self.executar("query", "--de", "2026-09-01", "--ate", "2026-10-01",
                      "--arquivo", str(destino))
        metodos = {chamada["metodo"] for chamada in rede.chamadas}
        self.assertEqual(metodos, {"GET"})

    def test_nao_aceita_confirmar(self):
        captura = io.StringIO()
        with contextlib.redirect_stderr(captura), self.assertRaises(SystemExit) as ctx:
            sdp_api.main(["query", "--confirmar"])
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("unrecognized arguments", captura.getvalue())
```

- [ ] **Step 2: Rodar e confirmar que falha**

```bash
cd plugins/kbr-servicedesk/tests && python -m unittest test_sdp_api.TesteArquivoPadrao test_sdp_api.TesteCmdQuery -v
```
Esperado: falhas — `argparse.ArgumentError` (subcomando `query` inexistente) ou `AttributeError` para `_arquivo_padrao`.

- [ ] **Step 3: Implementar**

Em `plugins/kbr-servicedesk/scripts/sdp_api.py`, logo depois de `_escrever_csv` (Task 3, ainda na seção de ajudantes, antes de `# --- comandos`), acrescente:

```python
def _arquivo_padrao(de: str | None, ate: str | None) -> Path:
    if de and ate:
        return Path(f"chamados_{de}_a_{ate}.csv")
    return Path("chamados.csv")
```

Depois, logo após `cmd_escopos` (o último comando existente, antes de `def _imprimir`), acrescente:

```python
def cmd_query(args) -> int:
    de, ate = args.de, args.ate
    if bool(de) != bool(ate):
        raise ErroSDP('Informe "--de" e "--ate" juntos, ou nenhum dos dois.')
    token = access_token()
    de_ms = _data_para_ms(de) if de else None
    ate_ms = _data_para_ms(ate) if ate else None
    brutos, truncado = _buscar_query(
        token, de_ms, ate_ms, args.campo_data, args.status, args.abertos)
    caminho = Path(args.arquivo) if args.arquivo else _arquivo_padrao(de, ate)
    _escrever_csv(caminho, brutos)
    _imprimir({"arquivo": str(caminho.resolve()), "linhas": len(brutos),
               "truncado": truncado})
    return 0
```

Em `construir_parser()`, logo depois de:
```python
    sub.add_parser("autorizar", help="troca o código de autorização por acesso permanente")
    sub.add_parser("escopos", help="mostra os escopos a marcar no console da Zoho")

    return parser
```
troque por (acrescentando o subparser `query` antes do `return parser`):
```python
    sub.add_parser("autorizar", help="troca o código de autorização por acesso permanente")
    sub.add_parser("escopos", help="mostra os escopos a marcar no console da Zoho")

    query = sub.add_parser(
        "query", help="extrai chamados de toda a operação para CSV (sem filtro de técnico)")
    query.add_argument("--de", default=None, help="data inicial, AAAA-MM-DD (inclusiva)")
    query.add_argument("--ate", default=None, help="data final, AAAA-MM-DD (exclusiva)")
    query.add_argument("--campo-data", dest="campo_data", default="created_time",
                       choices=["created_time", "resolved_time"])
    grupo_status = query.add_mutually_exclusive_group()
    grupo_status.add_argument("--status", default=None, help="filtra por um status exato")
    grupo_status.add_argument("--abertos", action="store_true",
                              help="só os chamados ainda não finalizados")
    query.add_argument("--arquivo", default=None, help="caminho do CSV de saída")

    return parser
```

Em `COMANDOS`, troque:
```python
COMANDOS = {"testar": cmd_testar, "listar": cmd_listar, "detalhe": cmd_detalhe,
            "nota": cmd_nota, "status": cmd_status, "resolver": cmd_resolver,
            "autorizar": cmd_autorizar, "escopos": cmd_escopos}
```
por:
```python
COMANDOS = {"testar": cmd_testar, "listar": cmd_listar, "detalhe": cmd_detalhe,
            "nota": cmd_nota, "status": cmd_status, "resolver": cmd_resolver,
            "autorizar": cmd_autorizar, "escopos": cmd_escopos, "query": cmd_query}
```

- [ ] **Step 4: Rodar e confirmar que passa**

```bash
cd plugins/kbr-servicedesk/tests && python -m unittest test_sdp_api.TesteArquivoPadrao test_sdp_api.TesteCmdQuery -v
```
Esperado: `OK` (9 testes).

Depois rode a suíte inteira do plugin para garantir que nada regrediu:
```bash
cd plugins/kbr-servicedesk/tests && python -m unittest discover -s . -t . -p test_sdp_api.py -v 2>&1 | tail -5
```
Esperado: `OK`.

- [ ] **Step 5: Commit**

```bash
git add plugins/kbr-servicedesk/scripts/sdp_api.py plugins/kbr-servicedesk/tests/test_sdp_api.py
git commit -m "$(cat <<'EOF'
feat(kbr-servicedesk): ligar o subcomando query ao argparse e ao COMANDOS

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FxSq1YTHKimYYBJmKABcBa
EOF
)"
```

---

## Task 5: a skill `/kbr-servicedesk:query`

**Files:**
- Create: `plugins/kbr-servicedesk/skills/query/SKILL.md`

**Interfaces:**
- Consumes: o subcomando `sdp_api.py query` (Task 4) via `${CLAUDE_PLUGIN_ROOT}/scripts/sdp_api.py`.

Este arquivo não tem teste automatizado (é instrução para o modelo, não código) — a verificação é o `claude plugin validate --strict` (Step 2) e leitura própria (Step 3).

- [ ] **Step 1: Escrever `plugins/kbr-servicedesk/skills/query/SKILL.md`**

```markdown
---
name: query
description: Extrai chamados de toda a operação do ServiceDesk Plus da KINTO — todos os técnicos, não só os seus — filtrados por período, para um arquivo CSV local que abre no Excel. Diferente da skill sdp (que responde perguntas rápidas sobre os SEUS chamados em texto), esta gera um arquivo para quem vai analisar fora do chat. Use quando o usuário pedir "exportar chamados", "planilha de chamados", "relatório de chamados em CSV", "extrair dados do ServiceDesk", "dados para o dashboard do ServiceDesk", "quero uma listagem de todos os chamados abertos em 09/2026", "chamados de toda a operação", ou invocar /kbr-servicedesk:query.
---

# Query — extração de dados do ServiceDesk KINTO

Você gera um **arquivo**, não uma resposta de chat. O escopo é **toda a operação** — todos os
técnicos, não só quem está conversando com você.

## Regras duras (não violar)

- 📖 **Sempre leitura.** Este comando nunca grava no ServiceDesk — não existe flag de
  confirmação porque não existe nada a confirmar.
- 🚫 **Nunca ação em massa.** Se o pedido envolver mudar algo ("fecha todos os de setembro",
  "atualiza o status de todos os abertos"), explique que aqui só se **extrai** dado — mudar
  chamado é sempre pela skill `sdp`, opções 3/4/5, um de cada vez, com confirmação. Ofereça
  levar a pessoa para lá.
- 📂 **Sempre diga o caminho absoluto do arquivo**, no fim da resposta — é o campo `arquivo`
  da saída do comando.
- ⚠️ **Se vier `truncado: true`**, avise antes de declarar a extração completa: a busca bateu
  no teto interno de 10 mil chamados. Diga que o arquivo tem pelo menos as primeiras linhas
  coletadas, não a base inteira do período.
- 🔒 **Segredo nunca no chat.** Se faltar credencial, leve para a skill `sdp`, opção 6.
- 🇧🇷 Tudo em PT-BR, com acentuação correta.

## Como chamar o script

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/sdp_api.py" query [--de AAAA-MM-DD --ate AAAA-MM-DD] [--campo-data created_time|resolved_time] [--status "<nome exato>" | --abertos] [--arquivo <caminho.csv>]
```

- `--de`/`--ate` vêm **juntos ou nenhum dos dois**. `--ate` é **exclusivo** — o dia seguinte
  ao último dia desejado. Sem os dois, a busca não filtra por data (é o caso da opção 5).
- `--campo-data` escolhe se o período é sobre quando o chamado foi **criado** (padrão) ou
  **resolvido**.
- `--status` e `--abertos` são mutuamente exclusivos: `--status "On Hold"` filtra por um
  status exato; `--abertos` traz tudo que ainda não é Resolved/Closed/Canceled. Sem nenhum
  dos dois, não filtra por status — traz tudo, inclusive já finalizado (é o padrão certo para
  dado histórico).
- `--arquivo` é opcional. Sem ele, o nome é `chamados_<de>_a_<ate>.csv` (ou `chamados.csv`
  sem período), gravado na pasta atual.

A saída é sempre JSON: `{"arquivo": "...", "linhas": N, "truncado": bool}`. Se vier
`{"erro": "..."}`, mostre o texto como está — já foi escrito em PT-BR — e siga a mesma tabela
de diagnóstico da skill `sdp` (menciona `/kbr-servicedesk:configurar` quando é credencial).

## Antes de calcular qualquer período: descubra a data de hoje

Nunca confie na sua própria noção de "hoje" para calcular "este mês"/"mês passado" — rode:

```bash
python -c "from datetime import date; print(date.today().isoformat())"
```

## O menu

```
🧮 QUERY — Extração de dados do ServiceDesk
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📅 1. Chamados criados este mês
📅 2. Chamados criados no mês passado
✅ 3. Chamados resolvidos este mês
✅ 4. Chamados resolvidos no mês passado
📂 5. Todos os chamados ainda abertos (toda a operação)
✍️ 6. Período personalizado — descreva o que você quer

🚪 0. Sair
```

| Opção | Comando |
|---|---|
| 1 | `query --de <dia 01 do mês corrente> --ate <dia 01 do mês seguinte>` |
| 2 | `query --de <dia 01 do mês anterior> --ate <dia 01 do mês corrente>` |
| 3 | `query --campo-data resolved_time --de <dia 01 do mês corrente> --ate <dia 01 do mês seguinte>` |
| 4 | `query --campo-data resolved_time --de <dia 01 do mês anterior> --ate <dia 01 do mês corrente>` |
| 5 | `query --abertos` |
| 6 | interpretado da fala — veja abaixo |

**Mês corrente/anterior:** a partir da data de hoje (seção acima). "Mês corrente" vai do dia
01 do mês de hoje até o dia 01 do mês seguinte (exclusivo). "Mês anterior" vai do dia 01 do mês
passado até o dia 01 do mês de hoje. Exemplo: hoje `2026-09-14` → este mês é
`--de 2026-09-01 --ate 2026-10-01`; mês passado é `--de 2026-08-01 --ate 2026-09-01`.

## Opção 6 — período personalizado

Aceita frases como "chamados abertos em 09/2026", "resolvidos entre 1º e 15 de agosto",
"tudo desde julho até hoje". Regras:

- Converta para `--de`/`--ate` em ISO, com `--ate` sempre **um dia depois** do último dia
  desejado (se a pessoa disse "até 15 de agosto", `--ate` é `2026-08-16`).
- Se a frase falar em "resolvido"/"fechado"/"concluído", use `--campo-data resolved_time`;
  se falar em "criado"/"aberto"/"registrado" (ou não especificar), use o padrão
  (`created_time`).
- Se a frase pedir só os que ainda estão em aberto, use `--abertos` em vez de um período —
  ou combine os dois se a pessoa quiser "abertos criados em setembro", por exemplo.
- **Nunca invente um filtro que a pessoa não pediu.** Se a frase for ambígua sobre o período
  ou o campo de data, pergunte antes de rodar — não adivinhe.

## Depois de gerar o arquivo

Diga, numa frase: quantas linhas (`linhas`), o caminho absoluto (`arquivo`), e se veio
`truncado: true`, o aviso de que a lista pode estar incompleta. Pergunte se a pessoa quer
gerar outra extração (volte ao menu) ou já terminou.
```

- [ ] **Step 2: Validar a skill**

```bash
claude plugin validate --strict plugins/kbr-servicedesk
```
Esperado: sem erros. Se o parser do YAML reclamar da `description`, confira se não há `: `
(dois-pontos seguido de espaço) fora de travessão dentro do valor.

- [ ] **Step 3: Commit**

```bash
git add plugins/kbr-servicedesk/skills/query/SKILL.md
git commit -m "$(cat <<'EOF'
feat(kbr-servicedesk): nova skill query — menu de extrações prontas e período personalizado

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FxSq1YTHKimYYBJmKABcBa
EOF
)"
```

---

## Task 6: README, versão e publicação

**Files:**
- Modify: `plugins/kbr-servicedesk/README.md`
- Modify: `plugins/kbr-servicedesk/.claude-plugin/plugin.json`

- [ ] **Step 1: Atualizar o README**

Em `plugins/kbr-servicedesk/README.md`, na seção `## Skills`, troque:
```markdown
## Skills

- **`/kbr-servicedesk:sdp`** — o painel: lista seus chamados, mostra detalhe, adiciona nota,
  muda status e resolve. Nada é gravado sem você confirmar.
- **`/kbr-servicedesk:configurar`** — o passo a passo que te ensina a criar as próprias chaves
  de acesso, em 8 etapas. Feito para quem nunca ouviu falar de OAuth. Tem também uma visão
  geral, se você quiser só entender o que está envolvido antes de começar.
```
por:
```markdown
## Skills

- **`/kbr-servicedesk:sdp`** — o painel: lista seus chamados, mostra detalhe, adiciona nota,
  muda status e resolve. Nada é gravado sem você confirmar.
- **`/kbr-servicedesk:query`** — extrai chamados de **toda a operação** (todos os técnicos)
  filtrados por período para um CSV local, com um menu de extrações prontas e período
  personalizado. Sempre leitura — nunca grava no ServiceDesk.
- **`/kbr-servicedesk:configurar`** — o passo a passo que te ensina a criar as próprias chaves
  de acesso, em 19 passos pequenos. Feito para quem nunca ouviu falar de OAuth. Tem também uma
  visão geral, se você quiser só entender o que está envolvido antes de começar.
```

(A correção de "8 etapas" para "19 passos pequenos" acompanha a mudança porque a mesma linha
está sendo tocada — o wizard já foi reescrito para 19 passos numa tarefa anterior desta sessão
e o README ficou desatualizado; não abre uma tarefa própria por ser uma linha só, no arquivo já
em edição.)

- [ ] **Step 2: Subir a versão do plugin**

Em `plugins/kbr-servicedesk/.claude-plugin/plugin.json`, troque `"version": "0.3.1"` por
`"version": "0.4.0"` (minor — funcionalidade nova, compatível com o que já existe).

- [ ] **Step 3: Rodar a suíte completa e o validador**

```bash
python scripts/testar.py
python scripts/validar.py
```
Esperado: `OK` nos dois.

- [ ] **Step 4: Commit**

```bash
git add plugins/kbr-servicedesk/README.md plugins/kbr-servicedesk/.claude-plugin/plugin.json
git commit -m "$(cat <<'EOF'
chore(kbr-servicedesk): 0.4.0 — documenta a skill query e corrige a contagem de passos do wizard

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FxSq1YTHKimYYBJmKABcBa
EOF
)"
```

- [ ] **Step 5: Criar e publicar a tag**

```bash
python scripts/criar_tag.py kbr-servicedesk --push
```
Esperado: `tag criada: kbr-servicedesk--v0.4.0` e confirmação do push. **Confirme com o usuário
antes deste step** — publicar no marketplace é uma ação visível para toda a organização.

---

## Self-Review (já aplicado ao escrever este plano)

1. **Cobertura da spec:** seções 1–5 cobertas pelas Tasks 1–5; seção 6 (testes) coberta por
   cada task (between-only, campo-data, fields_required, status com/sem filtro, CSV, teto de
   10 mil, id interno nunca exposto, nenhuma chamada de escrita alcançável); seção 7 (fora de
   escopo) não gerou nenhuma task, de propósito.
2. **Placeholders:** nenhum "TBD"/"depois" — todo step tem código completo.
3. **Consistência de tipos:** `_buscar_query` devolve `tuple[list[dict], bool]` igual a
   `_buscar_chamados`; `_resumir_query` e `COLUNAS_QUERY` usam exatamente as mesmas 12 chaves,
   na mesma ordem, checado por `test_colunas_na_ordem_da_spec` e `test_mapeia_todas_as_colunas`;
   `cmd_query` usa os mesmos nomes de atributo (`args.de`, `args.ate`, `args.campo_data`,
   `args.status`, `args.abertos`, `args.arquivo`) definidos no `add_parser` da Task 4.
4. **Os dois ajustes sobre a spec** (seção "Nota" no topo deste plano) estão implementados e
   testados em todas as tasks que tocam `--de`/`--ate` e `--status`/`--abertos`.
