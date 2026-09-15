# -*- coding: utf-8 -*-
"""Testes da cascata de config (resolver_marca.py): projeto -> usuario -> vazio."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ_PLUGIN = Path(__file__).resolve().parents[1]
SCRIPTS = RAIZ_PLUGIN / "skills" / "report-creator" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import resolver_marca  # noqa: E402


class BaseComRaizEUsuario(unittest.TestCase):
    """Isola tanto a raiz do projeto (tempdir) quanto o nivel de usuario
    (CLAUDE_USER_HOME) -- nunca toca no ~/.claude real."""

    def setUp(self):
        self.tmp_raiz = tempfile.TemporaryDirectory()
        self.raiz = Path(self.tmp_raiz.name)
        self.tmp_usuario = tempfile.TemporaryDirectory()
        self._env_anterior = dict(os.environ)
        os.environ["CLAUDE_USER_HOME"] = self.tmp_usuario.name

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env_anterior)
        self.tmp_raiz.cleanup()
        self.tmp_usuario.cleanup()

    def _gravar_projeto(self, texto: str, legado: bool = False) -> Path:
        caminho = (resolver_marca.caminho_projeto_legado(self.raiz) if legado
                   else resolver_marca.caminho_projeto(self.raiz))
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(texto, encoding="utf-8")
        return caminho

    def _gravar_usuario(self, texto: str) -> Path:
        caminho = resolver_marca.caminho_usuario()
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(texto, encoding="utf-8")
        return caminho


class TesteNenhumNivelConfigurado(BaseComRaizEUsuario):
    def test_verdadeiro_quando_nao_ha_nenhum_arquivo(self):
        self.assertTrue(resolver_marca.nenhum_nivel_configurado(self.raiz))

    def test_falso_quando_so_o_projeto_canonico_existe(self):
        self._gravar_projeto('projeto:\n  nome: "X"\n')
        self.assertFalse(resolver_marca.nenhum_nivel_configurado(self.raiz))

    def test_falso_quando_so_o_legado_existe(self):
        self._gravar_projeto('projeto:\n  nome: "X"\n', legado=True)
        self.assertFalse(resolver_marca.nenhum_nivel_configurado(self.raiz))

    def test_falso_quando_so_o_usuario_existe(self):
        self._gravar_usuario('autoria:\n  autor: "Fulano"\n')
        self.assertFalse(resolver_marca.nenhum_nivel_configurado(self.raiz))


class TesteResolverMescla(BaseComRaizEUsuario):
    def test_projeto_com_tudo_preenchido_ignora_usuario(self):
        self._gravar_projeto(
            'projeto:\n  nome: "Projeto"\n'
            'autoria:\n  autor: "Do Projeto"\n')
        self._gravar_usuario('autoria:\n  autor: "Do Usuario"\n')
        efetivo, notas = resolver_marca.resolver(self.raiz)
        self.assertEqual(efetivo["autoria"]["autor"], "Do Projeto")
        self.assertEqual(notas, [])

    def test_projeto_vazio_usa_usuario_por_completo(self):
        self._gravar_projeto('autoria:\n  autor: ""\n  cargo: ""\n')
        self._gravar_usuario('autoria:\n  autor: "Do Usuario"\n  cargo: "Arquiteto"\n')
        efetivo, _ = resolver_marca.resolver(self.raiz)
        self.assertEqual(efetivo["autoria"]["autor"], "Do Usuario")
        self.assertEqual(efetivo["autoria"]["cargo"], "Arquiteto")

    def test_mescla_campo_a_campo_dentro_da_mesma_secao(self):
        self._gravar_projeto('autoria:\n  autor: "Do Projeto"\n  cargo: ""\n')
        self._gravar_usuario('autoria:\n  autor: "Do Usuario"\n  cargo: "Arquiteto"\n')
        efetivo, _ = resolver_marca.resolver(self.raiz)
        self.assertEqual(efetivo["autoria"]["autor"], "Do Projeto")   # projeto vence
        self.assertEqual(efetivo["autoria"]["cargo"], "Arquiteto")    # cai pro usuario

    def test_mescla_recursiva_dentro_de_marca_claro(self):
        self._gravar_projeto(
            'marca:\n  claro:\n    brand: "#111111"\n    hover: ""\n')
        self._gravar_usuario(
            'marca:\n  claro:\n    brand: "#222222"\n    hover: "#333333"\n    tint: "#444444"\n')
        efetivo, _ = resolver_marca.resolver(self.raiz)
        self.assertEqual(efetivo["marca"]["claro"]["brand"], "#111111")  # projeto vence
        self.assertEqual(efetivo["marca"]["claro"]["hover"], "#333333")  # cai pro usuario
        self.assertEqual(efetivo["marca"]["claro"]["tint"], "#444444")   # so existe no usuario

    def test_booleano_false_do_projeto_nao_e_tratado_como_vazio(self):
        self._gravar_projeto('tipografia:\n  fontes_externas: false\n')
        self._gravar_usuario('tipografia:\n  fontes_externas: true\n')
        efetivo, _ = resolver_marca.resolver(self.raiz)
        self.assertIs(efetivo["tipografia"]["fontes_externas"], False)

    def test_nenhum_dos_dois_niveis_devolve_dict_vazio(self):
        efetivo, notas = resolver_marca.resolver(self.raiz)
        self.assertEqual(efetivo, {})
        self.assertEqual(notas, [])

    def test_canonico_vence_o_legado_sem_mesclar_com_ele(self):
        self._gravar_projeto('autoria:\n  autor: ""\n', legado=True)
        self._gravar_projeto('autoria:\n  cargo: "Do Canonico"\n')  # canonico, sem 'autor'
        efetivo, _ = resolver_marca.resolver(self.raiz)
        self.assertEqual(efetivo["autoria"]["cargo"], "Do Canonico")
        self.assertNotIn("autor", efetivo.get("autoria", {}))  # nao veio do legado

    def test_so_legado_ainda_funciona_retrocompatibilidade(self):
        self._gravar_projeto('projeto:\n  nome: "Projeto Legado"\n', legado=True)
        efetivo, _ = resolver_marca.resolver(self.raiz)
        self.assertEqual(efetivo["projeto"]["nome"], "Projeto Legado")


class TesteCaminhoDeArquivoAbsolutizado(BaseComRaizEUsuario):
    def test_logo_do_usuario_resolve_contra_a_pasta_do_usuario(self):
        logo_usuario = resolver_marca.caminho_usuario().parent / "minha-logo.svg"
        logo_usuario.parent.mkdir(parents=True, exist_ok=True)
        logo_usuario.write_text("<svg></svg>", encoding="utf-8")
        self._gravar_projeto('logo:\n  claro: ""\n')
        self._gravar_usuario('logo:\n  claro: "minha-logo.svg"\n')
        efetivo, notas = resolver_marca.resolver(self.raiz)
        caminho_resolvido = Path(efetivo["logo"]["claro"])
        self.assertTrue(caminho_resolvido.is_absolute())
        self.assertEqual(caminho_resolvido, logo_usuario.resolve())
        self.assertTrue(any("logo.claro" in n for n in notas))

    def test_logo_do_projeto_resolve_contra_a_raiz_do_projeto(self):
        logo_projeto = self.raiz / "assets" / "logo.svg"
        logo_projeto.parent.mkdir(parents=True)
        logo_projeto.write_text("<svg></svg>", encoding="utf-8")
        self._gravar_projeto('logo:\n  claro: "assets/logo.svg"\n')
        efetivo, notas = resolver_marca.resolver(self.raiz)
        self.assertEqual(Path(efetivo["logo"]["claro"]), logo_projeto.resolve())
        self.assertEqual(notas, [])  # veio do projeto, sem nota de nivel

    def test_avatar_vazio_nos_dois_niveis_fica_vazio(self):
        self._gravar_projeto('autoria:\n  avatar: ""\n')
        efetivo, _ = resolver_marca.resolver(self.raiz)
        self.assertEqual(efetivo["autoria"]["avatar"], "")


if __name__ == "__main__":
    unittest.main()
