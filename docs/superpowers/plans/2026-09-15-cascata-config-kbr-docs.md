# Cascata de config projeto/usuário/plugin (kbr-docs) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fazer o `kbr-docs` resolver cada campo de marca numa cascata de três níveis — projeto (`.claude/plugins-data/kbr-docs/`, com retrocompatibilidade pro `.docs-brand.yml` legado da raiz) → usuário (`~/.claude/plugins-data/kbr-docs/`) → placeholder do plugin (só logo) — em vez de olhar só pro arquivo da raiz do projeto.

**Architecture:** Um módulo novo, `resolver_marca.py`, dentro do mesmo `scripts/` dos outros dois scripts do plugin (é código dividido dentro do MESMO plugin — não é o caso da regra "plugin autocontido", que é sobre não ler arquivo de OUTRO plugin). Ele passa a ser o dono do parser de YAML (movido de `aplicar_marca.py`, que passa a importar de lá) e ganha a lógica de mescla campo a campo + resolução de caminho de arquivo relativo à pasta de origem. `descobrir.py` e `aplicar_marca.py` passam a chamar esse módulo em vez de ler o arquivo direto.

**Tech Stack:** Python ≥ 3.10, só biblioteca padrão (nenhuma dependência nova). Testes com `unittest`, mesmo padrão de isolamento por variável de ambiente (`KBR_HOME`) que o `kbr-core` já usa pra `~/.kbr` — aqui a variável nova é `CLAUDE_USER_HOME`, pra nunca tocar no `~/.claude` real durante os testes.

## Global Constraints

- Spec aprovada: `docs/superpowers/specs/2026-09-15-cascata-config-kbr-docs-design.md` — qualquer dúvida de comportamento, essa é a fonte da verdade.
- PT-BR em todo texto/comentário/docstring novo (regra do `CLAUDE.md` do repositório).
- Python ≥ 3.10, só biblioteca padrão — nenhum `pip install` novo.
- `python scripts/testar.py` e `python scripts/validar.py --strict`, rodados da raiz do repositório (`E:\Projetos\Kinto Brasil\src\github\KBR-Claude-Plugins`), precisam continuar limpos depois de CADA task.
- Trabalho direto na `main`, sem branch isolada — mesmo padrão já usado nas fatias anteriores do `kbr-docs` nesta sessão.
- Nenhum commit tem push — só local. Push e tag ficam pro Fábio decidir.
- **Nunca `git add -A`.** Nomeie os caminhos exatos.
- Mesclagem é campo a campo, recursiva: valor não-vazio no nível preferido sempre vence; string vazia (`""`) ou chave ausente cai pro próximo nível; **booleano nunca é tratado como "vazio"** (mesmo `false` — é um valor deliberado, não ausência de valor).
- Caminho de arquivo (`logo.claro`, `logo.escuro`, `autoria.avatar`) é absolutizado contra a pasta de onde ELE veio, ANTES da mescla — nunca contra a raiz do projeto quando vier do usuário.
- Nível de projeto: `<raiz>/.claude/plugins-data/kbr-docs/docs-brand.yml` (canônico); se não existir, `<raiz>/.docs-brand.yml` (legado — retrocompatibilidade, sem prazo pra sumir). Nível de usuário: `~/.claude/plugins-data/kbr-docs/docs-brand.yml` (ou `$CLAUDE_USER_HOME/.claude/plugins-data/kbr-docs/docs-brand.yml`, quando a variável de ambiente `CLAUDE_USER_HOME` estiver definida).
- Arquivos tocados, caminho completo a partir da raiz do repositório:
  - `plugins/kbr-docs/skills/report-creator/scripts/resolver_marca.py` (novo)
  - `plugins/kbr-docs/skills/report-creator/scripts/aplicar_marca.py`
  - `plugins/kbr-docs/skills/report-creator/scripts/descobrir.py`
  - `plugins/kbr-docs/skills/report-creator/SKILL.md`
  - `plugins/kbr-docs/tests/test_resolver_marca.py` (novo)
  - `plugins/kbr-docs/tests/test_aplicar_marca.py`
  - `plugins/kbr-docs/tests/test_descobrir.py`

---

### Task 1: Mover o parser de YAML pra `resolver_marca.py`

Só move código que já existe — zero mudança de comportamento. `aplicar_marca.py` passa a importar o parser em vez de defini-lo, então os testes que já existem (`TesteCarregarYamlSimples` em `test_aplicar_marca.py`, que chamam `aplicar_marca.carregar_yaml_simples(...)`) continuam passando sem alteração nenhuma — é reexportação, não remoção.

**Files:**
- Create: `plugins/kbr-docs/skills/report-creator/scripts/resolver_marca.py`
- Modify: `plugins/kbr-docs/skills/report-creator/scripts/aplicar_marca.py`

**Interfaces:**
- Produces: `resolver_marca.carregar_yaml_simples(texto: str) -> dict`, `resolver_marca.carregar_yaml(caminho: Path) -> dict` — as Tasks 2 e 3 usam essas duas.

- [ ] **Step 1: Criar `resolver_marca.py` com o parser movido**

Crie `plugins/kbr-docs/skills/report-creator/scripts/resolver_marca.py`:

