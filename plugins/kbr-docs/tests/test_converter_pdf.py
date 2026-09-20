# -*- coding: utf-8 -*-
"""Testes de converter_pdf.py: conversão de HTML local em PDF via navegador."""
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RAIZ_PLUGIN = Path(__file__).resolve().parents[1]
SCRIPTS = RAIZ_PLUGIN / "skills" / "report-creator" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import converter_pdf  # noqa: E402


def _navegador_disponivel() -> bool:
    try:
        converter_pdf.achar_navegador()
        return True
    except converter_pdf.ErroNavegadorNaoEncontrado:
        return False


HTML_MINIMO = (
    '<!doctype html><html><head><meta charset="utf-8"><title>Teste</title></head>'
    '<body><h1>Teste</h1><p>Página mínima para o converter_pdf.py.</p></body></html>'
)


class TesteAcharNavegador(unittest.TestCase):
    def setUp(self):
        self._env_anterior = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env_anterior)

    def test_kbr_docs_browser_valido_e_usado_direto(self):
        with tempfile.TemporaryDirectory() as tmp:
            falso_navegador = Path(tmp) / "navegador.exe"
            falso_navegador.write_text("", encoding="utf-8")
            os.environ["KBR_DOCS_BROWSER"] = str(falso_navegador)
            achado = converter_pdf.achar_navegador()
            self.assertEqual(achado, falso_navegador)

    def test_kbr_docs_browser_invalido_nao_cai_para_o_resto(self):
        os.environ["KBR_DOCS_BROWSER"] = "C:/caminho/que/nao/existe/navegador.exe"
        with self.assertRaises(converter_pdf.ErroNavegadorNaoEncontrado) as ctx:
            converter_pdf.achar_navegador()
        self.assertIn("KBR_DOCS_BROWSER", str(ctx.exception))

    @unittest.skipUnless(_navegador_disponivel(), "nenhum navegador Chromium encontrado")
    def test_acha_algum_navegador_de_verdade_nesta_maquina(self):
        os.environ.pop("KBR_DOCS_BROWSER", None)
        achado = converter_pdf.achar_navegador()
        self.assertTrue(achado.exists())


class TesteConverter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self.tmp.name)
        self.entrada = self.raiz / "teste.html"
        self.entrada.write_text(HTML_MINIMO, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    @unittest.skipUnless(_navegador_disponivel(), "nenhum navegador Chromium encontrado")
    def test_converte_html_real_em_pdf_valido(self):
        navegador = converter_pdf.achar_navegador()
        saida = self.raiz / "teste.pdf"
        converter_pdf.converter(self.entrada, saida, navegador)
        self.assertTrue(saida.exists())
        with open(saida, "rb") as f:
            assinatura = f.read(5)
        self.assertEqual(assinatura, b"%PDF-")

    def test_navegador_inexistente_levanta_erro_de_conversao(self):
        navegador_falso = self.raiz / "nao-existe.exe"
        saida = self.raiz / "teste.pdf"
        with self.assertRaises(converter_pdf.ErroConversao):
            converter_pdf.converter(self.entrada, saida, navegador_falso)


class TesteConverterErrosDoProcesso(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self.tmp.name)
        self.entrada = self.raiz / "teste.html"
        self.entrada.write_text(HTML_MINIMO, encoding="utf-8")
        self.navegador_falso = self.raiz / "navegador-falso.exe"
        self.navegador_falso.write_text("", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_returncode_diferente_de_zero_levanta_erro(self):
        saida = self.raiz / "teste.pdf"
        resultado_falso = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="deu erro na renderizacao")
        with mock.patch("converter_pdf.subprocess.run", return_value=resultado_falso):
            with self.assertRaises(converter_pdf.ErroConversao) as ctx:
                converter_pdf.converter(self.entrada, saida, self.navegador_falso)
        self.assertIn("código 1", str(ctx.exception))

    def test_sucesso_sem_arquivo_gerado_levanta_erro(self):
        saida = self.raiz / "teste.pdf"  # nunca criado, propositalmente
        resultado_falso = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr="")
        with mock.patch("converter_pdf.subprocess.run", return_value=resultado_falso):
            with self.assertRaises(converter_pdf.ErroConversao) as ctx:
                converter_pdf.converter(self.entrada, saida, self.navegador_falso)
        self.assertIn("não foi criado", str(ctx.exception))

    def test_saida_igual_a_entrada_levanta_erro(self):
        with self.assertRaises(converter_pdf.ErroConversao) as ctx:
            converter_pdf.converter(self.entrada, self.entrada, self.navegador_falso)
        self.assertIn("mesmo arquivo", str(ctx.exception))

    def test_entrada_inexistente_levanta_erro_direto_no_converter(self):
        entrada_falsa = self.raiz / "nao-existe.html"
        saida = self.raiz / "teste.pdf"
        with self.assertRaises(converter_pdf.ErroConversao) as ctx:
            converter_pdf.converter(entrada_falsa, saida, self.navegador_falso)
        self.assertIn("não existe", str(ctx.exception))

    def test_pdf_antigo_no_mesmo_caminho_nao_engana_a_checagem(self):
        saida = self.raiz / "teste.pdf"
        saida.write_bytes(b"PDF ANTIGO, NAO DEVE SOBREVIVER")
        resultado_falso = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        with mock.patch("converter_pdf.subprocess.run", return_value=resultado_falso):
            with self.assertRaises(converter_pdf.ErroConversao) as ctx:
                converter_pdf.converter(self.entrada, saida, self.navegador_falso)
        self.assertIn("não foi criado", str(ctx.exception))

    def test_comando_escapa_caracteres_especiais_na_url(self):
        entrada_especial = self.raiz / "chamado #4845.html"
        entrada_especial.write_text(HTML_MINIMO, encoding="utf-8")
        saida = self.raiz / "saida.pdf"

        def _run_falso(comando, **kwargs):
            saida.write_bytes(b"%PDF-1.4 fake")
            return subprocess.CompletedProcess(args=comando, returncode=0, stdout="", stderr="")

        with mock.patch("converter_pdf.subprocess.run", side_effect=_run_falso) as mock_run:
            converter_pdf.converter(entrada_especial, saida, self.navegador_falso)
        comando = mock_run.call_args.args[0]
        url = comando[-1]
        self.assertTrue(url.startswith("file:///"))
        self.assertIn("%23", url)
        self.assertNotIn(" ", url)
        self.assertIn("--headless", comando)
        self.assertIn("--no-pdf-header-footer", comando)

    def test_retenta_sem_sandbox_quando_falha_por_sandbox(self):
        saida = self.raiz / "saida.pdf"
        chamadas = []

        def _run_falso(comando, **kwargs):
            chamadas.append(comando)
            if "--no-sandbox" not in comando:
                return subprocess.CompletedProcess(
                    args=comando, returncode=1, stdout="",
                    stderr="[FATAL] No usable sandbox! Ver documentacao do Chromium.")
            saida.write_bytes(b"%PDF-1.4 fake")
            return subprocess.CompletedProcess(args=comando, returncode=0, stdout="", stderr="")

        with mock.patch("converter_pdf.subprocess.run", side_effect=_run_falso):
            converter_pdf.converter(self.entrada, saida, self.navegador_falso)
        self.assertEqual(len(chamadas), 2)
        self.assertNotIn("--no-sandbox", chamadas[0])
        self.assertIn("--no-sandbox", chamadas[1])
        self.assertTrue(saida.exists())

    def test_nao_retenta_quando_falha_por_outro_motivo(self):
        saida = self.raiz / "saida.pdf"
        chamadas = []

        def _run_falso(comando, **kwargs):
            chamadas.append(comando)
            return subprocess.CompletedProcess(
                args=comando, returncode=1, stdout="", stderr="algum outro erro qualquer")

        with mock.patch("converter_pdf.subprocess.run", side_effect=_run_falso):
            with self.assertRaises(converter_pdf.ErroConversao):
                converter_pdf.converter(self.entrada, saida, self.navegador_falso)
        self.assertEqual(len(chamadas), 1)


