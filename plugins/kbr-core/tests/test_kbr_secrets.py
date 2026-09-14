# -*- coding: utf-8 -*-
"""Testes do módulo de segredos — parser do .env e ordem de resolução."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

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
        self._rodar_op_original = kbr_secrets._rodar_op

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env_anterior)
        self.tmp.cleanup()
        kbr_secrets._rodar_op = self._rodar_op_original

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


class OpFalso:
    """Substitui subprocess.run para o comando op, registrando as chamadas."""

    def __init__(self, saida="", erro="", codigo=0, ausente=False):
        self.saida, self.erro, self.codigo, self.ausente = saida, erro, codigo, ausente
        self.chamadas = []

    def __call__(self, argumentos, **kwargs):
        if self.ausente:
            raise FileNotFoundError("op")
        self.chamadas.append(list(argumentos))
        return SimpleNamespace(returncode=self.codigo, stdout=self.saida, stderr=self.erro)


class TesteOnePassword(BaseTemporaria):
    def test_resolve_referencia(self):
        self.escrever("SDP_CLIENT_ID=op://Kinto Brasil/Item SDP/client-id\n")
        falso = OpFalso(saida="valor-do-cofre\n")
        kbr_secrets._rodar_op = falso
        self.assertEqual(kbr_secrets.obter("SDP_CLIENT_ID"), "valor-do-cofre")
        self.assertEqual(falso.chamadas[0],
                         ["read", "op://Kinto Brasil/Item SDP/client-id"])

    def test_cacheia_por_processo(self):
        self.escrever("SDP_CLIENT_ID=op://Cofre/Item/campo\n")
        falso = OpFalso(saida="valor\n")
        kbr_secrets._rodar_op = falso
        kbr_secrets.obter("SDP_CLIENT_ID")
        kbr_secrets.obter("SDP_CLIENT_ID")
        self.assertEqual(len(falso.chamadas), 1)

    def test_op_ausente_gera_erro_em_portugues(self):
        self.escrever("SDP_CLIENT_ID=op://Cofre/Item/campo\n")
        kbr_secrets._rodar_op = OpFalso(ausente=True)
        with self.assertRaises(kbr_secrets.SegredoInacessivel) as caso:
            kbr_secrets.obter("SDP_CLIENT_ID")
        self.assertIn("não está instalado", str(caso.exception))

    def test_op_com_erro_usa_so_a_primeira_linha(self):
        self.escrever("SDP_CLIENT_ID=op://Cofre/Item/campo\n")
        kbr_secrets._rodar_op = OpFalso(
            codigo=1, erro="cofre bloqueado\nlinha dois\nlinha três")
        with self.assertRaises(kbr_secrets.SegredoInacessivel) as caso:
            kbr_secrets.obter("SDP_CLIENT_ID")
        self.assertIn("cofre bloqueado", str(caso.exception))
        self.assertNotIn("linha três", str(caso.exception))

    def test_valor_vazio_do_cofre_gera_erro(self):
        self.escrever("SDP_CLIENT_ID=op://Cofre/Item/campo\n")
        kbr_secrets._rodar_op = OpFalso(saida="   \n")
        with self.assertRaises(kbr_secrets.SegredoInacessivel):
            kbr_secrets.obter("SDP_CLIENT_ID")

    def test_referencia_mal_formada(self):
        self.escrever("SDP_CLIENT_ID=op://so-uma-parte\n")
        kbr_secrets._rodar_op = OpFalso(saida="x")
        with self.assertRaises(kbr_secrets.SegredoInacessivel) as caso:
            kbr_secrets.obter("SDP_CLIENT_ID")
        self.assertIn("mal formada", str(caso.exception))

    def test_gravar_em_chave_literal_altera_o_arquivo(self):
        self.escrever("# cabeçalho\nSDP_REFRESH_TOKEN=antigo\nOUTRA=x\n")
        kbr_secrets.gravar("SDP_REFRESH_TOKEN", "novo")
        texto = kbr_secrets.caminho_arquivo().read_text(encoding="utf-8")
        self.assertIn("SDP_REFRESH_TOKEN=novo", texto)
        self.assertIn("# cabeçalho", texto)
        self.assertIn("OUTRA=x", texto)

    def test_gravar_chave_inexistente_acrescenta(self):
        self.escrever("A=1\n")
        kbr_secrets.gravar("B", "2")
        self.assertEqual(kbr_secrets.ler_arquivo()["B"], "2")

    def test_gravar_em_chave_op_vai_para_o_cofre(self):
        self.escrever("SDP_REFRESH_TOKEN=op://Kinto Brasil/Item SDP/refresh-token\n")
        falso = OpFalso(saida="ok")
        kbr_secrets._rodar_op = falso
        kbr_secrets.gravar("SDP_REFRESH_TOKEN", "token-novo")
        self.assertEqual(falso.chamadas[0], [
            "item", "edit", "Item SDP", "--vault", "Kinto Brasil",
            "refresh-token=token-novo"])

    def test_gravar_em_chave_op_preserva_a_referencia(self):
        self.escrever("SDP_REFRESH_TOKEN=op://Cofre/Item/campo\n")
        kbr_secrets._rodar_op = OpFalso(saida="ok")
        kbr_secrets.gravar("SDP_REFRESH_TOKEN", "token-novo")
        texto = kbr_secrets.caminho_arquivo().read_text(encoding="utf-8")
        self.assertIn("op://Cofre/Item/campo", texto)
        self.assertNotIn("token-novo", texto)

    def test_referencia_com_espacos_e_normalizada(self):
        self.escrever("SDP_CLIENT_ID=op:// Cofre / Item /campo\n")
        falso = OpFalso(saida="valor\n")
        kbr_secrets._rodar_op = falso
        kbr_secrets.obter("SDP_CLIENT_ID")
        # a referência chega ao `op read` como veio; o que importa é que as partes
        # extraídas para o `op item edit` não carreguem espaço
        self.assertEqual(kbr_secrets._partes_op("op:// Cofre / Item /campo", "X"),
                         ("Cofre", "Item", "campo"))

    def test_op_disponivel_reflete_o_path(self):
        import shutil
        original = shutil.which
        try:
            shutil.which = lambda nome: "/usr/bin/op" if nome == "op" else None
            self.assertTrue(kbr_secrets.op_disponivel())
            shutil.which = lambda nome: None
            self.assertFalse(kbr_secrets.op_disponivel())
        finally:
            shutil.which = original


class TesteInitERegistrar(BaseTemporaria):
    def setUp(self):
        super().setUp()
        # init cria a própria pasta; começa sem ela
        for filho in sorted(self.base.rglob("*"), reverse=True):
            filho.unlink() if filho.is_file() else filho.rmdir()
        self.base.rmdir()

    def executar(self, *argumentos):
        return kbr_secrets.main(list(argumentos))

    def test_init_cria_estrutura(self):
        self.assertEqual(self.executar("init"), 0)
        self.assertTrue(kbr_secrets.caminho_arquivo().is_file())
        self.assertTrue(kbr_secrets.caminho_config().is_file())
        self.assertTrue(kbr_secrets.caminho_cache().is_dir())

    def test_init_escreve_o_cabecalho(self):
        self.executar("init")
        texto = kbr_secrets.caminho_arquivo().read_text(encoding="utf-8")
        self.assertIn("fica fora do git", texto)

    def test_init_e_idempotente_e_nao_apaga_valores(self):
        self.executar("init")
        kbr_secrets.gravar("A", "valor-importante")
        self.executar("init")
        self.assertEqual(kbr_secrets.ler_arquivo()["A"], "valor-importante")

    def test_registrar_acrescenta_chaves_vazias(self):
        self.executar("init")
        self.executar("registrar", "--plugin", "kbr-servicedesk",
                      "--chaves", "SDP_CLIENT_ID,SDP_CLIENT_SECRET")
        valores = kbr_secrets.ler_arquivo()
        self.assertEqual(valores["SDP_CLIENT_ID"], "")
        self.assertEqual(valores["SDP_CLIENT_SECRET"], "")

    def test_registrar_escreve_a_marca_do_plugin(self):
        self.executar("init")
        self.executar("registrar", "--plugin", "kbr-servicedesk", "--chaves", "SDP_A")
        texto = kbr_secrets.caminho_arquivo().read_text(encoding="utf-8")
        self.assertIn("# --- kbr-servicedesk ---", texto)

    def test_registrar_e_idempotente(self):
        self.executar("init")
        self.executar("registrar", "--plugin", "p", "--chaves", "A,B")
        self.executar("registrar", "--plugin", "p", "--chaves", "A,B")
        texto = kbr_secrets.caminho_arquivo().read_text(encoding="utf-8")
        self.assertEqual(texto.count("A="), 1)
        self.assertEqual(texto.count("# --- p ---"), 1)

    def test_registrar_nao_apaga_valor_existente(self):
        self.executar("init")
        self.executar("registrar", "--plugin", "p", "--chaves", "A")
        kbr_secrets.gravar("A", "ja-preenchido")
        self.executar("registrar", "--plugin", "p", "--chaves", "A,B")
        self.assertEqual(kbr_secrets.ler_arquivo()["A"], "ja-preenchido")

    def test_registrar_roda_o_init_sozinho(self):
        self.assertEqual(self.executar("registrar", "--plugin", "p", "--chaves", "A"), 0)
        self.assertTrue(kbr_secrets.caminho_arquivo().is_file())

    @unittest.skipIf(os.name == "nt", "modo POSIX")
    def test_permissoes_posix(self):
        self.executar("init")
        self.assertEqual(kbr_secrets.caminho_base().stat().st_mode & 0o777, 0o700)
        self.assertEqual(kbr_secrets.caminho_arquivo().stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