```python
#!/usr/bin/env python3
"""
Resolve o config efetivo de marca do `kbr-docs` — por enquanto, só o parser de
YAML (movido de `aplicar_marca.py`). A cascata de três níveis entra na Task 2.
"""
from __future__ import annotations

from pathlib import Path


# --------------------------------------------------------------------- YAML --
def _dividir_comentario(linha: str) -> str:
    """Corta um comentário à direita (# fora de aspas). # dentro de "..." não conta."""
    dentro_de_aspas = False
    for i, ch in enumerate(linha):
        if ch == '"':
            dentro_de_aspas = not dentro_de_aspas
        elif ch == '#' and not dentro_de_aspas:
            return linha[:i]
    return linha


def _valor_escalar(bruto: str):
    """None quando a linha só abre um mapeamento aninhado (ex.: "marca:", sem valor)."""
    bruto = bruto.strip()
    if not bruto:
        return None
    if bruto.startswith('"') and bruto.endswith('"') and len(bruto) >= 2:
        return bruto[1:-1].replace('\\"', '"')
    minusculo = bruto.casefold()
    if minusculo in ('true', 'yes', 'on'):
        return True
    if minusculo in ('false', 'no', 'off'):
        return False
    return bruto


def carregar_yaml_simples(texto: str) -> dict:
    """
    Lê o subconjunto de YAML que `.docs-brand.yml` usa: mapeamentos aninhados até 3
    níveis, indentação de 2 espaços, valores entre aspas duplas ou booleano (`true`/
    `yes`/`on` e `false`/`no`/`off`, sem diferenciar maiúsculas), comentários com `#`
    (linha inteira ou à direita do valor, fora de aspas).

    Deliberadamente NÃO é um parser de YAML geral — feito para não exigir PyYAML (e
    portanto nenhum `pip install`) de quem usa o plugin. Não suporta lista, âncora,
    bloco multilinha, aspas simples nem chave com dois-pontos dentro do próprio nome.
    """
    raiz: dict = {}
    pilha: list[tuple[int, dict]] = [(-1, raiz)]
    for linha_bruta in texto.splitlines():
        sem_comentario = _dividir_comentario(linha_bruta)
        if not sem_comentario.strip():
            continue
        indent = len(sem_comentario) - len(sem_comentario.lstrip(' '))
        chave, _, resto = sem_comentario.strip().partition(':')
        chave = chave.strip()
        if not chave:
            continue
        while indent <= pilha[-1][0]:
            pilha.pop()
        atual = pilha[-1][1]
        valor = _valor_escalar(resto)
        if valor is None:
            novo: dict = {}
            atual[chave] = novo
            pilha.append((indent, novo))
        else:
            atual[chave] = valor
    return raiz


def carregar_yaml(caminho: Path) -> dict:
    return carregar_yaml_simples(caminho.read_text(encoding='utf-8-sig'))
```

- [ ] **Step 2: Trocar a definição por importação em `aplicar_marca.py`**

Em `plugins/kbr-docs/skills/report-creator/scripts/aplicar_marca.py`, confirme que existe, hoje, exatamente isto (linhas 32-96, do comentário `# --- YAML --` até o fim de `carregar_yaml`):

```python
# --------------------------------------------------------------------- YAML --
def _dividir_comentario(linha: str) -> str:
    """Corta um comentário à direita (# fora de aspas). # dentro de "..." não conta."""
    dentro_de_aspas = False
    for i, ch in enumerate(linha):
        if ch == '"':
            dentro_de_aspas = not dentro_de_aspas
        elif ch == '#' and not dentro_de_aspas:
            return linha[:i]
    return linha


def _valor_escalar(bruto: str):
    """None quando a linha só abre um mapeamento aninhado (ex.: "marca:", sem valor)."""
    bruto = bruto.strip()
    if not bruto:
        return None
    if bruto.startswith('"') and bruto.endswith('"') and len(bruto) >= 2:
        return bruto[1:-1].replace('\\"', '"')
    minusculo = bruto.casefold()
    if minusculo in ('true', 'yes', 'on'):
        return True
    if minusculo in ('false', 'no', 'off'):
        return False
    return bruto


def carregar_yaml_simples(texto: str) -> dict:
    """
    Lê o subconjunto de YAML que `.docs-brand.yml` usa: mapeamentos aninhados até 3
    níveis, indentação de 2 espaços, valores entre aspas duplas ou booleano (`true`/
    `yes`/`on` e `false`/`no`/`off`, sem diferenciar maiúsculas), comentários com `#`
    (linha inteira ou à direita do valor, fora de aspas).

    Deliberadamente NÃO é um parser de YAML geral — feito para não exigir PyYAML (e
    portanto nenhum `pip install`) de quem usa o plugin. Não suporta lista, âncora,
    bloco multilinha, aspas simples nem chave com dois-pontos dentro do próprio nome.
    """
    raiz: dict = {}
    pilha: list[tuple[int, dict]] = [(-1, raiz)]
    for linha_bruta in texto.splitlines():
        sem_comentario = _dividir_comentario(linha_bruta)
        if not sem_comentario.strip():
            continue
        indent = len(sem_comentario) - len(sem_comentario.lstrip(' '))
        chave, _, resto = sem_comentario.strip().partition(':')
        chave = chave.strip()
        if not chave:
            continue
        while indent <= pilha[-1][0]:
            pilha.pop()
        atual = pilha[-1][1]
        valor = _valor_escalar(resto)
        if valor is None:
            novo: dict = {}
            atual[chave] = novo
            pilha.append((indent, novo))
        else:
            atual[chave] = valor
    return raiz


def carregar_yaml(caminho: Path) -> dict:
    return carregar_yaml_simples(caminho.read_text(encoding='utf-8-sig'))
```

Troque por:

```python
# --------------------------------------------------------------------- YAML --
# O parser mora em resolver_marca.py (é ele quem também resolve a cascata de
# três níveis) — reexportado aqui pra quem já importa
# `aplicar_marca.carregar_yaml`/`carregar_yaml_simples` continuar funcionando.
from resolver_marca import carregar_yaml, carregar_yaml_simples  # noqa: F401
```

- [ ] **Step 3: Rodar os testes existentes — nada deve mudar**

```bash
cd "E:\Projetos\Kinto Brasil\src\github\KBR-Claude-Plugins"
python scripts/testar.py
python scripts/validar.py --strict
```

Esperado: o mesmo número de testes de antes desta task, todos OK — é reexportação pura, comportamento idêntico.

- [ ] **Step 4: Commit**

```bash
git add plugins/kbr-docs/skills/report-creator/scripts/resolver_marca.py plugins/kbr-docs/skills/report-creator/scripts/aplicar_marca.py
git commit -m "refactor(kbr-docs): mover o parser de YAML para resolver_marca.py

Preparacao para a cascata de tres niveis (Task 2 em diante) -- move o
parser (identico, zero mudanca de comportamento) para o modulo novo, e
aplicar_marca.py passa a importar dele. Reexportado (carregar_yaml,
carregar_yaml_simples) para os testes existentes continuarem
funcionando via aplicar_marca.carregar_yaml_simples(...) sem alteracao."
```

---

### Task 2: A cascata — `resolver()` em `resolver_marca.py`

Pura adição — ainda não é chamada por `descobrir.py` nem `aplicar_marca.py` (isso é a Task 3 e 4). Testável isoladamente.

**Files:**
- Modify: `plugins/kbr-docs/skills/report-creator/scripts/resolver_marca.py`
- Create: `plugins/kbr-docs/tests/test_resolver_marca.py`

**Interfaces:**
- Consumes: `carregar_yaml` (da Task 1, mesmo arquivo).
- Produces: `caminho_projeto(raiz)`, `caminho_projeto_legado(raiz)`, `pasta_usuario()`, `caminho_usuario()`, `nenhum_nivel_configurado(raiz) -> bool`, `resolver(raiz: Path) -> tuple[dict, list[str]]` — a Task 3 usa `resolver` e `nenhum_nivel_configurado`; a Task 4 usa `caminho_projeto` e `caminho_projeto_legado`.

- [ ] **Step 1: Escrever os testes (falham — as funções não existem ainda)**

Crie `plugins/kbr-docs/tests/test_resolver_marca.py`:

```python
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
        logo_usuario = Path(self.tmp_usuario.name) / "minha-logo.svg"
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
```

- [ ] **Step 2: Rodar e confirmar que falha (as funções não existem ainda)**

```bash
cd "E:\Projetos\Kinto Brasil\src\github\KBR-Claude-Plugins"
python -m unittest plugins.kbr-docs.tests.test_resolver_marca -v
```

Isso não funciona por causa do hífen no nome da pasta (mesmo motivo que `scripts/testar.py` existe em vez de `python -m unittest discover`). Rode assim:

```bash
python "plugins/kbr-docs/tests/test_resolver_marca.py"
```

Esperado: `AttributeError: module 'resolver_marca' has no attribute 'caminho_projeto'` (ou primeira função que faltar).

- [ ] **Step 3: Implementar a cascata em `resolver_marca.py`**

Acrescente ao FINAL de `plugins/kbr-docs/skills/report-creator/scripts/resolver_marca.py` (depois de `carregar_yaml`, que a Task 1 já deixou lá):

```python
import os

NOME_ARQUIVO = 'docs-brand.yml'
CAMPOS_DE_ARQUIVO = (('logo', 'claro'), ('logo', 'escuro'), ('autoria', 'avatar'))


# ------------------------------------------------------------------ caminhos --
def caminho_projeto(raiz: Path) -> Path:
    """<raiz>/.claude/plugins-data/kbr-docs/docs-brand.yml — o canônico."""
    return raiz / '.claude' / 'plugins-data' / 'kbr-docs' / NOME_ARQUIVO


def caminho_projeto_legado(raiz: Path) -> Path:
    """<raiz>/.docs-brand.yml — retrocompatibilidade com o formato de hoje."""
    return raiz / '.docs-brand.yml'


def pasta_usuario() -> Path:
    """
    ~/.claude/plugins-data/kbr-docs/ — ou $CLAUDE_USER_HOME/.claude/plugins-data/
    kbr-docs/, quando a variável de ambiente CLAUDE_USER_HOME estiver definida
    (só os testes usam isso, pra nunca tocar no ~/.claude de verdade).
    """
    override = os.environ.get('CLAUDE_USER_HOME')
    base = Path(override) if override else Path.home()
    return base / '.claude' / 'plugins-data' / 'kbr-docs'


def caminho_usuario() -> Path:
    return pasta_usuario() / NOME_ARQUIVO


def nenhum_nivel_configurado(raiz: Path) -> bool:
    """True quando nem projeto (canônico ou legado) nem usuário têm arquivo."""
    return not (
        caminho_projeto(raiz).exists()
        or caminho_projeto_legado(raiz).exists()
        or caminho_usuario().exists()
    )


# ------------------------------------------------------------------- mescla --
def _absolutizar_campos_de_arquivo(cfg: dict, base: Path) -> None:
    """Muda `cfg` no lugar: cada campo de arquivo não-vazio vira caminho absoluto
    contra `base` — a pasta de ONDE ESSE `cfg` veio, não a raiz do projeto."""
    for secao, campo in CAMPOS_DE_ARQUIVO:
        bloco = cfg.get(secao)
        if not isinstance(bloco, dict):
            continue
        valor = (bloco.get(campo) or '').strip()
        if valor:
            bloco[campo] = str((base / valor).resolve())


def _mesclar(preferido: dict, alternativo: dict) -> dict:
    """
    Campo a campo, recursivo: valor não-vazio de `preferido` sempre vence; string
    vazia ou chave ausente cai pro mesmo campo em `alternativo`. Booleano nunca é
    tratado como vazio (mesmo `False`). Nenhum dos dois argumentos é alterado.
    """
    resultado: dict = {}
    for chave in dict.fromkeys([*preferido.keys(), *alternativo.keys()]):
        v_pref = preferido.get(chave)
        v_alt = alternativo.get(chave)
        if isinstance(v_pref, dict) or isinstance(v_alt, dict):
            resultado[chave] = _mesclar(
                v_pref if isinstance(v_pref, dict) else {},
                v_alt if isinstance(v_alt, dict) else {})
        elif v_pref is None:
            resultado[chave] = v_alt
        elif isinstance(v_pref, str) and not v_pref.strip():
            resultado[chave] = v_alt if v_alt is not None else v_pref
        else:
            resultado[chave] = v_pref
    return resultado


def resolver(raiz: Path) -> tuple[dict, list[str]]:
    """
    Config efetivo (projeto -> usuário), com os campos de arquivo (logo.claro,
    logo.escuro, autoria.avatar) já absolutos. `notas` lista, no formato
    "secao.campo: nível de usuário (<caminho>)", cada campo de ARQUIVO que NÃO
    veio do projeto — pra aplicar_marca.py citar no relatório da geração.
    """
    notas: list[str] = []

    caminho_proj = caminho_projeto(raiz)
    if not caminho_proj.exists():
        caminho_proj = caminho_projeto_legado(raiz)
    cfg_projeto = carregar_yaml(caminho_proj) if caminho_proj.exists() else {}
    if cfg_projeto:
        _absolutizar_campos_de_arquivo(cfg_projeto, caminho_proj.parent)

    caminho_usr = caminho_usuario()
    cfg_usuario = carregar_yaml(caminho_usr) if caminho_usr.exists() else {}
    if cfg_usuario:
        _absolutizar_campos_de_arquivo(cfg_usuario, caminho_usr.parent)

    efetivo = _mesclar(cfg_projeto, cfg_usuario)

    for secao, campo in CAMPOS_DE_ARQUIVO:
        veio_do_projeto = bool(((cfg_projeto.get(secao) or {}).get(campo) or '').strip())
        veio_do_usuario = bool(((cfg_usuario.get(secao) or {}).get(campo) or '').strip())
        if not veio_do_projeto and veio_do_usuario:
            notas.append(f'{secao}.{campo}: nível de usuário ({caminho_usr})')

    return efetivo, notas
```

- [ ] **Step 4: Rodar os testes novos e confirmar que passam**

```bash
python "plugins/kbr-docs/tests/test_resolver_marca.py" -v
```

Esperado: todos os testes de `TesteNenhumNivelConfigurado`, `TesteResolverMescla` e `TesteCaminhoDeArquivoAbsolutizado` em `OK`.

- [ ] **Step 5: Rodar a suíte inteira do plugin — nada mais pode ter quebrado**

```bash
cd "E:\Projetos\Kinto Brasil\src\github\KBR-Claude-Plugins"
python scripts/testar.py
python scripts/validar.py --strict
```

- [ ] **Step 6: Commit**

```bash
git add plugins/kbr-docs/skills/report-creator/scripts/resolver_marca.py plugins/kbr-docs/tests/test_resolver_marca.py
git commit -m "feat(kbr-docs): cascata de tres niveis em resolver_marca.py

resolver(raiz) mescla projeto (.claude/plugins-data/kbr-docs/, com
fallback pro .docs-brand.yml legado da raiz) -> usuario
(~/.claude/plugins-data/kbr-docs/, ou \$CLAUDE_USER_HOME nos testes)
campo a campo, recursivo. Caminho de arquivo (logo.claro/escuro,
autoria.avatar) e absolutizado contra a pasta de origem de CADA CAMPO
antes da mescla -- um logo do usuario nunca resolve contra a raiz do
projeto. Booleano nunca conta como vazio. Ainda nao chamado por
descobrir.py/aplicar_marca.py (Tasks 3 e 4).

$(python "plugins/kbr-docs/tests/test_resolver_marca.py" -v 2>&1 | tail -3)"
```

---

### Task 3: Ligar `aplicar_marca.py` à cascata

**Files:**
- Modify: `plugins/kbr-docs/skills/report-creator/scripts/aplicar_marca.py`
- Modify: `plugins/kbr-docs/tests/test_aplicar_marca.py`

**Interfaces:**
- Consumes: `resolver_marca.resolver(raiz)`, `resolver_marca.nenhum_nivel_configurado(raiz)` (Task 2).
- Produces: `instalar_logos(cfg, destino)` e `instalar_avatar(cfg, destino)` com assinatura NOVA (sem `raiz`) — nenhuma outra task depende disso, mas é a mudança visível de fora deste arquivo.

- [ ] **Step 1: Isolar os testes de `main()` do `~/.claude` real (antes de mudar o código)**

Em `plugins/kbr-docs/tests/test_aplicar_marca.py`, troque a linha 6 (`import tempfile`) por:

```python
import os
import tempfile
```

Depois, confirme que existe, hoje, exatamente isto (a classe `TesteMainAplicarMarca`, sem `setUp`/`tearDown` de variável de ambiente):

```python
class TesteMainAplicarMarca(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()
```

Troque por:

```python
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
```

- [ ] **Step 2: Rodar a suíte — deve continuar 100% verde (isolamento não muda comportamento nenhum ainda)**

```bash
cd "E:\Projetos\Kinto Brasil\src\github\KBR-Claude-Plugins"
python scripts/testar.py
```

- [ ] **Step 3: Escrever o teste de integração da cascata (falha — `main()` ainda não usa o resolver)**

Acrescente, no FINAL de `plugins/kbr-docs/tests/test_aplicar_marca.py`, uma classe nova:

```python
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
```

- [ ] **Step 4: Rodar e confirmar que falha**

```bash
python "plugins/kbr-docs/tests/test_aplicar_marca.py" -v 2>&1 | grep -A5 test_autor_do_nivel_de_usuario
```

Esperado: FAIL — `main()` ainda lê só `.docs-brand.yml` da raiz, não acha o arquivo (a pasta `.claude/plugins-data/kbr-docs/` não é onde ele procura hoje), e o teste falha na asserção de `codigo == 0` ou de conteúdo do HTML.

- [ ] **Step 5: Trocar a leitura direta pela chamada ao resolver**

Em `plugins/kbr-docs/skills/report-creator/scripts/aplicar_marca.py`, confirme que existe, hoje, exatamente isto:

```python
def main() -> int:
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding='utf-8')
        except (AttributeError, OSError):
            pass

    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not args:
        print(__doc__)
        return 2
    destino = Path(args[0]).resolve()

    opc = {a.split('=')[0]: a.split('=', 1)[1] if '=' in a else ''
           for a in sys.argv[1:] if a.startswith('--')}
    raiz = raiz_do_projeto(Path(opc.get('--raiz', '.')))

    yml = raiz / '.docs-brand.yml'
    if not yml.exists():
        print(f'Não achei {yml}.\nInvoque a skill /kbr-docs:report-creator — ela descobre os '
              f'logos e a marca deste projeto na primeira vez.', file=sys.stderr)
        return 1
    cfg = carregar_yaml(yml)

    destino.mkdir(parents=True, exist_ok=True)
    (destino / 'assets').mkdir(exist_ok=True)

    for arq in (SKILL / 'assets').iterdir():
        shutil.copy2(arq, destino / 'assets' / arq.name)

    notas = instalar_logos(cfg, raiz, destino)
    avatarHtml, notasAvatar = instalar_avatar(cfg, raiz, destino)
    notas += notasAvatar
```

Troque por:

```python
def main() -> int:
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding='utf-8')
        except (AttributeError, OSError):
            pass

    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not args:
        print(__doc__)
        return 2
    destino = Path(args[0]).resolve()

    opc = {a.split('=')[0]: a.split('=', 1)[1] if '=' in a else ''
           for a in sys.argv[1:] if a.startswith('--')}
    raiz = raiz_do_projeto(Path(opc.get('--raiz', '.')))

    if resolver_marca.nenhum_nivel_configurado(raiz):
        print(f'Não achei marca nenhuma para {raiz} (nem projeto, nem nível de usuário).\n'
              f'Invoque a skill /kbr-docs:report-creator — ela descobre os '
              f'logos e a marca deste projeto na primeira vez.', file=sys.stderr)
        return 1
    cfg, notas_nivel = resolver_marca.resolver(raiz)

    destino.mkdir(parents=True, exist_ok=True)
    (destino / 'assets').mkdir(exist_ok=True)

    for arq in (SKILL / 'assets').iterdir():
        shutil.copy2(arq, destino / 'assets' / arq.name)

    notas = instalar_logos(cfg, destino)
    avatarHtml, notasAvatar = instalar_avatar(cfg, destino)
    notas += notasAvatar
    notas += notas_nivel
