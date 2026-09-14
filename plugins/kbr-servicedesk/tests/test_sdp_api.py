# -*- coding: utf-8 -*-
"""Testes do acesso à API do ServiceDesk Plus."""
import contextlib
import io
import json
import os
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.parse
from pathlib import Path
from types import SimpleNamespace

RAIZ_PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ_PLUGIN / "scripts"))
import kbr_secrets  # noqa: E402
import sdp_api  # noqa: E402


class OpFalsoSDP:
    """Duplo do 1Password CLI (mesmo padrão da Task 2), com outro nome para não
    depender do arquivo de teste do kbr-core."""

    def __init__(self, saida="", erro="", codigo=0):
        self.saida, self.erro, self.codigo = saida, erro, codigo
        self.chamadas = []

    def __call__(self, argumentos, **kwargs):
        self.chamadas.append(list(argumentos))
        return SimpleNamespace(returncode=self.codigo, stdout=self.saida, stderr=self.erro)


class RespostaFalsa(io.BytesIO):
    def __init__(self, corpo, status=200):
        super().__init__(json.dumps(corpo).encode("utf-8"))
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class RespostaBruta(io.BytesIO):
    """Como RespostaFalsa, mas grava bytes crus (não JSON) — simula um proxy ou portal
    cativo respondendo 200 no lugar do ServiceDesk."""

    def __init__(self, bruto: bytes, status=200):
        super().__init__(bruto)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class RedeFalsa:
    """Substitui sdp_api._abrir. Devolve as respostas na ordem da fila.

    Um item `bytes`/`bytearray` da fila vira uma resposta com corpo cru (não JSON);
    qualquer outro item (dict) vira o de sempre, serializado em JSON.
    """

    def __init__(self, *respostas):
        self.fila = list(respostas)
        self.chamadas = []

    def __call__(self, requisicao, timeout=None):
        self.chamadas.append({
            "url": requisicao.full_url,
            "metodo": requisicao.get_method(),
            "corpo": (requisicao.data or b"").decode("utf-8"),
            "cabecalhos": dict(requisicao.header_items()),
        })
        proxima = self.fila.pop(0)
        if isinstance(proxima, Exception):
            raise proxima
        if isinstance(proxima, (bytes, bytearray)):
            return RespostaBruta(bytes(proxima))
        return RespostaFalsa(proxima)


class BaseSDP(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name) / ".kbr"
        (self.base / "cache").mkdir(parents=True)
        self._env = dict(os.environ)
        os.environ["KBR_HOME"] = str(self.base)
        kbr_secrets._cache_op.clear()
        kbr_secrets.caminho_arquivo().write_text(
            "SDP_CLIENT_ID=cid\nSDP_CLIENT_SECRET=csec\nSDP_REFRESH_TOKEN=rtok\n",
            encoding="utf-8")
        sdp_api.gravar_config({"tecnico_nome": "Fulano de Tal",
                               "tecnico_email": "fulano@kintomobility.com.br"})
        self._abrir_original = sdp_api._abrir
        self._rodar_op_original = kbr_secrets._rodar_op

    def tearDown(self):
        sdp_api._abrir = self._abrir_original
        kbr_secrets._rodar_op = self._rodar_op_original
        os.environ.clear()
        os.environ.update(self._env)
        self.tmp.cleanup()

    def rede(self, *respostas):
        falsa = RedeFalsa(*respostas)
        sdp_api._abrir = falsa
        return falsa


class TesteConfig(BaseSDP):
    def test_preenche_os_padroes(self):
        config = sdp_api.ler_config()
        self.assertEqual(config["data_center"], "us")
        self.assertIn("sdpondemand.manageengine.com", config["api_base"])
        self.assertIn("accounts.zoho.com", config["token_url"])

    def test_preserva_o_que_ja_estava(self):
        self.assertEqual(sdp_api.ler_config()["tecnico_nome"], "Fulano de Tal")

    def test_nao_mexe_em_outras_chaves_do_config(self):
        caminho = kbr_secrets.caminho_config()
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        dados["outro_plugin"] = {"x": 1}
        caminho.write_text(json.dumps(dados), encoding="utf-8")
        sdp_api.gravar_config({"tecnico_nome": "Outro"})
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        self.assertEqual(dados["outro_plugin"], {"x": 1})


