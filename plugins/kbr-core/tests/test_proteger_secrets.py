# -*- coding: utf-8 -*-
"""Testes da decisão do hook que protege ~/.kbr."""
import json
import io
import contextlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))
import proteger_secrets  # noqa: E402

BASE = Path("C:/Users/Fulano/.kbr") if sys.platform == "win32" else Path("/home/fulano/.kbr")


class TesteNega(unittest.TestCase):
    def nega(self, **tool_input):
        return proteger_secrets.decidir(tool_input, BASE)

    def test_read_com_til(self):
        self.assertIsNotNone(self.nega(file_path="~/.kbr/secrets.env"))

    def test_read_com_caminho_absoluto(self):
        self.assertIsNotNone(self.nega(file_path=str(BASE / "secrets.env")))

    def test_read_com_barra_invertida(self):
        self.assertIsNotNone(self.nega(file_path="C:\\Users\\Fulano\\.kbr\\secrets.env"))

    def test_read_com_maiusculas(self):
        self.assertIsNotNone(self.nega(file_path="~/.KBR/SECRETS.ENV"))

    def test_bash_com_cat(self):
        self.assertIsNotNone(self.nega(command="cat ~/.kbr/secrets.env"))

    def test_bash_com_type_do_windows(self):
        self.assertIsNotNone(self.nega(command="type %USERPROFILE%\\.kbr\\secrets.env"))

    def test_bash_com_get_content(self):
        self.assertIsNotNone(self.nega(command="Get-Content $env:USERPROFILE\\.kbr\\secrets.env"))

    def test_bash_com_redirecionamento(self):
        self.assertIsNotNone(self.nega(command="sort < ~/.kbr/secrets.env"))

    def test_bash_com_python_open(self):
        self.assertIsNotNone(
            self.nega(command="python -c \"print(open('~/.kbr/secrets.env').read())\""))

    def test_grep_na_pasta(self):
        self.assertIsNotNone(self.nega(path="~/.kbr", pattern="SDP_"))

    def test_glob_com_estrela(self):
        self.assertIsNotNone(self.nega(pattern="~/.kbr/**"))

    def test_cache_do_token(self):
        self.assertIsNotNone(self.nega(file_path="~/.kbr/cache/sdp_access_token.json"))

    def test_listar_a_pasta(self):
        self.assertIsNotNone(self.nega(command="ls -la ~/.kbr"))

    def test_motivo_e_em_portugues_e_aponta_o_status(self):
        motivo = self.nega(file_path="~/.kbr/secrets.env")
        self.assertIn("segredos", motivo.lower())
        self.assertIn("/kbr-core:secrets status", motivo)


class TestePermite(unittest.TestCase):
    def permite(self, **tool_input):
        return proteger_secrets.decidir(tool_input, BASE)

    def test_config_json(self):
        self.assertIsNone(self.permite(file_path="~/.kbr/config.json"))

    def test_config_json_absoluto(self):
        self.assertIsNone(self.permite(file_path=str(BASE / "config.json")))

    def test_script_do_plugin(self):
        self.assertIsNone(self.permite(
            command="python ${CLAUDE_PLUGIN_ROOT}/scripts/sdp_api.py listar"))

    def test_caminho_do_repo_com_kbr_no_nome(self):
        self.assertIsNone(self.permite(file_path="E:/Projetos/plugins/kbr-core/scripts/x.py"))

    def test_pasta_parecida_nao_dispara(self):
        self.assertIsNone(self.permite(file_path="~/.kbrasil/dados.txt"))

    def test_arquivo_qualquer(self):
        self.assertIsNone(self.permite(file_path="README.md"))

    def test_tool_input_vazio(self):
        self.assertIsNone(self.permite())

    def test_tool_input_com_tipo_inesperado_nao_quebra(self):
        # tool_input vindo de JSON pode não ser um objeto (string, lista, número...).
        self.assertIsNone(proteger_secrets.decidir("~/.kbr/secrets.env", BASE))
        self.assertIsNone(proteger_secrets.decidir(["~/.kbr/secrets.env"], BASE))
        self.assertIsNone(proteger_secrets.decidir(42, BASE))


class TesteSaida(unittest.TestCase):
    def rodar(self, payload):
        entrada = io.StringIO(json.dumps(payload))
        captura = io.StringIO()
        anterior = sys.stdin
        sys.stdin = entrada
        try:
            with contextlib.redirect_stdout(captura):
                codigo = proteger_secrets.main()
        finally:
            sys.stdin = anterior
        return codigo, captura.getvalue()

    def test_permitir_nao_imprime_nada(self):
        codigo, saida = self.rodar({"tool_name": "Read",
                                    "tool_input": {"file_path": "README.md"}})
        self.assertEqual(codigo, 0)
        self.assertEqual(saida.strip(), "")

    def test_negar_imprime_json_do_hook(self):
        codigo, saida = self.rodar({"tool_name": "Read",
                                    "tool_input": {"file_path": "~/.kbr/secrets.env"}})
        self.assertEqual(codigo, 0)
        dados = json.loads(saida)
        especifico = dados["hookSpecificOutput"]
        self.assertEqual(especifico["hookEventName"], "PreToolUse")
        self.assertEqual(especifico["permissionDecision"], "deny")
        self.assertTrue(especifico["permissionDecisionReason"])

    def test_tool_input_com_tipo_inesperado_nao_quebra(self):
        codigo, saida = self.rodar({"tool_name": "Read", "tool_input": "algum texto"})
        self.assertEqual(codigo, 0)
        self.assertEqual(saida.strip(), "")

    def test_entrada_invalida_nao_quebra(self):
        entrada = io.StringIO("isso não é json")
        anterior = sys.stdin
        sys.stdin = entrada
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(proteger_secrets.main(), 0)
        finally:
            sys.stdin = anterior


if __name__ == "__main__":
    unittest.main()
