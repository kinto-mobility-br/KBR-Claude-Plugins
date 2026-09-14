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

RAIZ_PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ_PLUGIN / "scripts"))
import kbr_secrets  # noqa: E402
import sdp_api  # noqa: E402


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

    def tearDown(self):
        sdp_api._abrir = self._abrir_original
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


if __name__ == "__main__":
    unittest.main()
