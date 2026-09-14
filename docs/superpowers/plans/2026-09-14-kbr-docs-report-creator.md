# Plugin `kbr-docs`, skill `report-creator` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrar as skills pessoais `docs-init` (`~/.claude/skills/docs-init`) e `docs-html`
(`~/.claude/skills/docs-html`) para dentro de um plugin novo, `kbr-docs`, como uma única skill
consolidada `report-creator`, com cobertura de teste completa (hoje não existe nenhuma) e sem
depender de `pip install` nenhum — nem PyYAML, que o código original exige de verdade.

**Architecture:** Os dois scripts Python (`descobrir.py`, `aplicar_marca.py`) são relocados
sem mudança de lógica, exceto por uma: `aplicar_marca.py` ganha um leitor de YAML próprio,
restrito ao subconjunto que `.docs-brand.yml` usa, no lugar do `import yaml` (PyYAML) que o
original tinha embutido numa função — achado ao ler o arquivo inteiro durante o planejamento,
não capturado no brainstorming (era um `import` local, dentro de função, não no topo do
arquivo). As duas skills globais originais continuam existindo, intocadas — é uma cópia
paralela, não uma migração destrutiva.

**Tech Stack:** Python ≥ 3.10, biblioteca padrão apenas. Pillow continua **opcional** (só
melhora a detecção automática de cor/luminância de logo PNG; sem ele, esses campos ficam
`None` e o YAML gerado marca como `# SUGESTÃO — confira`).

## Global Constraints

- PT-BR em tudo — mensagens de script, comentários, `SKILL.md`, commits.
- Python ≥ 3.10, só biblioteca padrão. **Nenhum plugin pode exigir `pip install`** — é por
  isso que o `import yaml` (PyYAML) do código original vira um parser próprio nesta migração
  (Task 2). Pillow continua opcional, com fallback gracioso já existente no código original —
  não mude esse comportamento.
- Nenhuma mudança de comportamento além do necessário para funcionar como plugin — é
  migração, não redesenho. As duas exceções deliberadas (documentadas, não escondidas): o
  parser de YAML (Task 2) e o texto de uma linha de comentário gerada por `descobrir.py` que
  hoje aponta para o comando errado depois da consolidação (Task 1).
- Caminhos em `SKILL.md` sempre via `${CLAUDE_PLUGIN_ROOT}`.
- As skills globais originais (`~/.claude/skills/docs-init`, `~/.claude/skills/docs-html`)
  **não são tocadas** — ficam fora do escopo deste plano inteiro.
- `report-creator` é uma skill só, não duas — consolidando o fluxo "descobrir a marca (só na
  primeira vez) → gerar o documento" que hoje precisa de duas invocações separadas.
- `kb-doc-creator` e `presentation-creator` (apresentações/PPTX) ficam fora de escopo.
- Nunca `git add -A`. Nomeie os caminhos e confira `git status --short` antes de cada commit.
- Runner de teste do repositório: `python scripts/testar.py` roda tudo; para rodar só este
  plugin durante o desenvolvimento, use
  `cd plugins/kbr-docs/tests && python -m unittest discover -s . -t . -v`.
- Validação: `claude plugin validate --strict plugins/kbr-docs` valida só este plugin
  (progressivo, a partir da Task 3, quando o `SKILL.md` existir); `python scripts/validar.py`
  valida marketplace + todos os plugins listados em `marketplace.json` — só inclui `kbr-docs`
  depois da Task 4, quando a entrada for acrescentada lá.

---

## Task 1: Migrar `descobrir.py` (descoberta de marca), com testes

**Files:**
- Create: `plugins/kbr-docs/.claude-plugin/plugin.json`
- Create: `plugins/kbr-docs/skills/report-creator/scripts/descobrir.py`
  (copiado de `C:\Users\Fabio.Patria\.claude\skills\docs-init\scripts\descobrir.py`, com um
  ajuste de texto — ver Step 3)
- Create: `plugins/kbr-docs/tests/test_descobrir.py`

