# -*- coding: utf-8 -*-
"""Testes da descoberta de marca (descobrir.py)."""
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RAIZ_PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ_PLUGIN / "skills" / "report-creator" / "scripts"))
import descobrir  # noqa: E402


def _rodar(*argumentos):
    argv_original = sys.argv
    sys.argv = ["descobrir.py", *argumentos]
    saida, erro = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(saida), contextlib.redirect_stderr(erro):
            codigo = descobrir.main()
    finally:
        sys.argv = argv_original
    return codigo, saida.getvalue(), erro.getvalue()


class TesteAcharLogos(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _criar(self, relativo: str, conteudo: str = "x"):
        caminho = self.raiz / relativo
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(conteudo, encoding="utf-8")
        return caminho

    def test_ignora_pastas_de_dependencia(self):
        self._criar("node_modules/pacote/logo.svg")
        self._criar("assets/logo.svg")
        achados = [a["caminho"] for a in descobrir.achar_logos(self.raiz)]
        self.assertEqual(achados, ["assets/logo.svg"])

    def test_acha_por_padrao_no_nome_mas_nao_qualquer_imagem(self):
        self._criar("assets/brand-mark.png")
        self._criar("assets/icone-generico.png")
        achados = {a["caminho"] for a in descobrir.achar_logos(self.raiz)}
        self.assertIn("assets/brand-mark.png", achados)
        self.assertNotIn("assets/icone-generico.png", achados)

    def test_ignora_extensao_fora_da_lista(self):
        self._criar("assets/logo.gif")
        self._criar("assets/logo.svg")
        achados = {a["caminho"] for a in descobrir.achar_logos(self.raiz)}
        self.assertEqual(achados, {"assets/logo.svg"})


class TesteCorDeSvg(unittest.TestCase):
    def test_pega_a_cor_mais_repetida_ignorando_neutras(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "logo.svg"
            caminho.write_text(
                '<svg><rect fill="#336699"/><rect fill="#336699"/>'
                '<rect fill="#112233"/></svg>', encoding="utf-8")
            self.assertEqual(descobrir.cor_de_svg(caminho), "#336699")

    def test_sem_cor_valida_devolve_none(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "logo.svg"
            caminho.write_text('<svg><rect fill="#FFFFFF"/></svg>', encoding="utf-8")
            self.assertIsNone(descobrir.cor_de_svg(caminho))


class TesteEscolherPar(unittest.TestCase):
    def test_por_nome_do_arquivo(self):
        logos = [
            {"caminho": "logo-branco.svg", "nome": "logo-branco.svg", "bytes": 1,
             "luminancia": None, "cor": None},
            {"caminho": "logo-preto.svg", "nome": "logo-preto.svg", "bytes": 1,
             "luminancia": None, "cor": None},
        ]
        claro, escuro = descobrir.escolher_par(logos)
        self.assertEqual(claro["nome"], "logo-preto.svg")
        self.assertEqual(escuro["nome"], "logo-branco.svg")

    def test_por_luminancia_no_empate_de_nome(self):
        logos = [
            {"caminho": "a.png", "nome": "a.png", "bytes": 1, "luminancia": 0.9, "cor": None},
            {"caminho": "b.png", "nome": "b.png", "bytes": 1, "luminancia": 0.1, "cor": None},
        ]
        claro, escuro = descobrir.escolher_par(logos)
        self.assertEqual(claro["nome"], "b.png")   # mais escuro → sobre papel
        self.assertEqual(escuro["nome"], "a.png")  # mais claro → sobre fundo escuro

    def test_sem_logo_nenhum(self):
        self.assertEqual(descobrir.escolher_par([]), (None, None))


class TesteNomeDoProjeto(unittest.TestCase):
    def test_de_package_json(self):
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            (raiz / "package.json").write_text('{"name": "meu-projeto"}', encoding="utf-8")
            nome, origem = descobrir.nome_do_projeto(raiz)
            self.assertEqual(nome, "meu-projeto")
            self.assertEqual(origem, "package.json")

    def test_de_claude_md_quando_sem_package_json(self):
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            (raiz / "CLAUDE.md").write_text("# Meu Projeto\n\ntexto", encoding="utf-8")
            nome, origem = descobrir.nome_do_projeto(raiz)
            self.assertEqual(nome, "Meu Projeto")
            self.assertEqual(origem, "CLAUDE.md")

    def test_cai_no_nome_da_pasta(self):
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            nome, origem = descobrir.nome_do_projeto(raiz)
            self.assertEqual(nome, raiz.name)
            self.assertEqual(origem, "nome da pasta")


class TesteSemPillow(unittest.TestCase):
    def test_luminancia_sem_pillow_devolve_none(self):
        with mock.patch.dict(sys.modules, {"PIL": None}):
            with tempfile.TemporaryDirectory() as pasta:
                caminho = Path(pasta) / "logo.png"
                caminho.write_bytes(b"nao e um png de verdade")
                self.assertIsNone(descobrir.luminancia_media(caminho))

    def test_cor_dominante_de_png_sem_pillow_devolve_none(self):
        with mock.patch.dict(sys.modules, {"PIL": None}):
            with tempfile.TemporaryDirectory() as pasta:
                caminho = Path(pasta) / "logo.png"
                caminho.write_bytes(b"nao e um png de verdade")
                self.assertIsNone(descobrir.cor_dominante(caminho))


class TesteMontarYaml(unittest.TestCase):
    def test_produz_as_secoes_esperadas(self):
        texto = descobrir.montar_yaml(
            Path("/tmp/projeto-x"), "Projeto X", "CLAUDE.md",
            {"caminho": "assets/logo-claro.svg", "cor": "#336699"},
            {"caminho": "assets/logo-escuro.svg", "cor": None})
        for secao in ("projeto:", "logo:", "marca:", "textos:", "autoria:",
                     "contato:", "tipografia:", "saida:"):
            self.assertIn(secao, texto)
        self.assertIn('nome: "Projeto X"', texto)
        self.assertIn('claro: "assets/logo-claro.svg"', texto)
        self.assertIn('brand: "#336699"', texto)

    def test_nao_cita_as_skills_antigas_separadas(self):
        texto = descobrir.montar_yaml(
            Path("/tmp/projeto-x"), "Projeto X", "CLAUDE.md",
            {"caminho": "assets/logo-claro.svg", "cor": "#336699"},
            {"caminho": "assets/logo-escuro.svg", "cor": None})
        self.assertNotIn("docs-html", texto)
        self.assertNotIn("docs-init", texto)
        self.assertIn("report-creator", texto)


class TesteMain(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_modo_leitura_nao_grava_nada(self):
        codigo, saida, _ = _rodar(str(self.raiz))
        self.assertEqual(codigo, 0)
        self.assertIn("raiz do projeto", saida)
        self.assertFalse((self.raiz / ".docs-brand.yml").exists())

    def test_escrever_grava_o_arquivo(self):
        codigo, saida, _ = _rodar(str(self.raiz), "--escrever")
        self.assertEqual(codigo, 0)
        destino = self.raiz / ".docs-brand.yml"
        self.assertTrue(destino.exists())
        self.assertIn("escrito:", saida)

    def test_nunca_sobrescreve_arquivo_existente(self):
        destino = self.raiz / ".docs-brand.yml"
        destino.write_text("conteudo original\n", encoding="utf-8")
        codigo, saida, _ = _rodar(str(self.raiz), "--escrever")
        self.assertEqual(codigo, 1)
        self.assertEqual(destino.read_text(encoding="utf-8"), "conteudo original\n")