class TesteDataParaMs(BaseSDP):
    def test_meia_noite_utc(self):
        # Verificado ao vivo em 2026-09-14 (spec, seção 2.2): 1756684800000 ms é
        # 2025-09-01T00:00:00 UTC — a mesma forma usada na busca real contra o SDP.
        self.assertEqual(sdp_api._data_para_ms("2025-09-01"), "1756684800000")

    def test_um_mes_depois(self):
        self.assertEqual(sdp_api._data_para_ms("2025-10-01"), "1759276800000")


class TesteToken(BaseSDP):
    def test_troca_refresh_por_access(self):
        rede = self.rede({"access_token": "acc-1", "expires_in": 3600})
        self.assertEqual(sdp_api.access_token(), "acc-1")
        chamada = rede.chamadas[0]
        self.assertEqual(chamada["metodo"], "POST")
        self.assertIn("accounts.zoho.com", chamada["url"])
        self.assertIn("grant_type=refresh_token", chamada["corpo"])
        self.assertIn("rtok", chamada["corpo"])

    def test_reusa_o_token_em_cache(self):
        rede = self.rede({"access_token": "acc-1", "expires_in": 3600})
        sdp_api.access_token()
        sdp_api.access_token()
        self.assertEqual(len(rede.chamadas), 1)

    def test_renova_quando_esta_perto_de_vencer(self):
        caminho = kbr_secrets.caminho_cache() / "sdp_access_token.json"
        caminho.write_text(json.dumps({"access_token": "velho",
                                       "expira_em": time.time() + 60}), encoding="utf-8")
        self.rede({"access_token": "novo", "expires_in": 3600})
        self.assertEqual(sdp_api.access_token(), "novo")

    def test_cache_nao_guarda_refresh_token(self):
        self.rede({"access_token": "acc-1", "expires_in": 3600})
        sdp_api.access_token()
        bruto = (kbr_secrets.caminho_cache() / "sdp_access_token.json").read_text(
            encoding="utf-8")
        self.assertNotIn("rtok", bruto)

    def test_segredo_ausente_vira_mensagem_do_wizard(self):
        kbr_secrets.caminho_arquivo().write_text("SDP_CLIENT_ID=\n", encoding="utf-8")
        with self.assertRaises(sdp_api.ErroSDP) as caso:
            sdp_api.access_token()
        self.assertIn("configurar", str(caso.exception))

    def test_cache_com_expira_em_nao_numerico_busca_token_novo(self):
        # expira_em não é número (ex.: arquivo corrompido) — cache vale como ausente.
        caminho = kbr_secrets.caminho_cache() / "sdp_access_token.json"
        caminho.write_text(json.dumps({"access_token": "velho", "expira_em": "abc"}),
                           encoding="utf-8")
        self.rede({"access_token": "novo", "expires_in": 3600})
        self.assertEqual(sdp_api.access_token(), "novo")

    def test_cache_que_e_uma_lista_busca_token_novo(self):
        # JSON válido, mas não é objeto — cache vale como ausente.
        caminho = kbr_secrets.caminho_cache() / "sdp_access_token.json"
        caminho.write_text(json.dumps(["nao", "e", "um", "dict"]), encoding="utf-8")
        self.rede({"access_token": "novo", "expires_in": 3600})
        self.assertEqual(sdp_api.access_token(), "novo")

    def test_cache_que_e_uma_string_crua_busca_token_novo(self):
        # JSON válido, mas é uma string solta — cache vale como ausente.
        caminho = kbr_secrets.caminho_cache() / "sdp_access_token.json"
        caminho.write_text(json.dumps("apenas uma string"), encoding="utf-8")
        self.rede({"access_token": "novo", "expires_in": 3600})
        self.assertEqual(sdp_api.access_token(), "novo")