**Interfaces:**
- Produces: módulo `descobrir` com `raiz_do_projeto(inicio: Path) -> Path`,
  `achar_logos(raiz: Path) -> list[dict]`, `escolher_par(logos: list[dict]) -> tuple[dict | None, dict | None]`,
  `nome_do_projeto(raiz: Path) -> tuple[str, str]`, `luminancia_media(caminho: Path) -> float | None`,
  `cor_dominante(caminho: Path) -> str | None`, `cor_de_svg(caminho: Path) -> str | None`,
  `montar_yaml(raiz: Path, nome: str, origem_nome: str, claro: dict | None, escuro: dict | None) -> str`,
  `main() -> int` (lê `sys.argv`). Usado pela Task 2 (`montar_yaml` no teste de round-trip do
  parser de YAML) e pela Task 3 (`SKILL.md` chama o script via linha de comando).

- [ ] **Step 1: Criar o `plugin.json`**

```bash
mkdir -p plugins/kbr-docs/.claude-plugin
```

Crie `plugins/kbr-docs/.claude-plugin/plugin.json`:
```json
{
  "name": "kbr-docs",
  "displayName": "KINTO — Documentação",
  "version": "0.1.0",
  "description": "Gera documentação em HTML com o design system oficial da KINTO — descobre a marca do projeto na primeira vez e gera os documentos a partir daí.",
  "author": {
    "name": "KINTO Brasil — TI"
  },
  "keywords": [
    "documentacao",
    "html",
    "relatorio",
    "design-system",
    "kinto"
  ]
}
```

- [ ] **Step 2: Copiar `descobrir.py` para o plugin**

```bash
mkdir -p plugins/kbr-docs/skills/report-creator/scripts
cp "/c/Users/Fabio.Patria/.claude/skills/docs-init/scripts/descobrir.py" \
   plugins/kbr-docs/skills/report-creator/scripts/descobrir.py
```

- [ ] **Step 3: Ajustar o único texto que muda**

Em `plugins/kbr-docs/skills/report-creator/scripts/descobrir.py`, dentro da função
`montar_yaml`, a f-string do YAML gerado tem este comentário (perto do topo do bloco):
```python
# Depois de editar, gere de novo:
#   python ~/.claude/skills/docs-html/scripts/aplicar_marca.py docs/<assunto> --raiz=.
```
Troque por (a skill consolidada não expõe mais o comando cru — depois da migração, quem edita
o YAML à mão volta a invocar a skill, não o script direto):
```python
# Depois de editar, gere de novo:
#   invoque a skill /kbr-docs:report-creator
```

Nenhuma outra linha do arquivo muda — o resto do script já se localiza sozinho via
`Path(__file__).resolve().parent...` e não tem caminho absoluto embutido em lugar nenhum.

- [ ] **Step 4: Escrever os testes**

Crie `plugins/kbr-docs/tests/test_descobrir.py`:
```python
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
```

- [ ] **Step 5: Rodar e confirmar (a maioria já passa — é migração, não código novo)**

```bash
cd plugins/kbr-docs/tests && python -m unittest test_descobrir -v
```
Esperado: `OK` (16 testes). Como o código em si não muda nesta task (só relocação + um texto),
não há um "RED" de verdade — se algum teste falhar, é sinal de que a cópia divergiu do
original ou de que uma suposição do teste está errada; investigue antes de seguir.

- [ ] **Step 6: Commit**

```bash
git add plugins/kbr-docs/.claude-plugin/plugin.json \
        plugins/kbr-docs/skills/report-creator/scripts/descobrir.py \
        plugins/kbr-docs/tests/test_descobrir.py
git commit -m "$(cat <<'EOF'
feat(kbr-docs): migrar descobrir.py (descoberta de marca) com testes

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FxSq1YTHKimYYBJmKABcBa
EOF
)"
```

---

## Task 2: Migrar `aplicar_marca.py`, trocando PyYAML por um parser próprio, com testes

**Files:**
- Create: `plugins/kbr-docs/skills/report-creator/scripts/aplicar_marca.py`
  (baseado em `C:\Users\Fabio.Patria\.claude\skills\docs-html\scripts\aplicar_marca.py`, com a
  mudança do parser de YAML — ver Steps 2-3)
