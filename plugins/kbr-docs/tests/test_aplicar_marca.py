# -*- coding: utf-8 -*-
"""Testes da geração de documentos (aplicar_marca.py)."""
import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ_PLUGIN = Path(__file__).resolve().parents[1]
SCRIPTS = RAIZ_PLUGIN / "skills" / "report-creator" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import aplicar_marca  # noqa: E402
import descobrir  # noqa: E402


def _rodar(*argumentos):
    argv_original = sys.argv
    sys.argv = ["aplicar_marca.py", *argumentos]
    saida, erro = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(saida), contextlib.redirect_stderr(erro):
            codigo = aplicar_marca.main()
    finally:
        sys.argv = argv_original
    return codigo, saida.getvalue(), erro.getvalue()


class TesteCarregarYamlSimples(unittest.TestCase):
    def test_le_secoes_aninhadas_ate_tres_niveis(self):
        texto = '''
projeto:
  nome: "Projeto X"
  subtitulo: ""
marca:
  claro:
    brand: "#336699"
    hover: "#2A527A"
  escuro:
    brand: "#5C9BC9"
'''
        cfg = aplicar_marca.carregar_yaml_simples(texto)
        self.assertEqual(cfg["projeto"]["nome"], "Projeto X")
        self.assertEqual(cfg["projeto"]["subtitulo"], "")
        self.assertEqual(cfg["marca"]["claro"]["brand"], "#336699")
        self.assertEqual(cfg["marca"]["claro"]["hover"], "#2A527A")
        self.assertEqual(cfg["marca"]["escuro"]["brand"], "#5C9BC9")

    def test_booleano_vira_bool_de_verdade(self):
        cfg = aplicar_marca.carregar_yaml_simples('tipografia:\n  fontes_externas: true\n')
        self.assertIs(cfg["tipografia"]["fontes_externas"], True)

    def test_booleano_aceita_variacoes_do_yaml_1_1(self):
        for texto_verdadeiro in ('true', 'True', 'TRUE', 'yes', 'on'):
            cfg = aplicar_marca.carregar_yaml_simples(
                f'tipografia:\n  fontes_externas: {texto_verdadeiro}\n')
            self.assertIs(cfg["tipografia"]["fontes_externas"], True, texto_verdadeiro)
        for texto_falso in ('false', 'False', 'FALSE', 'no', 'off'):
            cfg = aplicar_marca.carregar_yaml_simples(
                f'tipografia:\n  fontes_externas: {texto_falso}\n')
            self.assertIs(cfg["tipografia"]["fontes_externas"], False, texto_falso)

    def test_aspas_vencem_a_interpretacao_como_booleano(self):
        # "true"/"no" citados são texto, não booleano — precisa continuar assim mesmo
        # se _valor_escalar for mexido de novo no futuro (ex.: para aceitar mais formas
        # de booleano sem aspas).
        cfg = aplicar_marca.carregar_yaml_simples('projeto:\n  nome: "true"\n')
        self.assertIsInstance(cfg["projeto"]["nome"], str)
        self.assertEqual(cfg["projeto"]["nome"], "true")

    def test_le_arquivo_com_bom_sem_perder_a_primeira_chave(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / ".docs-brand.yml"
            texto = 'projeto:\n  nome: "Projeto X"\n'
            caminho.write_bytes(b'\xef\xbb\xbf' + texto.encode('utf-8'))
            cfg = aplicar_marca.carregar_yaml(caminho)
            self.assertEqual(cfg["projeto"]["nome"], "Projeto X")

    def test_comentario_de_linha_inteira_e_ignorado(self):
        texto = '# isto é um comentário\nprojeto:\n  nome: "X"\n'
        cfg = aplicar_marca.carregar_yaml_simples(texto)
        self.assertEqual(cfg["projeto"]["nome"], "X")

    def test_comentario_a_direita_do_valor_e_removido(self):
        cfg = aplicar_marca.carregar_yaml_simples(
            'projeto:\n  nome: "X"   # comentário com : dois pontos dentro\n')
        self.assertEqual(cfg["projeto"]["nome"], "X")

    def test_cardinal_dentro_de_aspas_nao_e_tratado_como_comentario(self):
        cfg = aplicar_marca.carregar_yaml_simples(
            'textos:\n  rodape: "Time de Dados #1"\n')
        self.assertEqual(cfg["textos"]["rodape"], "Time de Dados #1")

    def test_round_trip_com_montar_yaml_da_task_1(self):
        texto = descobrir.montar_yaml(
            Path("/tmp/projeto-x"), "Projeto X", "CLAUDE.md",
            {"caminho": "assets/logo-claro.svg", "cor": "#336699"},
            {"caminho": "assets/logo-escuro.svg", "cor": None})
        cfg = aplicar_marca.carregar_yaml_simples(texto)
        self.assertEqual(cfg["projeto"]["nome"], "Projeto X")
        self.assertEqual(cfg["projeto"]["classificacao"], "Interno")
        self.assertEqual(cfg["logo"]["claro"], "assets/logo-claro.svg")
        self.assertEqual(cfg["logo"]["escuro"], "assets/logo-escuro.svg")
        self.assertEqual(cfg["marca"]["claro"]["brand"], "#336699")
        self.assertIn("hover", cfg["marca"]["claro"])
        self.assertIn("tint", cfg["marca"]["claro"])
        self.assertIn("brand", cfg["marca"]["escuro"])
        self.assertIs(cfg["tipografia"]["fontes_externas"], True)
        self.assertEqual(cfg["saida"]["pasta"], "docs")


class TesteMainAplicarMarca(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self.tmp.name)
        # Isola do nível de usuário real (~/.claude/plugins-data/kbr-docs/) --
        # sem isso, esta suíte lê o que houver na máquina de quem rodar.
        self.tmp_usuario = tempfile.TemporaryDirectory()
        self._env_anterior = dict(os.environ)
        os.environ["CLAUDE_USER_HOME"] = self.tmp_usuario.name

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env_anterior)
        self.tmp.cleanup()
        self.tmp_usuario.cleanup()

    def _gravar_yaml_minimo(self, extra: str = "") -> None:
        (self.raiz / ".docs-brand.yml").write_text(
            'projeto:\n  nome: "Projeto X"\n'
            'logo:\n  claro: ""\n  escuro: ""\n'
            'marca:\n  claro:\n    brand: "#336699"\n'
            '  escuro:\n    brand: "#5C9BC9"\n'
            'textos:\n  rodape: "rodape"\n'
            'autoria:\n  autor: ""\n'
            'contato:\n  email: ""\n'
            'tipografia:\n  fontes_externas: true\n' + extra,
            encoding="utf-8")

    def test_falha_limpa_sem_docs_brand_yml(self):
        destino = self.raiz / "saida"
        codigo, _, erro = _rodar(str(destino), f"--raiz={self.raiz}")
        self.assertEqual(codigo, 1)
        self.assertIn("report-creator", erro)

    def test_copia_os_assets_para_o_destino(self):
        self._gravar_yaml_minimo()
        destino = self.raiz / "saida"
        codigo, _, _ = _rodar(str(destino), f"--raiz={self.raiz}")
        self.assertEqual(codigo, 0)
        self.assertTrue((destino / "assets" / "docs.css").is_file())
        self.assertTrue((destino / "assets" / "docs.js").is_file())

    def test_sem_logo_mantem_o_placeholder(self):
        self._gravar_yaml_minimo()
        destino = self.raiz / "saida"
        _rodar(str(destino), f"--raiz={self.raiz}")
        self.assertTrue((destino / "assets" / "logo-claro.svg").is_file())
        self.assertTrue((destino / "assets" / "logo-escuro.svg").is_file())

    def test_instala_logo_do_projeto_sobre_o_placeholder(self):
        (self.raiz / "meu-logo.svg").write_text("<svg></svg>", encoding="utf-8")
        self._gravar_yaml_minimo()
        (self.raiz / ".docs-brand.yml").write_text(
            (self.raiz / ".docs-brand.yml").read_text(encoding="utf-8")
            .replace('claro: ""', 'claro: "meu-logo.svg"'), encoding="utf-8")
        destino = self.raiz / "saida"
        _rodar(str(destino), f"--raiz={self.raiz}")
        self.assertTrue((destino / "assets" / "logo-claro.svg").is_file())
        self.assertEqual(
            (destino / "assets" / "logo-claro.svg").read_text(encoding="utf-8"), "<svg></svg>")

    def test_gera_brand_css_com_os_tokens_do_yaml(self):
        self._gravar_yaml_minimo()
        destino = self.raiz / "saida"
        _rodar(str(destino), f"--raiz={self.raiz}")
        brand_css = (destino / "assets" / "brand.css").read_text(encoding="utf-8")
        self.assertIn("#336699", brand_css)

    def test_nunca_sobrescreve_arquivo_ja_existente(self):
        self._gravar_yaml_minimo()
        destino = self.raiz / "saida"
        destino.mkdir()
        sentinela = destino / "index.html"
        sentinela.write_text("NAO MEXER", encoding="utf-8")
        codigo, _, _ = _rodar(str(destino), f"--raiz={self.raiz}")
        self.assertEqual(codigo, 0)
        self.assertEqual(sentinela.read_text(encoding="utf-8"), "NAO MEXER")

    def test_fontes_externas_false_remove_links_do_google_fonts(self):
        self._gravar_yaml_minimo()
        (self.raiz / ".docs-brand.yml").write_text(
            (self.raiz / ".docs-brand.yml").read_text(encoding="utf-8")
            .replace("fontes_externas: true", "fontes_externas: false"), encoding="utf-8")
        destino = self.raiz / "saida"
        _rodar(str(destino), f"--raiz={self.raiz}")
        index_html = (destino / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("fonts.googleapis.com", index_html)
        self.assertNotIn("fonts.gstatic.com", index_html)


class TesteCascataViaMain(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self.tmp.name)
        self.tmp_usuario = tempfile.TemporaryDirectory()
        self._env_anterior = dict(os.environ)
        os.environ["CLAUDE_USER_HOME"] = self.tmp_usuario.name

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env_anterior)
        self.tmp.cleanup()
        self.tmp_usuario.cleanup()

    def test_autor_do_nivel_de_usuario_chega_ao_html_gerado(self):
        # projeto define o nome, mas deixa autoria em branco
        caminho_projeto = self.raiz / ".claude" / "plugins-data" / "kbr-docs" / "docs-brand.yml"
        caminho_projeto.parent.mkdir(parents=True)
        caminho_projeto.write_text(
            'projeto:\n  nome: "Projeto X"\n'
            'logo:\n  claro: ""\n  escuro: ""\n'
            'marca:\n  claro:\n    brand: "#336699"\n'
            '  escuro:\n    brand: "#5C9BC9"\n'
            'textos:\n  rodape: "rodape"\n'
            'autoria:\n  autor: ""\n'
            'contato:\n  email: ""\n'
            'tipografia:\n  fontes_externas: true\n',
            encoding="utf-8")

        # usuario define o autor
        caminho_usuario = Path(self.tmp_usuario.name) / ".claude" / "plugins-data" / "kbr-docs" / "docs-brand.yml"
        caminho_usuario.parent.mkdir(parents=True)
        caminho_usuario.write_text('autoria:\n  autor: "Autor Pessoal"\n', encoding="utf-8")

        destino = self.raiz / "saida"
        codigo, saida, _ = _rodar(str(destino), f"--raiz={self.raiz}")
        self.assertEqual(codigo, 0)
        html = (destino / "index.html").read_text(encoding="utf-8")
        self.assertIn("Autor Pessoal", html)
        self.assertIn("nível de usuário", saida)  # citado no relatório
