# -*- coding: utf-8 -*-
"""Testes da decisão do hook que protege ~/.kbr."""
import json
import io
import contextlib
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))
import proteger_secrets  # noqa: E402

BASE = Path("C:/Users/Fulano/.kbr") if sys.platform == "win32" else Path("/home/fulano/.kbr")


class TesteNega(unittest.TestCase):
    def nega(self, tool_name="Read", **tool_input):
        return proteger_secrets.decidir(tool_name, tool_input, BASE)

    def test_read_com_til(self):
        self.assertIsNotNone(self.nega(file_path="~/.kbr/secrets.env"))

    def test_read_com_caminho_absoluto(self):
        self.assertIsNotNone(self.nega(file_path=str(BASE / "secrets.env")))

    def test_read_com_barra_invertida(self):
        self.assertIsNotNone(self.nega(file_path="C:\\Users\\Fulano\\.kbr\\secrets.env"))

    def test_read_com_maiusculas(self):
        self.assertIsNotNone(self.nega(file_path="~/.KBR/SECRETS.ENV"))

    def test_bash_com_cat(self):
        self.assertIsNotNone(self.nega(tool_name="Bash", command="cat ~/.kbr/secrets.env"))

    def test_bash_com_type_do_windows(self):
        self.assertIsNotNone(self.nega(
            tool_name="Bash", command="type %USERPROFILE%\\.kbr\\secrets.env"))

    def test_bash_com_get_content(self):
        self.assertIsNotNone(self.nega(
            tool_name="Bash", command="Get-Content $env:USERPROFILE\\.kbr\\secrets.env"))

    def test_bash_com_redirecionamento(self):
        self.assertIsNotNone(self.nega(tool_name="Bash", command="sort < ~/.kbr/secrets.env"))

    def test_bash_com_python_open(self):
        self.assertIsNotNone(self.nega(
            tool_name="Bash",
            command="python -c \"print(open('~/.kbr/secrets.env').read())\""))

    def test_grep_na_pasta(self):
        self.assertIsNotNone(self.nega(tool_name="Grep", path="~/.kbr", pattern="SDP_"))

    def test_glob_com_estrela(self):
        self.assertIsNotNone(self.nega(tool_name="Glob", pattern="~/.kbr/**"))

    def test_cache_do_token(self):
        self.assertIsNotNone(self.nega(file_path="~/.kbr/cache/sdp_access_token.json"))

    def test_listar_a_pasta(self):
        self.assertIsNotNone(self.nega(tool_name="Bash", command="ls -la ~/.kbr"))

    def test_motivo_e_em_portugues_e_aponta_o_status(self):
        motivo = self.nega(file_path="~/.kbr/secrets.env")
        self.assertIn("segredos", motivo.lower())
        self.assertIn("/kbr-core:secrets status", motivo)

    # --- Achado 1: campos inspecionados dependem de tool_name -------------

    def test_notebookedit_usa_notebook_path(self):
        self.assertIsNotNone(self.nega(
            tool_name="NotebookEdit", notebook_path=str(BASE / "notebook.ipynb")))

    def test_multiedit_usa_file_path(self):
        self.assertIsNotNone(self.nega(
            tool_name="MultiEdit", file_path=str(BASE / "secrets.env")))

    def test_ferramenta_desconhecida_usa_lista_padrao_de_campos(self):
        # Prova o fallback: uma ferramenta que o hook não conhece ainda assim
        # tem o campo "path" varrido, porque está na lista padrão de campos.
        self.assertIsNotNone(self.nega(
            tool_name="FerramentaXYZDesconhecida", path="~/.kbr/secrets.env"))

    # --- Rodada 3, achado 1: ".kbr" nega em qualquer posição do "command" --
    #
    # Postura fixada na terceira rodada da revisão: dentro de "command", ".kbr"
    # nega sempre que aparece como segmento de caminho completo, não importa o
    # que vem antes (início da string, espaço, "/", "~", aspas, ";", "&&"...).
    # Isso reinstala de propósito o falso positivo que a segunda rodada tinha
    # removido: um comando cujo texto só *menciona* a pasta protegida — numa
    # mensagem de commit, num `echo` — volta a ser negado. Não dá pra separar
    # esse caso de um caminho de verdade sendo endereçado sem rastrear aspas
    # do shell (que este hook deliberadamente não faz); entre negar à toa
    # numa frase e deixar passar um comando que lê o arquivo de verdade, a
    # escolha é negar. Ver docstring do módulo e relatório da task 5.

    def test_bash_commit_mencionando_a_pasta_entre_aspas_e_negado(self):
        self.assertIsNotNone(self.nega(
            tool_name="Bash",
            command='git commit -m "feat(kbr-core): hook que protege ~/.kbr"'))

    def test_bash_echo_mencionando_a_pasta_em_prosa_e_negado(self):
        # Migrado de TestePermite nesta rodada: antes era o caso que provava
        # que "command" só casava forma de caminho, não menção solta. Essa
        # distinção foi removida de propósito (ver comentário da seção acima)
        # — este teste agora prova o oposto, deliberadamente.
        self.assertIsNotNone(self.nega(
            tool_name="Bash", command='echo "os segredos ficam dentro de .kbr"'))

    def test_bash_cd_relativo_e_cat_e_negado(self):
        # Achado 1 da terceira rodada: "cd .kbr" não tem "/", "~" nem letra de
        # unidade antes de ".kbr" — a exigência de prefixo que existia antes
        # deixava isso passar, apesar de "cat *.env" ler o conteúdo de dentro
        # da pasta protegida logo em seguida.
        self.assertIsNotNone(self.nega(tool_name="Bash", command="cd .kbr && cat *.env"))

    def test_bash_cat_caminho_relativo_do_token_e_negado(self):
        # Grafia relativa do mesmo arquivo que test_cache_do_token já nega via
        # file_path — aqui o alvo é endereçado de dentro de um comando Bash,
        # sem separador nenhum antes de ".kbr".
        self.assertIsNotNone(self.nega(
            tool_name="Bash", command="cat .kbr/cache/sdp_access_token.json"))

    def test_bash_cd_encadeado_relativo_e_negado(self):
        self.assertIsNotNone(self.nega(
            tool_name="Bash", command="cd; cd .kbr; cat *.env"))

    def test_bash_pushd_relativo_e_negado(self):
        self.assertIsNotNone(self.nega(
            tool_name="Bash", command="pushd .kbr && cat *.env && popd"))

    # --- Achado 3 (rodada 2): secrets.env como segundo marcador ------------
    #
    # Na terceira rodada esse marcador passou a valer só para "command" do
    # Bash (achado 2 da terceira rodada — ver TestePermite): os três bypasses
    # abaixo continuam sendo casos de "command", então continuam negados.

    def test_bypass_aspas_no_meio_do_nome_e_negado(self):
        self.assertIsNotNone(self.nega(tool_name="Bash", command='cat ~/.k""br/secrets.env'))

    def test_bypass_variavel_de_shell_e_negado(self):
        self.assertIsNotNone(self.nega(
            tool_name="Bash", command="x=kbr; cat ~/.$x/secrets.env"))

    def test_bypass_coringa_no_nome_e_negado(self):
        self.assertIsNotNone(self.nega(tool_name="Bash", command="cat ~/.kb?/secrets.env"))

    # --- Achado 4: exceção do config.json é exata ---------------------------

    def test_config_json_bak_e_negado(self):
        self.assertIsNotNone(self.nega(file_path=str(BASE / "config.json.bak")))

    def test_config_jsonx_e_negado(self):
        self.assertIsNotNone(self.nega(file_path=str(BASE / "config.jsonx")))

    def test_config_json_com_travessia_e_negado(self):
        self.assertIsNotNone(self.nega(
            file_path=str(BASE).replace("\\", "/") + "/config.json/../secrets.env"))