- Create: `plugins/kbr-docs/skills/report-creator/assets/` (cópia de
  `C:\Users\Fabio.Patria\.claude\skills\docs-html\assets\`)
- Create: `plugins/kbr-docs/skills/report-creator/templates/` (cópia de
  `C:\Users\Fabio.Patria\.claude\skills\docs-html\templates\`)
- Create: `plugins/kbr-docs/skills/report-creator/referencia/` (cópia de
  `C:\Users\Fabio.Patria\.claude\skills\docs-html\referencia\`)
- Create: `plugins/kbr-docs/tests/test_aplicar_marca.py`

**Interfaces:**
- Consumes: `descobrir.montar_yaml` (Task 1) — usado no teste de round-trip do parser de YAML
  (Step 4).
- Produces: módulo `aplicar_marca` com `carregar_yaml_simples(texto: str) -> dict`,
  `carregar_yaml(caminho: Path) -> dict`, `css_da_marca(marca: dict) -> str`,
  `instalar_logos`, `instalar_avatar`, `substituir`, `main() -> int`. Usado pela Task 3
  (`SKILL.md` chama o script via linha de comando).

- [ ] **Step 1: Copiar os assets estáticos e o script**

```bash
mkdir -p plugins/kbr-docs/skills/report-creator/assets
mkdir -p plugins/kbr-docs/skills/report-creator/templates
mkdir -p plugins/kbr-docs/skills/report-creator/referencia
cp "/c/Users/Fabio.Patria/.claude/skills/docs-html/assets/"* \
   plugins/kbr-docs/skills/report-creator/assets/
cp "/c/Users/Fabio.Patria/.claude/skills/docs-html/templates/"* \
   plugins/kbr-docs/skills/report-creator/templates/
cp "/c/Users/Fabio.Patria/.claude/skills/docs-html/referencia/componentes.html" \
   plugins/kbr-docs/skills/report-creator/referencia/
cp "/c/Users/Fabio.Patria/.claude/skills/docs-html/scripts/aplicar_marca.py" \
   plugins/kbr-docs/skills/report-creator/scripts/aplicar_marca.py
```

Confira que nada de `__pycache__`/`.pyc` foi copiado junto (a skill global tem um
`scripts/__pycache__/` que não deve entrar no plugin):
```bash
find plugins/kbr-docs/skills/report-creator -iname "__pycache__" -o -iname "*.pyc"
```
Esperado: nenhuma saída. Se aparecer algo, apague antes de commitar.

- [ ] **Step 2: Escrever o teste do parser de YAML (RED)**

Crie `plugins/kbr-docs/tests/test_aplicar_marca.py`:
```python
# -*- coding: utf-8 -*-
"""Testes da geração de documentos (aplicar_marca.py)."""
import contextlib
import io
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

    def tearDown(self):
        self.tmp.cleanup()

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
        self.assertIn("docs-init", erro)

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
```

- [ ] **Step 3: Rodar e confirmar que os testes do parser falham**

```bash
cd plugins/kbr-docs/tests && python -m unittest test_aplicar_marca.TesteCarregarYamlSimples -v
```
Esperado: `AttributeError: module 'aplicar_marca' has no attribute 'carregar_yaml_simples'`
(o script ainda tem o `carregar_yaml` original, que exige PyYAML).

- [ ] **Step 4: Trocar `carregar_yaml` pelo parser próprio**

Em `plugins/kbr-docs/skills/report-creator/scripts/aplicar_marca.py`, troque:
```python
# --------------------------------------------------------------------- YAML --
def carregar_yaml(caminho: Path) -> dict:
    try:
        import yaml
    except ImportError:
        print('PyYAML não está instalado: pip install pyyaml', file=sys.stderr)
        raise SystemExit(2)
    return yaml.safe_load(caminho.read_text(encoding='utf-8')) or {}
```
por:
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
    if bruto == 'true':
        return True
    if bruto == 'false':
        return False
    return bruto


def carregar_yaml_simples(texto: str) -> dict:
    """
    Lê o subconjunto de YAML que `.docs-brand.yml` usa: mapeamentos aninhados até 3
    níveis, indentação de 2 espaços, valores entre aspas duplas ou `true`/`false`,
    comentários com `#` (linha inteira ou à direita do valor, fora de aspas).

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
    return carregar_yaml_simples(caminho.read_text(encoding='utf-8'))
```

Depois, ajuste a mensagem de erro em `main()` (ela hoje manda rodar a skill `docs-init`
separada, que na skill consolidada não existe mais como comando isolado). Troque:
```python
    yml = raiz / '.docs-brand.yml'
    if not yml.exists():
        print(f'Não achei {yml}.\nRode a skill `docs-init` antes — ela descobre os logos '
              f'e a marca deste projeto.', file=sys.stderr)
        return 1
```
por:
```python
    yml = raiz / '.docs-brand.yml'
    if not yml.exists():
        print(f'Não achei {yml}.\nRode a descoberta de marca (docs-init) antes — ela acha os '
              f'logos e a marca deste projeto.', file=sys.stderr)
        return 1
```
(O teste `test_falha_limpa_sem_docs_brand_yml` do Step 2 confere só que a palavra `docs-init`
aparece na mensagem — qualquer frase que a mantenha passa.)

- [ ] **Step 5: Rodar e confirmar que tudo passa**

```bash
cd plugins/kbr-docs/tests && python -m unittest test_aplicar_marca -v
```
Esperado: `OK` (14 testes).

Depois rode a suíte inteira do plugin para garantir que a Task 1 continua intacta:
```bash
cd plugins/kbr-docs/tests && python -m unittest discover -s . -t . -v 2>&1 | tail -5
```
Esperado: `OK` (30 testes).

- [ ] **Step 6: Commit**

```bash
git add plugins/kbr-docs/skills/report-creator/scripts/aplicar_marca.py \
        plugins/kbr-docs/skills/report-creator/assets \
        plugins/kbr-docs/skills/report-creator/templates \
        plugins/kbr-docs/skills/report-creator/referencia \
        plugins/kbr-docs/tests/test_aplicar_marca.py
git commit -m "$(cat <<'EOF'
feat(kbr-docs): migrar aplicar_marca.py sem depender de PyYAML

O código original importa `yaml` (PyYAML) dentro de uma função — não é biblioteca
padrão, e violaria a regra de nenhum plugin exigir pip install. Escrito um parser
próprio, restrito ao subconjunto de YAML que .docs-brand.yml usa (validado por
round-trip contra o gerador da Task 1), no lugar do PyYAML.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FxSq1YTHKimYYBJmKABcBa
EOF
)"
```

---

## Task 3: `SKILL.md` consolidado — `report-creator`

**Files:**
- Create: `plugins/kbr-docs/skills/report-creator/SKILL.md`

**Interfaces:**
- Consumes: `descobrir.py` (Task 1) e `aplicar_marca.py` (Task 2), via
  `${CLAUDE_PLUGIN_ROOT}/scripts/...`.

Sem teste automatizado (é instrução para o modelo) — a verificação é o validador do Claude
Code.

- [ ] **Step 1: Escrever `plugins/kbr-docs/skills/report-creator/SKILL.md`**

```markdown
---
name: report-creator
description: Gera documentação em HTML com o design system oficial da KINTO — plano, spec, diagnóstico, relatório, manual, avaliação técnica ou conjunto de documentos. Na primeira vez num projeto, descobre a marca (logo, cor, nome) e cria o .docs-brand.yml sozinho; nas vezes seguintes, gera direto a partir dele. Use quando o usuário pedir "documento", "documentação", "relatório em HTML", "gerar relatório", "inicializar a documentação", "configurar a marca do projeto", ou invocar /kbr-docs:report-creator.
---