```

Agora adicione o import — no topo do arquivo, confirme que existe, hoje, exatamente isto:

```python
from resolver_marca import carregar_yaml, carregar_yaml_simples  # noqa: F401
```

Troque por:

```python
import resolver_marca
from resolver_marca import carregar_yaml, carregar_yaml_simples  # noqa: F401
```

- [ ] **Step 6: Simplificar `instalar_logos` e `instalar_avatar` — não recebem mais `raiz`**

Confirme que existe, hoje, exatamente isto:

```python
def instalar_avatar(cfg: dict, raiz: Path, destino: Path) -> tuple[str, list[str]]:
    """
    Copia a foto do autor, quando houver. Devolve o HTML do avatar e o relatório.

    Sem foto — ou com um caminho que não existe — voltam as iniciais, que é o
    estado normal e não um defeito: nem todo documento tem retrato do autor.
    """
    autoria = cfg.get('autoria', {}) or {}
    rel = (autoria.get('avatar') or '').strip()
    nome = autoria.get('autor', '')
    iniciaisHtml = f'<div class="avatar">{iniciais(nome)}</div>'

    if not rel:
        return iniciaisHtml, []
    origem = (raiz / rel).resolve()
    if not origem.exists():
        return iniciaisHtml, [f'avatar: "{rel}" não existe — usando as iniciais']

    alvo = destino / 'assets' / f'avatar{origem.suffix.lower()}'
    shutil.copy2(origem, alvo)
    notas = [f'avatar: {rel} → assets/{alvo.name}']
    if alvo.stat().st_size > 300_000:
        notas.append(f'   ⚠ {alvo.name} tem {alvo.stat().st_size // 1024} KB — '
                     f'a foto aparece em 32px; vale reduzir')
    alt = f'{nome}, autor do documento' if nome else 'Autor do documento'
    return (f'<img class="avatar" src="assets/{alvo.name}" alt="{alt}" '
            f'width="32" height="32" loading="lazy">'), notas