class TesteErros(unittest.TestCase):
    def test_codigo_expirado(self):
        texto = sdp_api.traduzir("zoho", {"error": "invalid_code"})
        self.assertIn("10 minutos", texto)

    def test_cliente_invalido(self):
        texto = sdp_api.traduzir("zoho", {"error": "invalid_client"})
        self.assertIn("Client ID", texto)

    def test_cliente_invalido_menciona_o_console_americano(self):
        texto = sdp_api.traduzir("zoho", {"error": "invalid_client"})
        self.assertIn("api-console.zoho.com", texto)

    def test_escopo_faltando(self):
        texto = sdp_api.traduzir("zoho", {"error": "invalid_scope"})
        self.assertIn("escopo", texto.lower())

    def test_http_401(self):
        texto = sdp_api.traduzir("sdp", {}, http=401)
        self.assertIn("revogado", texto.lower())

    def test_http_403(self):
        texto = sdp_api.traduzir("sdp", {}, http=403)
        self.assertIn("permissão", texto.lower())

    def test_rede(self):
        texto = sdp_api.traduzir("rede", {})
        self.assertIn("conexão", texto.lower())

    def test_erro_desconhecido_nao_quebra(self):
        texto = sdp_api.traduzir("sdp", {"response_status": {"messages": [
            {"message": "algo inesperado"}]}}, http=400)
        self.assertIn("algo inesperado", texto)

    def test_nenhuma_mensagem_vaza_token(self):
        texto = sdp_api.traduzir("zoho", {"error": "invalid_client",
                                          "access_token": "NAO-DEVE-APARECER"})
        self.assertNotIn("NAO-DEVE-APARECER", texto)

    def test_response_status_com_tipo_inesperado_nao_quebra(self):
        # response_status não é dict: não pode lançar AttributeError nem ecoar o valor bruto.
        texto = sdp_api.traduzir("sdp", {"response_status": "NAO-DEVE-APARECER"}, http=400)
        self.assertIsInstance(texto, str)
        self.assertTrue(texto)
        self.assertNotIn("NAO-DEVE-APARECER", texto)

    def test_messages_com_item_que_nao_e_dict_nao_quebra(self):
        # um item da lista messages não é dict: não pode lançar AttributeError nem ecoar o
        # valor bruto do item.
        texto = sdp_api.traduzir(
            "sdp", {"response_status": {"messages": [123, None, "NAO-DEVE-APARECER"]}}, http=400)
        self.assertIsInstance(texto, str)
        self.assertTrue(texto)
        self.assertNotIn("NAO-DEVE-APARECER", texto)

    def test_erro_da_zoho_aninhado_nao_vaza_estrutura(self):
        # corpo["error"] vindo como dict (em vez de string curta) não pode ser ecoado.
        texto = sdp_api.traduzir("zoho", {"error": {"vazou": "NAO-DEVE-APARECER"}})
        self.assertNotIn("NAO-DEVE-APARECER", texto)