# Gerador de relatórios — documentação HTML da KINTO

Você gera **documentação em HTML**, sempre a partir do template oficial. **Nunca invente um
layout novo** — se o pedido é um documento, comece por aqui.

## Fluxo

1. Confira se `.docs-brand.yml` existe na raiz do projeto.
2. **Não existe:** descubra a marca primeiro (seção 1 abaixo), depois siga para a geração.
3. **Já existe:** vá direto para a geração (seção 2).

### 1. Descobrir a marca (só na primeira vez por projeto)

**Descobrir — não grava nada:**
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/descobrir.py" .
```
O script varre o repositório e mostra o que encontrou: logos (ignorando `node_modules`,
`dist`, `.venv` e afins), qual serve a que fundo — claro/escuro —, a cor de marca amostrada do
próprio logo, e o nome do projeto (de `package.json`, `.csproj`, do título do `CLAUDE.md` ou
da pasta).

**Conferir com a pessoa.** Mostre o que foi encontrado e pergunte o que o script não tem como
saber: subtítulo, área, classificação, texto de rodapé, autor e revisor. Se o projeto não tem
logo, diga isso — o documento sai com o placeholder, e é melhor que a pessoa saiba antes.

**Gravar:**
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/descobrir.py" . --escrever
```
Não sobrescreve um `.docs-brand.yml` existente. Depois de gravado, a pessoa pode editar à mão
o que faltou — é um YAML (um subconjunto dele, veja "Detalhes que costumam morder"), e os
comentários dizem para que serve cada campo.