def _rodar(*args):
    argv_antigo = sys.argv
    sys.argv = ["converter_pdf.py", *args]
    saida_antiga, erro_antigo = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = io.StringIO(), io.StringIO()
    try:
        codigo = converter_pdf.main()
    finally:
        saida_txt = sys.stdout.getvalue()
        erro_txt = sys.stderr.getvalue()
        sys.stdout, sys.stderr = saida_antiga, erro_antigo
        sys.argv = argv_antigo
    return codigo, saida_txt, erro_txt


class TesteMain(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self.tmp.name)
        self.entrada = self.raiz / "teste.html"
        self.entrada.write_text(HTML_MINIMO, encoding="utf-8")
        self._env_anterior = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env_anterior)
        self.tmp.cleanup()

    def test_sem_argumento_mostra_ajuda_e_sai_com_codigo_2(self):
        codigo, _, _ = _rodar()
        self.assertEqual(codigo, 2)

    def test_entrada_inexistente_sai_com_codigo_1(self):
        codigo, _, erro = _rodar(str(self.raiz / "nao-existe.html"))
        self.assertEqual(codigo, 1)
        self.assertIn("Não achei", erro)

    def test_kbr_docs_browser_invalido_sai_com_codigo_1(self):
        os.environ["KBR_DOCS_BROWSER"] = str(self.raiz / "nao-existe.exe")
        codigo, _, erro = _rodar(str(self.entrada))
        self.assertEqual(codigo, 1)
        self.assertIn("KBR_DOCS_BROWSER", erro)

    @unittest.skipUnless(_navegador_disponivel(), "nenhum navegador Chromium encontrado")
    def test_conversao_completa_via_main_gera_pdf_valido(self):
        saida = self.raiz / "saida.pdf"
        codigo, texto_saida, _ = _rodar(str(self.entrada), str(saida))
        self.assertEqual(codigo, 0)
        self.assertTrue(saida.exists())
        with open(saida, "rb") as f:
            assinatura = f.read(5)
        self.assertEqual(assinatura, b"%PDF-")
        self.assertIn(str(saida.resolve()), texto_saida)

    @unittest.skipUnless(_navegador_disponivel(), "nenhum navegador Chromium encontrado")
    def test_sem_saida_explicita_usa_mesmo_nome_com_pdf(self):
        codigo, _, _ = _rodar(str(self.entrada))
        self.assertEqual(codigo, 0)
        esperado = self.entrada.with_suffix(".pdf")
        self.assertTrue(esperado.exists())


if __name__ == "__main__":
    unittest.main()