class TesteCorpoNaoJson(BaseSDP):
    """Resposta 200 cujo corpo não é JSON — o retrato de um proxy ou portal cativo
    respondendo no lugar do ServiceDesk."""

    CORPO_HTML = b"<html><body>Faca login na rede Wi-Fi para continuar</body></html>"

    def test_postar_form_com_200_html_vira_errosdp(self):
        self.rede(self.CORPO_HTML)
        with self.assertRaises(sdp_api.ErroSDP) as caso:
            sdp_api._postar_form(sdp_api.PADRAO_CONFIG["token_url"], {"grant_type": "x"})
        texto = str(caso.exception)
        self.assertTrue(texto)
        self.assertNotIn("<html>", texto)
        self.assertIn("proxy", texto.lower())

    def test_access_token_com_200_html_vira_errosdp_nao_jsondecodeerror(self):
        # access_token() chama _postar_form por baixo; o corpo HTML tem que virar ErroSDP,
        # nunca um json.JSONDecodeError cru.
        self.rede(self.CORPO_HTML)
        with self.assertRaises(sdp_api.ErroSDP) as caso:
            sdp_api.access_token()
        texto = str(caso.exception)
        self.assertTrue(texto)
        self.assertNotIn("<html>", texto)

    def test_chamar_com_200_html_vira_errosdp(self):
        rede = self.rede({"access_token": "acc-1", "expires_in": 3600}, self.CORPO_HTML)
        token = sdp_api.access_token()
        with self.assertRaises(sdp_api.ErroSDP) as caso:
            sdp_api.chamar("GET", "/requests/123", None, token)
        texto = str(caso.exception)
        self.assertTrue(texto)
        self.assertNotIn("<html>", texto)
        self.assertIn("proxy", texto.lower())
        self.assertEqual(len(rede.chamadas), 2)


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

    def test_exclui_canceled_com_grafia_americana(self):
        # Achado ao vivo em 2026-09-14: o ServiceDesk da KINTO usa "Canceled" (L
        # simples), não "Cancelled" (L duplo). Com a grafia errada o filtro "is not"
        # não dava erro nenhum, só não excluía ninguém — 335 chamados cancelados
        # vazavam como "abertos". Trava a grafia certa para não regredir em silêncio.
        rede = self.rede(TOKEN_OK, CHAMADO_LISTA)
        self.executar("listar")
        url = urllib.parse.unquote_plus(rede.chamadas[1]["url"])
        self.assertIn("Canceled", url)
        self.assertNotIn("Cancelled", url)

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

    def test_sem_tecnico_falha_antes_de_qualquer_chamada_de_rede(self):
        # Mesma classe de bug já corrigida em cmd_testar (Task 9): se a checagem do técnico
        # vier depois de access_token(), este teste bate numa chamada HTTP real contra a Zoho
        # em vez de falhar rápido e determinístico — de propósito, NÃO chamamos self.rede(...)
        # aqui. Nome pensado para deixar claro o motivo: se a ordem regredir, este teste vira
        # lento e instável (bate na Zoho de verdade) em vez de simplesmente falhar.
        sdp_api.gravar_config({"tecnico_nome": ""})
        codigo, saida = self.executar("listar")
        self.assertEqual(codigo, 1)
        self.assertIn("técnico", self.json_da_saida(saida)["erro"].lower())

    def test_requests_como_string_vira_errosdp(self):
        # Tipo errado e truthy: "or []" não pega, então sem a checagem de forma isso
        # estouraria TypeError ao tentar iterar/indexar uma string como se fosse lista de
        # chamados.
        self.rede(TOKEN_OK, {"requests": "nao e uma lista",
                             "list_info": {"has_more_rows": False}})
        codigo, saida = self.executar("listar")
        self.assertEqual(codigo, 1)
        erro = self.json_da_saida(saida)["erro"]
        self.assertIn("formato", erro.lower())

    def test_paginacao_tem_teto_e_sinaliza_truncamento(self):
        sempre_mais = {"requests": CHAMADO_LISTA["requests"],
                       "list_info": {"has_more_rows": True}}
        rede = self.rede(TOKEN_OK, *([sempre_mais] * sdp_api.LIMITE_PAGINAS))
        codigo, saida = self.executar("listar")
        self.assertEqual(codigo, 0)
        dados = self.json_da_saida(saida)
        self.assertTrue(dados["truncado"])
        self.assertEqual(len(dados["chamados"]), sdp_api.LIMITE_PAGINAS)
        # 1 chamada de token + uma por página — nunca mais que o teto, mesmo com has_more_rows
        # sempre truthy.
        self.assertEqual(len(rede.chamadas), 1 + sdp_api.LIMITE_PAGINAS)


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

    def test_requests_como_dict_vira_errosdp(self):
        # achar_id: "requests" veio como dict (truthy, tipo errado) em vez de lista — sem a
        # checagem de forma, encontrados[0] estouraria TypeError num dict.
        self.rede(TOKEN_OK, {"requests": {"nao": "e uma lista"}})
        codigo, saida = self.executar("detalhe", "4942")
        self.assertEqual(codigo, 1)
        erro = self.json_da_saida(saida)["erro"]
        self.assertIn("formato", erro.lower())

    def test_request_como_lista_vira_errosdp(self):
        # cmd_detalhe: "request" veio como lista (truthy, tipo errado) em vez de dict — sem a
        # checagem de forma, campo(bruto, ...) e bruto.get(...) tratariam uma lista como se
        # fosse o chamado.
        self.rede(TOKEN_OK, self.BUSCA, {"request": ["nao e um dict"]})
        codigo, saida = self.executar("detalhe", "4942")
        self.assertEqual(codigo, 1)
        erro = self.json_da_saida(saida)["erro"]
        self.assertIn("formato", erro.lower())

    def test_nota_que_nao_e_dict_vira_errosdp(self):
        # Um item de "notes" não é dict — sem a checagem por item, nota.get(...) estouraria
        # AttributeError numa string.
        self.rede(TOKEN_OK, self.BUSCA, self.DETALHE, {"notes": ["nao e um dict"]})
        codigo, saida = self.executar("detalhe", "4942")
        self.assertEqual(codigo, 1)
        erro = self.json_da_saida(saida)["erro"]
        self.assertIn("nota", erro.lower())

    def test_falha_ao_buscar_notas_nao_derruba_o_detalhe(self):
        # O chamado continua aparecendo mesmo se a busca de notas falhar (ex.: token vencido
        # entre as duas chamadas) — mas a falha tem que ficar visível, não parecer "0 notas".
        self.rede(TOKEN_OK, self.BUSCA, self.DETALHE,
                 urllib.error.HTTPError("u", 401, "Unauthorized", {}, io.BytesIO(b"{}")))
        codigo, saida = self.executar("detalhe", "4942")
        self.assertEqual(codigo, 0)
        dados = self.json_da_saida(saida)
        self.assertEqual(dados["numero"], "4942")
        self.assertTrue(dados["notas_indisponiveis"])
        self.assertEqual(dados["notas"], [])


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

    def _arquivo_latin1(self, nome="nota_latin1.html"):
        # Bytes explícitos (não depende do locale da máquina que roda o teste) — simula um
        # arquivo salvo no codepage padrão do Windows (PowerShell Set-Content/Out-File,
        # Bloco de Notas), que não é UTF-8.
        caminho = Path(self.tmp.name) / nome
        caminho.write_bytes("<p>Situação em análise, atenção redobrada.</p>".encode("latin-1"))
        return str(caminho)

    def test_arquivo_fora_de_utf8_vira_errosdp_na_nota(self):
        self.rede(TOKEN_OK)
        codigo, saida = self.executar("nota", "4942", "--arquivo", self._arquivo_latin1(),
                                      "--confirmar")
        self.assertEqual(codigo, 1)
        erro = self.json_da_saida(saida)["erro"]
        self.assertIn("UTF-8", erro)

    def test_arquivo_fora_de_utf8_vira_errosdp_no_resolver(self):
        self.rede(TOKEN_OK)
        codigo, saida = self.executar(
            "resolver", "4942", "--arquivo",
            self._arquivo_latin1("resolucao_latin1.html"), "--confirmar")
        self.assertEqual(codigo, 1)
        erro = self.json_da_saida(saida)["erro"]
        self.assertIn("UTF-8", erro)

    def test_arquivo_que_e_pasta_diz_que_nao_e_arquivo(self):
        self.rede(TOKEN_OK)
        pasta = Path(self.tmp.name) / "pasta_em_vez_de_arquivo.html"
        pasta.mkdir()
        codigo, saida = self.executar("nota", "4942", "--arquivo", str(pasta), "--confirmar")
        self.assertEqual(codigo, 1)
        erro = self.json_da_saida(saida)["erro"].lower()
        self.assertNotIn("não encontrei", erro)
        self.assertIn("não é um arquivo", erro)

    def test_status_simples(self):
        rede = self.rede(TOKEN_OK, self.BUSCA, {"response_status": {"status": "success"}})
        self.executar("status", "4942", "In Progress", "--confirmar")
        envio = rede.chamadas[-1]
        self.assertEqual(envio["metodo"], "PUT")
        payload = json.loads(urllib.parse.parse_qs(envio["corpo"])["input_data"][0])
        self.assertEqual(payload["request"]["status"]["name"], "In Progress")
        self.assertNotIn("onhold_scheduler", payload["request"])

    def test_status_sem_confirmar_nao_escreve(self):
        rede = self.rede(TOKEN_OK, self.BUSCA)
        codigo, saida = self.executar("status", "4942", "In Progress")
        self.assertEqual(codigo, 0)
        self.assertTrue(self.json_da_saida(saida)["simulacao"])
        self.assertTrue(all(c["metodo"] == "GET" for c in rede.chamadas[1:]))

    def test_status_de_espera_exige_comentario(self):
        self.rede(TOKEN_OK, self.BUSCA)
        codigo, saida = self.executar("status", "4942", "On Hold", "--confirmar")
        self.assertEqual(codigo, 1)
        self.assertIn("comentário", self.json_da_saida(saida)["erro"].lower())

    def test_status_de_espera_com_comentario_manda_onhold(self):
        # Comentário sem acento de propósito: este teste verifica que o texto confirmado
        # chega a onhold_scheduler.comments, não a conversão de acentos — essa parte tem
        # teste dedicado logo abaixo (test_status_de_espera_comentario_acentos_viram_entidades),
        # no mesmo estilo do teste de acentos da nota.
        rede = self.rede(TOKEN_OK, self.BUSCA, {"response_status": {"status": "success"}})
        self.executar("status", "4942", "Aguardando Aprovação",
                      "--comentario", "esperando aprovacao do gestor", "--confirmar")
        payload = json.loads(
            urllib.parse.parse_qs(rede.chamadas[-1]["corpo"])["input_data"][0])
        self.assertEqual(payload["request"]["onhold_scheduler"]["comments"],
                         "esperando aprovacao do gestor")

    def test_status_de_espera_comentario_acentos_viram_entidades(self):
        # Mesmo tratamento que a nota e a resolução (entidades()) — antes da correção da
        # revisão, o comentário de onhold_scheduler ia cru, sem passar por entidades().
        rede = self.rede(TOKEN_OK, self.BUSCA, {"response_status": {"status": "success"}})
        self.executar("status", "4942", "Aguardando Aprovação",
                      "--comentario", "esperando validação e atenção", "--confirmar")
        payload = json.loads(
            urllib.parse.parse_qs(rede.chamadas[-1]["corpo"])["input_data"][0])
        comentario = payload["request"]["onhold_scheduler"]["comments"]
        self.assertIn("&#231;", comentario)  # ç
        self.assertIn("&#227;", comentario)  # ã
        self.assertNotIn("ç", comentario)
        self.assertNotIn("ã", comentario)

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

    def test_grant_code_via_op_com_falha_vira_errosdp(self):
        # Defeito encontrado no código de referência do plano: SDP_GRANT_CODE
        # apontando para o 1Password (op://...) com a leitura falhando fazia
        # kbr_secrets.ErroSegredo escapar cru de cmd_autorizar — main() só
        # captura ErroSDP, então o técnico veria um traceback em vez de JSON.
        kbr_secrets.caminho_arquivo().write_text(
            "SDP_CLIENT_ID=cid\nSDP_CLIENT_SECRET=csec\n"
            "SDP_GRANT_CODE=op://Cofre/Item/grant\nSDP_REFRESH_TOKEN=\n", encoding="utf-8")
        kbr_secrets._rodar_op = OpFalsoSDP(erro="não autenticado", codigo=1)
        codigo, saida = self.executar("autorizar")
        self.assertEqual(codigo, 1)
        erro = self.json_da_saida(saida)["erro"]
        self.assertIn("SDP_GRANT_CODE", erro)


class TesteEscopos(BaseComando):
    def test_lista_os_tres_escopos(self):
        codigo, saida = self.executar("escopos")
        self.assertEqual(codigo, 0)
        dados = self.json_da_saida(saida)
        self.assertEqual(dados["escopos"], sdp_api.ESCOPOS)
        self.assertIn("api-console.zoho.com", dados["console"])


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
        self.rede(pagina1, pagina2)
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


if __name__ == "__main__":
    unittest.main()