### 2. Gerar o documento

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/aplicar_marca.py" docs/<assunto> --raiz=.
# páginas extras já criadas a partir do modelo:
#   --paginas=01-visao,02-arquitetura,03-operacao
```

O script:
1. lê o `.docs-brand.yml` da raiz (se não existir, volte à seção 1);
2. copia `assets/` (design system + runtime) para o destino;
3. instala os logos do projeto por cima dos placeholders, mantendo a extensão original, e a
   foto do autor (`autoria.avatar`) no selo do rodapé — sem foto, ficam as iniciais;
4. escreve `assets/brand.css` com os tokens de marca — carregado **depois** de `docs.css`,
   então atualizar a skill nunca apaga a marca de ninguém;
5. gera os HTML com `{{PROJETO}}`, `{{RODAPE}}`, `{{AUTOR}}` e companhia já substituídos;
6. **nunca sobrescreve** arquivo que já existe.

Leia o relatório no fim: ele diz de onde veio cada logo, ou avisa quando caiu no placeholder.

Para um documento **único**, gere assim mesmo e use só `documento-modelo.html`: a sidebar vira
a lista de seções e o Front Matter pode entrar como primeira seção.

## O que existe nesta skill

```
scripts/
  descobrir.py           descobre marca/logo/nome e escreve .docs-brand.yml
  aplicar_marca.py        gera o conjunto de documentos a partir do .docs-brand.yml
assets/
  docs.css              design system completo (tokens, componentes, layout, claro/escuro)
  docs.js               runtime: tema, codetabs, copiar código, TOC ativo, toast
  logo-claro.svg         PLACEHOLDER — só entra se o projeto não tiver logo
  logo-escuro.svg        PLACEHOLDER
templates/
  front-matter.html     a PÁGINA de controle do documento — sempre o 1º link do menu
  index.html            capa/índice de um conjunto de documentos
  documento-modelo.html  modelo de um documento individual
referencia/
  componentes.html      galeria navegável de TODOS os componentes — consulte antes de inventar
```

## O que o `.docs-brand.yml` guarda

```yaml
projeto:      nome · subtitulo · area · classificacao
logo:         claro · escuro (caminhos relativos à RAIZ) · alt
marca:        claro{brand,hover,tint} · escuro{brand,hover,tint}
textos:       cabecalho · rodape       # rodapé aceita {ano} e {data}
autoria:      autor · cargo · avatar (foto) · revisor
contato:      email · site            # assinatura do rodapé
tipografia:   fontes_externas          # false = sem Google Fonts (offline, e-mail)
saida:        pasta                    # onde os conjuntos de documentos nascem
```

## Regras do `.docs-brand.yml`

- **Logo do projeto vem primeiro, sempre.** O placeholder da skill só entra quando o YAML não
  aponta para arquivo que exista — e, nesse caso, o aviso aparece no relatório da geração.
- **Nada é chutado em silêncio.** Valor que não veio do repositório entra marcado com
  `# SUGESTÃO — confira`.