def instalar_logos(cfg: dict, raiz: Path, destino: Path) -> list[str]:
    """Copia os logos do projeto sobre os placeholders. Devolve o relatório."""
    notas = []
    for chave, alvo_base in (('claro', 'logo-claro'), ('escuro', 'logo-escuro')):
        rel = (cfg.get('logo') or {}).get(chave) or ''
        if not rel:
            notas.append(f'logo {chave}: NÃO definido no YAML — usando o placeholder da skill')
            continue
        origem = (raiz / rel).resolve()
        if not origem.exists():
            notas.append(f'logo {chave}: "{rel}" não existe — usando o placeholder da skill')
            continue
        # mantém a extensão do arquivo do projeto: png, svg, webp…
        alvo = destino / 'assets' / f'{alvo_base}{origem.suffix.lower()}'
        shutil.copy2(origem, alvo)
        # documentação carrega o logo em toda página; um PNG de 2 MB pesa em cada uma
        if alvo.stat().st_size > 500_000:
            notas.append(f'   ⚠ {alvo.name} tem {alvo.stat().st_size // 1024} KB — '
                         f'vale gerar uma versão reduzida para a documentação')
        # o HTML aponta para o placeholder .svg; se o logo real tem outra extensão,
        # o placeholder sai de cena para não ficar arquivo morto na pasta
        placeholder = destino / 'assets' / f'{alvo_base}.svg'
        if placeholder.exists() and placeholder != alvo:
            placeholder.unlink()
        notas.append(f'logo {chave}: {rel} → assets/{alvo.name}')
    return notas
