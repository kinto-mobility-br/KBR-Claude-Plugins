# -*- coding: utf-8 -*-
"""Testes do acesso à API do ServiceDesk Plus."""
import io
import json
import os
import sys
import tempfile
import time
import unittest
import urllib.error
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


class RedeFalsa:
    """Substitui sdp_api._abrir. Devolve as respostas na ordem da fila."""

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
        # response_status não é dict: não pode lançar AttributeError.
        texto = sdp_api.traduzir("sdp", {"response_status": "formato inesperado"}, http=400)
        self.assertIsInstance(texto, str)

    def test_messages_com_item_que_nao_e_dict_nao_quebra(self):
        # um item da lista messages não é dict: não pode lançar AttributeError.
        texto = sdp_api.traduzir(
            "sdp", {"response_status": {"messages": [123, None, "str"]}}, http=400)
        self.assertIsInstance(texto, str)

    def test_erro_da_zoho_aninhado_nao_vaza_estrutura(self):
        # corpo["error"] vindo como dict (em vez de string curta) não pode ser ecoado.
        texto = sdp_api.traduzir("zoho", {"error": {"vazou": "NAO-DEVE-APARECER"}})
        self.assertNotIn("NAO-DEVE-APARECER", texto)


if __name__ == "__main__":
    unittest.main()