- **Um arquivo por projeto, na raiz.** Ele é a fonte da verdade da identidade.
- **Versione o `.docs-brand.yml`.** Ele é configuração de projeto, não segredo.
- **O leitor é um subconjunto de YAML, não um parser completo.** Suporta mapeamentos
  aninhados até 3 níveis, valores entre aspas duplas ou `true`/`false`, comentários com `#`.
  Não suporta lista, âncora, bloco multilinha nem aspas simples — se o arquivo tiver algo
  assim (editado à mão fora do padrão que a skill gera), a geração pode ler o valor errado.

## Regras do padrão (não negociáveis)

- **Header:** só logo (clicável, leva ao índice) + alternador de tema. Sem "Exportar", sem
  "Compartilhar", sem busca.
- **Front Matter é uma PÁGINA** (`front-matter.html`), **sempre o 1º link** do menu — nunca um
  bloco no topo dos outros documentos. Contém: ID, Título, Status, Versão, Classificação,
  Projeto/Área, Autor, Revisor/Aprovador, Criado em, Atualizado em, Tags, **Histórico de
  revisões** e **Detalhes das versões**.
- **Governança do histórico:** *Histórico de revisões* e *Detalhes das versões* só recebem
  entrada nova quando o `Status` for **Published**. Em `Draft` ou `Em revisão`, muda apenas
  *Atualizado em* (e a *Versão*, se for o caso).
- **Status:** `Draft` (neutral) · `Em revisão` (warning) · `Published` (success) ·
  `Obsoleto` (danger).
- **Navegação:** menu ESQUERDO = páginas do conjunto (um HTML por link, Front Matter primeiro);
  menu DIREITO = âncoras da página atual. Nunca duplicar a mesma navegação nos dois.
- **Layout:** header fixo; sidebar e TOC `sticky`; quem rola é o shell. O `<footer>` fica
  **dentro** do `<main>` (rola junto) e sangra até as bordas da janela.
- **Marca:** nunca escreva cor ou caminho de logo direto no HTML. Tudo vem do
  `.docs-brand.yml` → `assets/brand.css`. Mudou a marca? Edite o YAML e gere de novo.