```

Troque por:

```python
def instalar_avatar(cfg: dict, destino: Path) -> tuple[str, list[str]]:
    """
    Copia a foto do autor, quando houver. Devolve o HTML do avatar e o relatório.

    `cfg['autoria']['avatar']` já chega em caminho ABSOLUTO (ou vazio) —
    `resolver_marca.resolver()` já decidiu de qual nível ele vem e já
    absolutizou contra a pasta certa antes de devolver o config.

    Sem foto — ou com um caminho que não existe — voltam as iniciais, que é o
    estado normal e não um defeito: nem todo documento tem retrato do autor.
    """
    autoria = cfg.get('autoria', {}) or {}
    rel = (autoria.get('avatar') or '').strip()
    nome = autoria.get('autor', '')
    iniciaisHtml = f'<div class="avatar">{iniciais(nome)}</div>'

    if not rel:
        return iniciaisHtml, []
    origem = Path(rel)
    if not origem.exists():
        return iniciaisHtml, [f'avatar: "{rel}" não existe — usando as iniciais']

    alvo = destino / 'assets' / f'avatar{origem.suffix.lower()}'
    shutil.copy2(origem, alvo)
    notas = [f'avatar: {rel} → assets/{alvo.name}']
    if alvo.stat().st_size > 300_000:
        notas.append(f'   ⚠ {alvo.name} tem {alvo.stat().st_size // 1024} KB — '
                     f'a foto aparece em 32px; vale reduzir')
    alt = f'{nome}, autor do documento' if nome else 'Autor do documento'
    return (f'<img class="avatar" src="assets/{alvo.name}" alt="{alt}" '
            f'width="32" height="32" loading="lazy">'), notas


