# -*- coding: utf-8 -*-
"""Testes do módulo de segredos — parser do .env e ordem de resolução."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import kbr_secrets  # noqa: E402


class BaseTemporaria(unittest.TestCase):
    """Redireciona ~/.kbr para uma pasta temporária via KBR_HOME."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name) / ".kbr"
        self.base.mkdir(parents=True)
        self._env_anterior = dict(os.environ)
        os.environ["KBR_HOME"] = str(self.base)
        kbr_secrets._cache_op.clear()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env_anterior)
        self.tmp.cleanup()

    def escrever(self, texto):
        kbr_secrets.caminho_arquivo().write_text(texto, encoding="utf-8")


class TesteParser(unittest.TestCase):
    def test_par_simples(self):
        valores, avisos = kbr_secrets.analisar("SDP_CLIENT_ID=abc123\n")
        self.assertEqual(valores, {"SDP_CLIENT_ID": "abc123"})
        self.assertEqual(avisos, [])

    def test_ignora_bom_e_crlf(self):
        valores, _ = kbr_secrets.analisar("\ufeffA=1\r\nB=2\r\n")
        self.assertEqual(valores, {"A": "1", "B": "2"})

    def test_ignora_comentario_e_linha_vazia(self):
        valores, avisos = kbr_secrets.analisar("# comentário\n\n  # outro\nA=1\n")
        self.assertEqual(valores, {"A": "1"})
        self.assertEqual(avisos, [])

    def test_remove_espacos_em_volta(self):
        valores, _ = kbr_secrets.analisar("  A  =  valor com espaço  \n")
        self.assertEqual(valores, {"A": "valor com espaço"})

    def test_remove_aspas(self):
        valores, _ = kbr_secrets.analisar("A=\"com aspas\"\nB='simples'\n")
        self.assertEqual(valores, {"A": "com aspas", "B": "simples"})

    def test_valor_com_igual_dentro(self):
        valores, _ = kbr_secrets.analisar("A=x=y=z\n")
        self.assertEqual(valores, {"A": "x=y=z"})

    def test_chave_repetida_vale_a_ultima(self):
        valores, _ = kbr_secrets.analisar("A=1\nA=2\n")
        self.assertEqual(valores, {"A": "2"})

    def test_linha_sem_igual_vira_aviso(self):
        valores, avisos = kbr_secrets.analisar("lixo\nA=1\n")
        self.assertEqual(valores, {"A": "1"})
        self.assertEqual(len(avisos), 1)
        self.assertIn("linha 1", avisos[0])

    def test_chave_invalida_vira_aviso(self):
        valores, avisos = kbr_secrets.analisar("minha-chave=1\nA=2\n")
        self.assertEqual(valores, {"A": "2"})
        self.assertEqual(len(avisos), 1)

    def test_valor_vazio_e_preservado(self):
        valores, avisos = kbr_secrets.analisar("A=\n")
        self.assertEqual(valores, {"A": ""})
        self.assertEqual(avisos, [])


class TesteResolucao(BaseTemporaria):
    def test_le_do_arquivo(self):
        self.escrever("SDP_CLIENT_ID=do-arquivo\n")
        self.assertEqual(kbr_secrets.obter("SDP_CLIENT_ID"), "do-arquivo")

    def test_ambiente_ganha_do_arquivo(self):
        self.escrever("SDP_CLIENT_ID=do-arquivo\n")
        os.environ["SDP_CLIENT_ID"] = "do-ambiente"
        self.assertEqual(kbr_secrets.obter("SDP_CLIENT_ID"), "do-ambiente")

    def test_ausente_obrigatorio_levanta(self):
        self.escrever("SDP_CLIENT_ID=\n")
        with self.assertRaises(kbr_secrets.SegredoAusente):
            kbr_secrets.obter("SDP_CLIENT_ID")

    def test_ausente_opcional_devolve_none(self):
        self.escrever("")
        self.assertIsNone(kbr_secrets.obter("SDP_CLIENT_ID", obrigatorio=False))

    def test_mensagem_do_erro_aponta_o_wizard(self):
        self.escrever("")
        with self.assertRaises(kbr_secrets.SegredoAusente) as caso:
            kbr_secrets.obter("SDP_CLIENT_ID")
        self.assertIn("/kbr-servicedesk:configurar", str(caso.exception))

    def test_mensagem_do_erro_nao_vaza_valor(self):
        self.escrever("OUTRO=segredo-secretissimo\n")
        with self.assertRaises(kbr_secrets.SegredoAusente) as caso:
            kbr_secrets.obter("SDP_CLIENT_ID")
        self.assertNotIn("segredo-secretissimo", str(caso.exception))

    def test_arquivo_inexistente_nao_quebra(self):
        self.assertEqual(kbr_secrets.ler_arquivo(), {})


if __name__ == "__main__":
    unittest.main()