- **Exemplos de código:** sempre nas três linguagens (Python, Java, C#) pelo componente
  `.codetabs`, quando o assunto comportar.
- **Componentes: COPIE a marcação, não escreva de cabeça.** Abra
  `referencia/componentes.html`, copie o bloco do componente e troque só o texto. Tem
  callouts, tabelas, badges, steps, tabs, FAQ, timeline, stat/feature/hero cards, kbd,
  codetabs e gráficos em CSS puro (barras, progress, donut, gauge, heatmap).

  O CSS depende da **estrutura exata**. Escrever "quase igual" quebra em silêncio e só
  aparece no navegador. O caso mais comum é o callout, um **grid de duas colunas** — filho
  solto dentro dele vira célula do grid, o `<b>` herda o estilo de título (bloco + caixa-alta)
  e o texto se sobrepõe ao `<code>` ao lado:

  ```html
  <!-- ERRADO: filhos soltos -->        <!-- CERTO: ícone + bloco de conteúdo -->
  <div class="callout callout--info">   <div class="callout callout--info">
    <b>Título</b> texto <code>x</code>    <span class="ico">i</span>
  </div>                                  <div><b>Título</b><p>texto</p></div>
                                        </div>
  ```

  Ícone por tipo: `i` info · `!` warning · `✓` success · `×` danger · `•` neutral.

## Conteúdo — como escrever o documento

- **Afirme o que foi medido.** Número na página é número verificado; o que é estimativa vem
  marcado como estimativa.
- **Escopo em duas colunas: dentro e fora.** O que fica de fora, escrito, evita a discussão
  que volta toda semana.
- **Critério de aceite por item.** Um documento sem "como saber que terminou" não é plano.
- Português do Brasil, com acentuação correta. Termos técnicos e identificadores de código
  ficam na forma original.

## Detalhes que costumam morder

- O template carrega **Inter** e **JetBrains Mono** do Google Fonts. Documento que vá circular
  por e-mail ou rodar sem internet deve usar `tipografia.fontes_externas: false` no YAML — a
  geração remove os links e a página continua correta, só muda a tipografia.
- O tema é escrito em `data-theme` no `<html>`; `docs.js` lembra a escolha em `localStorage`.
- Logo de marca costuma ser um PNG grande. Acima de 500 KB o script avisa — vale gerar uma
  versão reduzida só para a documentação. A foto do autor tem o mesmo aviso a partir de
  300 KB: ela aparece em 48px, recortada no centro.
- **A folha impressa é sempre clara**, mesmo com o leitor no tema escuro: o `@media print`
  redefine os tokens na raiz, e a marca clara é repetida ali porque `brand.css` é carregado
  depois do `docs.css`. Header, sidebar, TOC e o botão de copiar somem; o bloco de código
  continua escuro de propósito.
- **A detecção automática de cor/luminância de logo em PNG precisa do Pillow — que é
  opcional.** Sem Pillow instalado, esses campos do YAML saem como `# SUGESTÃO — confira` em
  vez de preenchidos sozinhos. Logo em `.svg` não depende disso (a cor é lida do próprio
  código do arquivo). Nunca trate a ausência de Pillow como erro — é o comportamento normal.
- Ao publicar um conjunto novo, abra pelo menos uma página no navegador e confira: alternador
  de tema, links da sidebar, âncoras do TOC e a impressão (Ctrl+P).
```

- [ ] **Step 2: Validar a skill**

```bash
claude plugin validate --strict plugins/kbr-docs
```
Esperado: sem erros. Se o YAML do frontmatter reclamar, confira se não há `: ` (dois-pontos
seguido de espaço) fora de travessão dentro do valor de `description`.

- [ ] **Step 3: Commit**

```bash
git add plugins/kbr-docs/skills/report-creator/SKILL.md
git commit -m "$(cat <<'EOF'
feat(kbr-docs): SKILL.md consolidado da report-creator — descoberta + geração num fluxo só

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FxSq1YTHKimYYBJmKABcBa
EOF
)"
```

---

## Task 4: README, `marketplace.json` e verificação final

**Files:**
- Create: `plugins/kbr-docs/README.md`
- Modify: `.claude-plugin/marketplace.json`

- [ ] **Step 1: Escrever o README**

Crie `plugins/kbr-docs/README.md`:
```markdown
# kbr-docs

Gera documentação em HTML com o design system oficial da KINTO, dentro do Claude Code.

## Skills

- **`/kbr-docs:report-creator`** — descobre a marca do projeto (logo, cor, nome) na primeira
  vez e cria o `.docs-brand.yml` sozinho; nas vezes seguintes, gera direto a partir dele. Um
  documento único ou um conjunto inteiro (visão, arquitetura, operação...), sempre no mesmo
  template — header, sidebar, TOC, Front Matter como página própria, tema claro/escuro.

## Primeira vez num projeto

Abra `/kbr-docs:report-creator` e peça um documento qualquer — a skill percebe sozinha que
falta o `.docs-brand.yml`, descobre o que existe no repositório (logo, nome), confirma com
você o que não deu para descobrir sozinho, e já segue para gerar o documento.

## O que ele guarda, e onde

| Onde | O quê |
|---|---|
| `.docs-brand.yml`, na raiz do projeto documentado | identidade visual — logo, cor, nome, autoria. Não é segredo; versione. |
| `docs/<assunto>/` (ou o destino pedido) | os HTML gerados, com `assets/` copiado junto |

Nada disso entra em `kbr-docs` — cada projeto documentado guarda a própria identidade.

## Pré-requisitos

Python 3.10 ou superior no `PATH`. Nenhuma biblioteca externa é obrigatória — a leitura do
`.docs-brand.yml` usa um parser próprio, sem PyYAML. Pillow é **opcional**: sem ele, a
detecção automática de cor/luminância de logo em PNG (não em SVG) fica marcada como
sugestão a conferir, em vez de preenchida sozinha.

## Fora de escopo nesta versão