def instalar_logos(cfg: dict, destino: Path) -> list[str]:
    """
    Copia os logos do projeto sobre os placeholders. Devolve o relatório.

    `cfg['logo']['claro']`/`['escuro']` já chegam em caminho ABSOLUTO (ou
    vazio) — ver `instalar_avatar`.
    """
    notas = []
    for chave, alvo_base in (('claro', 'logo-claro'), ('escuro', 'logo-escuro')):
        rel = (cfg.get('logo') or {}).get(chave) or ''
        if not rel:
            notas.append(f'logo {chave}: NÃO definido em nenhum nível — usando o placeholder da skill')
            continue
        origem = Path(rel)
        if not origem.exists():
            notas.append(f'logo {chave}: "{rel}" não existe — usando o placeholder da skill')
            continue
        # mantém a extensão do arquivo do projeto: png, svg, webp…
        alvo = destino / 'assets' / f'{alvo_base}{origem.suffix.lower()}'
        shutil.copy2(origem, alvo)
        # documentação carrega o logo em toda página; um PNG de 2 MB pesa em cada uma
        if alvo.stat().st_size > 500_000:
            notas.append(f'   ⚠ {alvo.name} tem {alvo.stat().st_size // 1024} KB — '
                         f'vale gerar uma versão reduzida para a documentação')
        # o HTML aponta para o placeholder .svg; se o logo real tem outra extensão,
        # o placeholder sai de cena para não ficar arquivo morto na pasta
        placeholder = destino / 'assets' / f'{alvo_base}.svg'
        if placeholder.exists() and placeholder != alvo:
            placeholder.unlink()
        notas.append(f'logo {chave}: {rel} → assets/{alvo.name}')
    return notas
```

- [ ] **Step 7: Rodar o teste de integração — deve passar agora**

```bash
python "plugins/kbr-docs/tests/test_aplicar_marca.py" -v 2>&1 | grep -A3 test_autor_do_nivel_de_usuario
```

Esperado: `test_autor_do_nivel_de_usuario_chega_ao_html_gerado ... ok`.

- [ ] **Step 8: Rodar a suíte inteira do plugin**

```bash
cd "E:\Projetos\Kinto Brasil\src\github\KBR-Claude-Plugins"
python scripts/testar.py
python scripts/validar.py --strict
```

Esperado: todos os testes de `test_aplicar_marca.py` (inclusive os que já existiam antes desta task — `test_falha_limpa_sem_docs_brand_yml`, `test_instala_logo_do_projeto_sobre_o_placeholder` etc., que escrevem no `.docs-brand.yml` LEGADO da raiz) continuam passando — é a retrocompatibilidade funcionando.

- [ ] **Step 9: Commit**

```bash
git add plugins/kbr-docs/skills/report-creator/scripts/aplicar_marca.py plugins/kbr-docs/tests/test_aplicar_marca.py
git commit -m "feat(kbr-docs): aplicar_marca.py usa a cascata de tres niveis

main() troca a leitura direta do .docs-brand.yml da raiz por
resolver_marca.resolver(raiz) -- projeto (canonico ou legado) mesclado
com o nivel de usuario. instalar_logos()/instalar_avatar() perdem o
parametro raiz (o caminho ja chega absoluto do resolver).

Testes existentes isolados de ~/.claude real via CLAUDE_USER_HOME
(mesmo padrao que kbr-core ja usa com KBR_HOME pra ~/.kbr). Teste novo
prova o caminho ponta a ponta: autor definido so no nivel de usuario
chega no HTML gerado, e o relatorio cita 'nivel de usuario'.

$(python scripts/testar.py 2>&1 | tail -3)"
```

---

### Task 4: Ligar `descobrir.py` à cascata (só o local de gravação)

`descobrir.py` não precisa mesclar nada — só passa a gravar no lugar canônico, e recusa gravar se JÁ existir um arquivo (canônico OU legado), pra nunca criar um segundo arquivo por cima de uma configuração já feita.

**Files:**
- Modify: `plugins/kbr-docs/skills/report-creator/scripts/descobrir.py`
- Modify: `plugins/kbr-docs/tests/test_descobrir.py`

**Interfaces:**
- Consumes: `resolver_marca.caminho_projeto(raiz)`, `resolver_marca.caminho_projeto_legado(raiz)` (Task 2).

- [ ] **Step 1: Atualizar os testes existentes pro novo local (escrevem — devem falhar contra o local antigo depois do Step 3)**

Em `plugins/kbr-docs/tests/test_descobrir.py`, confirme que existe, hoje, exatamente isto:

```python
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
```

Troque por:

```python
    def test_escrever_grava_o_arquivo_no_local_canonico(self):
        codigo, saida, _ = _rodar(str(self.raiz), "--escrever")
        self.assertEqual(codigo, 0)
        destino = self.raiz / ".claude" / "plugins-data" / "kbr-docs" / "docs-brand.yml"
        self.assertTrue(destino.exists())
        self.assertIn("escrito:", saida)

    def test_nunca_sobrescreve_o_canonico_ja_existente(self):
        destino = self.raiz / ".claude" / "plugins-data" / "kbr-docs" / "docs-brand.yml"
        destino.parent.mkdir(parents=True)
        destino.write_text("conteudo original\n", encoding="utf-8")
        codigo, saida, _ = _rodar(str(self.raiz), "--escrever")
        self.assertEqual(codigo, 1)
        self.assertEqual(destino.read_text(encoding="utf-8"), "conteudo original\n")

    def test_nao_cria_canonico_quando_ja_ha_legado(self):
        legado = self.raiz / ".docs-brand.yml"
        legado.write_text("conteudo legado\n", encoding="utf-8")
        codigo, saida, _ = _rodar(str(self.raiz), "--escrever")
        self.assertEqual(codigo, 1)
        canonico = self.raiz / ".claude" / "plugins-data" / "kbr-docs" / "docs-brand.yml"
        self.assertFalse(canonico.exists())
        self.assertEqual(legado.read_text(encoding="utf-8"), "conteudo legado\n")
```

Também confirme que existe, hoje, exatamente isto (no `test_modo_leitura_nao_grava_nada`):

```python
    def test_modo_leitura_nao_grava_nada(self):
        codigo, saida, _ = _rodar(str(self.raiz))
        self.assertEqual(codigo, 0)
        self.assertIn("raiz do projeto", saida)
        self.assertFalse((self.raiz / ".docs-brand.yml").exists())