class TestePermite(unittest.TestCase):
    def permite(self, tool_name="Read", **tool_input):
        return proteger_secrets.decidir(tool_name, tool_input, BASE)

    def test_config_json(self):
        self.assertIsNone(self.permite(file_path="~/.kbr/config.json"))

    def test_config_json_absoluto(self):
        self.assertIsNone(self.permite(file_path=str(BASE / "config.json")))

    def test_script_do_plugin(self):
        self.assertIsNone(self.permite(
            tool_name="Bash", command="python ${CLAUDE_PLUGIN_ROOT}/scripts/sdp_api.py listar"))

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
        self.assertIsNone(proteger_secrets.decidir("Read", "~/.kbr/secrets.env", BASE))
        self.assertIsNone(proteger_secrets.decidir("Read", ["~/.kbr/secrets.env"], BASE))
        self.assertIsNone(proteger_secrets.decidir("Read", 42, BASE))

    def test_tool_name_com_tipo_inesperado_nao_quebra(self):
        # tool_name também vem de JSON e pode chegar como lista/dict (tipo não
        # hashável) — não pode estourar TypeError no .get() do dicionário de
        # campos por ferramenta; deve só cair no padrão seguro e não achar nada.
        self.assertIsNone(proteger_secrets.decidir(["Read"], {"file_path": "README.md"}, BASE))
        self.assertIsNone(proteger_secrets.decidir(None, {"file_path": "README.md"}, BASE))

    # --- Achado 1: campos inspecionados dependem de tool_name -------------

    def test_grep_pattern_mencionando_pasta_com_path_fora_e_permitido(self):
        # Cenário exato da revisão: Grep(pattern="\.kbr", path=".") é trabalho
        # legítimo de busca no código-fonte, não um acesso à pasta protegida.
        self.assertIsNone(self.permite(tool_name="Grep", pattern=r"\.kbr", path="."))

    # --- Rodada 2, achado 2 (o que sobra dele após a rodada 3) ------------
    #
    # A exigência de forma de caminho em "command" foi removida (ver
    # TesteNega, seção "Rodada 3, achado 1"): agora até menção solta em prosa
    # nega. O que continua permitido é só o caso em que ".kbr" nem aparece —
    # "kbr_secrets" não tem o "." literal antes de "kbr", então nenhum dos
    # dois marcadores (MARCA ou MARCADOR_SEGREDOS) casa.

    def test_bash_grep_por_kbr_secrets_e_permitido(self):
        self.assertIsNone(self.permite(tool_name="Bash", command='grep -rn "kbr_secrets" plugins/'))

    # --- Rodada 3, achado 2: secrets.env só conta no "command" do Bash -----
    #
    # O marcador do nome do arquivo (MARCADOR_SEGREDOS) existia para fechar
    # três grafias que escapam do marcador ".kbr" dentro de um comando Bash
    # (ver TesteNega, "Achado 3"). Aplicado a qualquer campo, ele também
    # negava um "secrets.env" de outro projeto sem relação nenhuma com
    # "~/.kbr" — passou a valer só para "command".

    def test_read_secrets_env_de_outro_projeto_e_permitido(self):
        self.assertIsNone(self.permite(
            file_path="E:/Projetos/OutroProjeto/config/secrets.env"))

    def test_edit_secrets_env_de_outro_projeto_e_permitido(self):
        self.assertIsNone(self.permite(
            tool_name="Edit", file_path="E:/Projetos/OutroProjeto/config/secrets.env"))


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

    # --- Achado 5: caminho_base() pode levantar -----------------------------

    def test_main_com_home_indisponivel_retorna_0_sem_imprimir(self):
        payload = {"tool_name": "Read", "tool_input": {"file_path": "~/.kbr/secrets.env"}}
        entrada = io.StringIO(json.dumps(payload))
        captura = io.StringIO()
        anterior_stdin = sys.stdin
        kbr_home_anterior = os.environ.pop("KBR_HOME", None)
        sys.stdin = entrada
        try:
            with mock.patch.object(
                    proteger_secrets.Path, "home",
                    side_effect=RuntimeError("não foi possível resolver o diretório do usuário")):
                with contextlib.redirect_stdout(captura):
                    codigo = proteger_secrets.main()
        finally:
            sys.stdin = anterior_stdin
            if kbr_home_anterior is not None:
                os.environ["KBR_HOME"] = kbr_home_anterior
        self.assertEqual(codigo, 0)
        self.assertEqual(captura.getvalue().strip(), "")


if __name__ == "__main__":
    unittest.main()