PDF, apresentações (PPTX — fica para um plugin/skill futuro, `presentation-creator`), e
`kb-doc-creator` (documentos `.md` padronizados tipo ADR/runbook — outra ferramenta, outro
propósito).
```

- [ ] **Step 2: Acrescentar a entrada em `marketplace.json`**

Em `.claude-plugin/marketplace.json`, troque:
```json
    {
      "name": "kbr-servicedesk",
      "description": "Gestor de chamados do ServiceDesk Plus por menu, com wizard de configuração, e extração de dados para CSV/analytics",
      "source": "./plugins/kbr-servicedesk",
      "category": "productivity"
    }
  ]
}
```
por:
```json
    {
      "name": "kbr-servicedesk",
      "description": "Gestor de chamados do ServiceDesk Plus por menu, com wizard de configuração, e extração de dados para CSV/analytics",
      "source": "./plugins/kbr-servicedesk",
      "category": "productivity"
    },
    {
      "name": "kbr-docs",
      "description": "Gera documentação em HTML com o design system oficial da KINTO, descobrindo a marca do projeto sozinho",
      "source": "./plugins/kbr-docs",
      "category": "productivity"
    }
  ]
}
```

- [ ] **Step 3: Rodar a suíte completa e o validador**

```bash
python scripts/testar.py
python scripts/validar.py
```
Esperado: `OK` na suíte (agora incluindo os 30 testes de `kbr-docs`); `Validation passed` para
o marketplace e os três plugins (`kbr-core`, `kbr-servicedesk`, `kbr-docs`).

- [ ] **Step 4: Commit**

```bash
git add plugins/kbr-docs/README.md .claude-plugin/marketplace.json
git commit -m "$(cat <<'EOF'
docs(kbr-docs): README e entrada no marketplace — plugin pronto para publicar

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FxSq1YTHKimYYBJmKABcBa
EOF
)"
```

- [ ] **Step 5: Criar e publicar a tag**

```bash
python scripts/criar_tag.py kbr-docs --push
```
Esperado: `tag criada: kbr-docs--v0.1.0` e confirmação do push. **Confirme com o usuário antes
deste step** — publicar no marketplace é uma ação visível para toda a organização. Confirme
também, antes deste step, que a **branch `main` local está de fato com `origin/main`** (não
só as tags) — `git status -sb` deve mostrar `## main...origin/main` sem "ahead"/"behind". Já
aconteceu nesta mesma sessão de só publicar tag sem publicar a branch por trás dela.

---

## Self-Review (já aplicado ao escrever este plano)

1. **Cobertura da spec:** seções 1-6 da spec cobertas: Task 1 (descoberta), Task 2 (geração +
   o achado do PyYAML, seção "Fatos que tornam a migração mecânica" corrigida), Task 3 (skill
   consolidada, fluxo da seção 3 da spec), Task 4 (plugin.json/marketplace.json da seção 4,
   testes da seção 5). Seção 6 (fora de escopo) não gerou task nenhuma, de propósito.
2. **Placeholders:** nenhum "TBD"/"depois" — todo step tem código completo. As duas únicas
   mudanças de comportamento (parser de YAML, texto do comentário gerado) estão explicadas e
   justificadas, não escondidas.
3. **Consistência de tipos:** `carregar_yaml_simples(texto: str) -> dict` e
   `carregar_yaml(caminho: Path) -> dict` (Task 2) usam os mesmos nomes que o `SKILL.md`
   (Task 3) pressupõe implicitamente ao descrever o fluxo; `montar_yaml` (Task 1) é consumida
   por nome idêntico no teste de round-trip da Task 2.
4. **Achado do brainstorming preservado:** a dependência real de PyYAML (não capturada na
   spec original, só descoberta ao ler o arquivo inteiro nesta fase de planejamento) está
   registrada nas Global Constraints, na Task 2 e no commit da Task 2 — não é um desvio
   silencioso do plano em relação à spec, é uma correção documentada no próprio plano.
5. **Lição da fatia anterior (`query`) aplicada:** o Step 5 da Task 4 lembra explicitamente de
   conferir que a branch `main` foi publicada, não só a tag — exatamente o erro que aconteceu
   na publicação da `/kbr-servicedesk:query` nesta mesma sessão.