```

Troque por:

```python
    def test_modo_leitura_nao_grava_nada(self):
        codigo, saida, _ = _rodar(str(self.raiz))
        self.assertEqual(codigo, 0)
        self.assertIn("raiz do projeto", saida)
        self.assertFalse((self.raiz / ".docs-brand.yml").exists())
        self.assertFalse(
            (self.raiz / ".claude" / "plugins-data" / "kbr-docs" / "docs-brand.yml").exists())
```

- [ ] **Step 2: Rodar e confirmar que os 3 testes de escrita falham (código ainda grava no local antigo)**

```bash
cd "E:\Projetos\Kinto Brasil\src\github\KBR-Claude-Plugins"
python "plugins/kbr-docs/tests/test_descobrir.py" -v 2>&1 | grep -E "test_escrever|test_nunca_sobrescreve|test_nao_cria_canonico"
```

Esperado: `test_escrever_grava_o_arquivo_no_local_canonico` e `test_nao_cria_canonico_quando_ja_ha_legado` FALHAM (o código ainda grava em `.docs-brand.yml`); `test_nunca_sobrescreve_o_canonico_ja_existente` também falha (ainda compara contra o local antigo).

- [ ] **Step 3: Trocar o local de gravação em `descobrir.py`**

Confirme que existe, hoje, exatamente isto:

```python
    yml = montar_yaml(raiz, nome, origem, claro, escuro)
    destino = raiz / '.docs-brand.yml'

    if not escrever:
        print(f'\n--- {destino} (prévia; use --escrever para gravar) ---\n')
        print(yml)
        return 0

    if destino.exists():
        print(f'\n{destino} já existe — não vou sobrescrever. Apague ou edite à mão.')
        return 1
    destino.write_text(yml, encoding='utf-8', newline='\n')
    print(f'\nescrito: {destino}')
    return 0
```

Troque por:

```python
    yml = montar_yaml(raiz, nome, origem, claro, escuro)
    destino = resolver_marca.caminho_projeto(raiz)
    legado = resolver_marca.caminho_projeto_legado(raiz)

    if not escrever:
        print(f'\n--- {destino} (prévia; use --escrever para gravar) ---\n')
        print(yml)
        return 0

    if destino.exists():
        print(f'\n{destino} já existe — não vou sobrescrever. Apague ou edite à mão.')
        return 1
    if legado.exists():
        print(f'\n{legado} já existe (formato legado) — não vou criar {destino} por cima.\n'
              f'Apague o legado primeiro se quiser migrar pro local novo, ou edite-o à mão.')
        return 1
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(yml, encoding='utf-8', newline='\n')
    print(f'\nescrito: {destino}')
    return 0
```

Adicione o import — logo depois de `from pathlib import Path` no topo do arquivo, confirme que existe, hoje, exatamente isto:

```python
from pathlib import Path
```

Troque por:

```python
from pathlib import Path

import resolver_marca
```

- [ ] **Step 4: Rodar os testes de novo — devem passar**

```bash
python "plugins/kbr-docs/tests/test_descobrir.py" -v
```

Esperado: todos os testes de `TesteMain` em `ok`, inclusive os três atualizados/novos do Step 1.

- [ ] **Step 5: Rodar a suíte inteira do plugin**

```bash
cd "E:\Projetos\Kinto Brasil\src\github\KBR-Claude-Plugins"
python scripts/testar.py
python scripts/validar.py --strict
```

- [ ] **Step 6: Commit**

```bash
git add plugins/kbr-docs/skills/report-creator/scripts/descobrir.py plugins/kbr-docs/tests/test_descobrir.py
git commit -m "feat(kbr-docs): descobrir.py grava no local canonico da cascata

--escrever passa a gravar em .claude/plugins-data/kbr-docs/docs-brand.yml
em vez da raiz -- e recusa gravar (saida 1) se JA existir um arquivo,
canonico OU legado, pra nunca criar um segundo por cima de config ja
feita. A heuristica de descoberta (achar logo/cor/nome) nao muda em
nada; so o destino da gravacao.

$(python scripts/testar.py 2>&1 | tail -3)"
```

---

### Task 5: Documentar os três níveis em `SKILL.md`

**Files:**
- Modify: `plugins/kbr-docs/skills/report-creator/SKILL.md`

- [ ] **Step 1: Atualizar a seção do fluxo de descoberta**

Confirme que existe, hoje, exatamente isto:

```
1. Confira se `.docs-brand.yml` existe na raiz do projeto.
2. **Não existe:** descubra a marca primeiro (seção 1 abaixo), depois siga para a geração.
3. **Já existe:** vá direto para a geração (seção 2).
```

Troque por:

```
1. Confira se já existe config de marca — em qualquer um dos três níveis (veja
   "Os três níveis" abaixo). O jeito mais rápido é rodar o resolver:
   `python "${CLAUDE_PLUGIN_ROOT}/skills/report-creator/scripts/resolver_marca.py" .`
   — ele mostra o efetivo (projeto mesclado com o nível de usuário) sem gravar nada.
2. **Nada configurado (nem projeto, nem usuário):** descubra a marca do projeto
   primeiro (seção 1 abaixo), depois siga para a geração.
3. **Já existe algo** (mesmo que só no nível de usuário): vá direto para a
   geração (seção 2) — e, ao perguntar o que falta preencher, **não pergunte
   de novo** o que o resolver já mostrou como preenchido pelo nível de usuário.
```

- [ ] **Step 2: Adicionar a seção "Os três níveis"**

Depois do bloco `## O que existe nesta skill` (o que lista `scripts/`, `assets/`, `templates/`, `referencia/`), adicione uma seção nova:

```markdown
## Os três níveis de configuração

Cada campo do `.docs-brand.yml` é resolvido nesta ordem — o primeiro nível que
tiver o campo preenchido vence:

1. **Projeto** — `<raiz>/.claude/plugins-data/kbr-docs/docs-brand.yml` (canônico).
   Se não existir, `<raiz>/.docs-brand.yml` (formato de antes desta cascata —
   continua funcionando, sem prazo pra sumir).
2. **Usuário** — `~/.claude/plugins-data/kbr-docs/docs-brand.yml`. Preenchido à
   mão (sem descoberta automática) — é o lugar certo pra guardar um default
   pessoal (nome, cargo, e-mail, até logo/cor próprios) que se aplica a
   qualquer projeto que não tenha configurado a própria marca.
3. **Placeholder do plugin** — só pra logo (`logo-claro.svg`/`logo-escuro.svg`),
   quando nem projeto nem usuário tiverem um.

A mescla é campo a campo: um projeto pode definir só o logo e herdar
autoria/contato do nível de usuário — não precisa repetir tudo em cada
repositório. Caminho de arquivo (logo, avatar) sempre resolve relativo à
pasta de ONDE aquele campo veio, nunca contra a raiz do projeto quando vier
do usuário.

`python resolver_marca.py <raiz>` mostra o efetivo (já mesclado) sem gravar
nada — use isso, não `descobrir.py`, pra ver o que já está coberto antes de
perguntar à pessoa o que falta.
```

- [ ] **Step 3: Rodar `validar.py --strict` — confirma que o `SKILL.md` continua bem formado**

```bash
cd "E:\Projetos\Kinto Brasil\src\github\KBR-Claude-Plugins"
python scripts/validar.py --strict
```

- [ ] **Step 4: Commit**

```bash
git add plugins/kbr-docs/skills/report-creator/SKILL.md
git commit -m "docs(kbr-docs): documentar a cascata de tres niveis no SKILL.md

Fluxo de descoberta atualizado pra checar os tres niveis (via
resolver_marca.py, em vez de so olhar pro .docs-brand.yml da raiz) e
nao perguntar de novo o que o nivel de usuario ja cobre. Secao nova
explicando os tres niveis e a ordem de prioridade."
```

---

### Task 6: Verificação final — suíte completa + prova end-to-end da cascata

Sem código novo esperado — checagem de regressão e uma prova manual, num scratch fora do repositório, de que o nível de usuário funciona de ponta a ponta sem tocar no `~/.claude` real do Fábio.

**Files:** nenhum (verificação) — ou os das tasks anteriores, se algo precisar de ajuste.

- [ ] **Step 1: Suíte completa + validador**

```bash
cd "E:\Projetos\Kinto Brasil\src\github\KBR-Claude-Plugins"
python scripts/testar.py
python scripts/validar.py --strict
```

Confirme visualmente que o NÚMERO de testes cresceu em relação ao que havia antes desta fatia (as Tasks 2 e 3 adicionaram testes novos) — não é só "ainda dá OK", é "cresceu e continua OK".

- [ ] **Step 2: Prova end-to-end, num scratch — projeto parcial + nível de usuário fake**

```bash
SCRATCH_HOME=$(mktemp -d)
SCRATCH_PROJ=$(mktemp -d)
export CLAUDE_USER_HOME="$SCRATCH_HOME"

mkdir -p "$SCRATCH_HOME/.claude/plugins-data/kbr-docs"
cat > "$SCRATCH_HOME/.claude/plugins-data/kbr-docs/docs-brand.yml" <<'EOF'
autoria:
  autor: "Fulano de Teste"
  cargo: "Arquiteto de Testes"
contato:
  email: "fulano@teste.com"
EOF

cd "$SCRATCH_PROJ"
python "/e/Projetos/Kinto Brasil/src/github/KBR-Claude-Plugins/plugins/kbr-docs/skills/report-creator/scripts/descobrir.py" . --escrever
python "/e/Projetos/Kinto Brasil/src/github/KBR-Claude-Plugins/plugins/kbr-docs/skills/report-creator/scripts/aplicar_marca.py" docs/x --raiz=.
```

Confira:
1. O `descobrir.py --escrever` gravou em `.claude/plugins-data/kbr-docs/docs-brand.yml` dentro de `$SCRATCH_PROJ` (não na raiz):
   ```bash
   test -f "$SCRATCH_PROJ/.claude/plugins-data/kbr-docs/docs-brand.yml" && echo "canonico OK"
   ```
2. O relatório do `aplicar_marca.py` citou "nível de usuário" pelo menos duas vezes (autor e cargo vieram de lá — `email` também):
   ```bash
   python "/e/Projetos/Kinto Brasil/src/github/KBR-Claude-Plugins/plugins/kbr-docs/skills/report-creator/scripts/aplicar_marca.py" docs/y --raiz="$SCRATCH_PROJ" 2>&1 | grep "nível de usuário"
   ```
3. O HTML gerado tem "Fulano de Teste":
   ```bash
   grep -o "Fulano de Teste" "$SCRATCH_PROJ/docs/x/index.html"
   ```

- [ ] **Step 3: Prova de retrocompatibilidade — só o legado, sem canônico nem usuário**

```bash
SCRATCH_LEGADO=$(mktemp -d)
unset CLAUDE_USER_HOME
cd "$SCRATCH_LEGADO"
cat > .docs-brand.yml <<'EOF'
projeto:
  nome: "Projeto Legado"
logo:
  claro: ""
  escuro: ""
marca:
  claro:
    brand: "#336699"
  escuro:
    brand: "#5C9BC9"
textos:
  rodape: "rodape"
autoria:
  autor: ""
contato:
  email: ""
tipografia:
  fontes_externas: true
EOF
python "/e/Projetos/Kinto Brasil/src/github/KBR-Claude-Plugins/plugins/kbr-docs/skills/report-creator/scripts/aplicar_marca.py" docs/x --raiz=.
grep -o "Projeto Legado" docs/x/index.html
```

Esperado: gera normalmente, sem erro — o formato de antes desta fatia continua funcionando sozinho, sem precisar do nível canônico nem do de usuário.

- [ ] **Step 4: Limpar os scratches**

```bash
rm -rf "$SCRATCH_HOME" "$SCRATCH_PROJ" "$SCRATCH_LEGADO"
```

- [ ] **Step 5: Se algo precisou de correção, commit; senão, task concluída sem commit novo**

```bash
cd "E:\Projetos\Kinto Brasil\src\github\KBR-Claude-Plugins"
git status --short
```

Se vazio, a fatia está pronta, aguardando o Fábio decidir sobre push + tag `kbr-docs--v0.1.1` (mesma pendência já registrada das fatias anteriores desta sessão).
