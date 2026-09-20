# Converter HTML → PDF (kbr-docs) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dar ao `kbr-docs` um script autocontido que converte um arquivo HTML local em PDF, chamando um navegador Chromium já instalado na máquina — sem Playwright, sem nenhuma dependência Python nova.

**Architecture:** Um script novo, `converter_pdf.py`, dentro do mesmo `scripts/` dos outros três scripts da skill `report-creator`. Ele acha um navegador Chromium instalado (variável de ambiente → caminhos padrão do Windows → PATH) e chama `subprocess.run([...])` com as flags de impressão headless já testadas na prática. Zero integração com o resto do plugin — recebe um caminho de entrada, devolve um arquivo de saída.

**Tech Stack:** Python ≥ 3.10, só biblioteca padrão (`subprocess`, `shutil`, `pathlib`, `os`). Testes com `unittest`, incluindo testes de integração real (sem mock) contra um navegador de verdade, pulados com `skipUnless` quando a máquina não tiver nenhum.

## Global Constraints

- Spec aprovada: `docs/superpowers/specs/2026-09-18-converter-html-pdf-kbr-docs-design.md` — qualquer dúvida de comportamento, essa é a fonte da verdade.
- PT-BR em todo texto/comentário/docstring/commit novo.
- Python ≥ 3.10, só biblioteca padrão — **nenhuma dependência nova, Playwright incluído**.
- `python scripts/testar.py` e `python scripts/validar.py --strict`, rodados da raiz do repositório (`E:\Projetos\Kinto Brasil\src\github\KBR-Claude-Plugins`), precisam continuar limpos depois da task.
- Trabalho direto na `main`, sem branch isolada — mesmo padrão já usado em todas as fatias anteriores desta sessão.
- Nenhum commit tem push — só local, até decisão explícita.
- **Nunca `git add -A`.** Nomeie os caminhos exatos.
- Flags do navegador já verificadas na prática (Edge, nesta máquina, gerou um PDF válido de primeira): `--headless --disable-gpu --print-to-pdf=<saida> --no-pdf-header-footer file:///<entrada-absoluta-em-posix>`.
- `KBR_DOCS_BROWSER`, quando definida, é **autoritativa** — não cai pros outros métodos de busca se o caminho nela não existir; isso é erro de configuração, não "tenta o resto".
- Escopo desta fatia: só conversão de UM arquivo por vez. Sem lote/pasta, sem ligação com o `gestor-chamados` (fica pra depois, fora deste repositório), sem atualizar a memória `feedback_sdp_anexar_discovery_e_solucao`.
- Arquivos tocados, caminho completo a partir da raiz do repositório:
  - `plugins/kbr-docs/skills/report-creator/scripts/converter_pdf.py` (novo)
  - `plugins/kbr-docs/tests/test_converter_pdf.py` (novo)
  - `plugins/kbr-docs/skills/report-creator/SKILL.md`

---

### Task 1: `converter_pdf.py` — script completo, com TDD

**Files:**
- Create: `plugins/kbr-docs/skills/report-creator/scripts/converter_pdf.py`
- Create: `plugins/kbr-docs/tests/test_converter_pdf.py`

**Interfaces:**
- Produces: `converter_pdf.achar_navegador() -> Path` (levanta `converter_pdf.ErroNavegadorNaoEncontrado` se não achar nada), `converter_pdf.converter(entrada: Path, saida: Path, navegador: Path) -> None` (levanta `converter_pdf.ErroConversao` em falha), `converter_pdf.main() -> int`. Nenhuma outra task consome isso nesta fatia — é o produto final.

- [ ] **Step 1: Escrever os testes de `achar_navegador()` (falham — a função não existe ainda)**

Crie `plugins/kbr-docs/tests/test_converter_pdf.py`:

```python
# -*- coding: utf-8 -*-
"""Testes de converter_pdf.py: conversao de HTML local em PDF via navegador."""
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

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
    '<body><h1>Teste</h1><p>Pagina minima para o converter_pdf.py.</p></body></html>'
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
        self.assertIn(str(saida), texto_saida)

    @unittest.skipUnless(_navegador_disponivel(), "nenhum navegador Chromium encontrado")
    def test_sem_saida_explicita_usa_mesmo_nome_com_pdf(self):
        codigo, _, _ = _rodar(str(self.entrada))
        self.assertEqual(codigo, 0)
        esperado = self.entrada.with_suffix(".pdf")
        self.assertTrue(esperado.exists())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar e confirmar que falha (o módulo `converter_pdf` não existe ainda)**

```bash
cd "E:\Projetos\Kinto Brasil\src\github\KBR-Claude-Plugins"
python "plugins/kbr-docs/tests/test_converter_pdf.py" -v
```

Esperado: `ModuleNotFoundError: No module named 'converter_pdf'`.

- [ ] **Step 3: Implementar `converter_pdf.py`**

Crie `plugins/kbr-docs/skills/report-creator/scripts/converter_pdf.py`:

```python
#!/usr/bin/env python3
"""
Converte um arquivo HTML local em PDF, chamando (via subprocess) um navegador
Chromium já instalado na máquina em modo headless — sem Playwright, sem
nenhuma dependência Python nova.

Uso:
    python converter_pdf.py <entrada.html> [saida.pdf]

Sem `saida.pdf`, usa o mesmo nome de `entrada.html` com a extensão trocada
pra `.pdf`, na mesma pasta. O `@media print` do CSS da própria página entra
em ação sozinho — é o mesmo comportamento de apertar Ctrl+P no navegador.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

CAMINHOS_PADRAO_WINDOWS = (
    r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
    r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
    r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files\Google\Chrome\Application\chrome.exe',
)

NOMES_NO_PATH = ('msedge', 'chrome', 'chromium')


class ErroNavegadorNaoEncontrado(Exception):
    pass


class ErroConversao(Exception):
    pass


def achar_navegador() -> Path:
    """
    Acha um navegador Chromium instalado, nesta ordem: variável de ambiente
    KBR_DOCS_BROWSER, caminhos padrão do Windows (Edge, depois Chrome), e por
    fim o PATH. Levanta ErroNavegadorNaoEncontrado (mensagem em PT-BR) se não
    achar nada.

    KBR_DOCS_BROWSER, quando definida, é AUTORITATIVA — não cai pros outros
    métodos se o caminho nela não existir; isso é erro de configuração, não
    "tenta o resto".
    """
    override = os.environ.get('KBR_DOCS_BROWSER')
    if override:
        caminho = Path(override)
        if caminho.exists():
            return caminho
        raise ErroNavegadorNaoEncontrado(
            f'KBR_DOCS_BROWSER aponta para um caminho que não existe: {override}')

    for bruto in CAMINHOS_PADRAO_WINDOWS:
        caminho = Path(bruto)
        if caminho.exists():
            return caminho

    for nome in NOMES_NO_PATH:
        achado = shutil.which(nome)
        if achado:
            return Path(achado)

    tentativas = '\n'.join(f'  - {c}' for c in CAMINHOS_PADRAO_WINDOWS)
    tentativas += '\n' + '\n'.join(f'  - shutil.which("{n}")' for n in NOMES_NO_PATH)
    raise ErroNavegadorNaoEncontrado(
        f'Não achei nenhum navegador Chromium instalado. Tentei:\n{tentativas}\n\n'
        f'Defina KBR_DOCS_BROWSER com o caminho do executável, se tiver um instalado '
        f'em lugar não padrão.')


def converter(entrada: Path, saida: Path, navegador: Path) -> None:
    """
    Roda `navegador` em modo headless pra gerar `saida` a partir de `entrada`.
    Levanta ErroConversao (mensagem em PT-BR) se o processo falhar ou não
    produzir o arquivo esperado.
    """
    comando = [
        str(navegador),
        '--headless',
        '--disable-gpu',
        f'--print-to-pdf={saida}',
        '--no-pdf-header-footer',
        f'file:///{entrada.resolve().as_posix()}',
    ]
    try:
        resultado = subprocess.run(comando, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as erro:
        raise ErroConversao(f'Não consegui rodar {navegador}: {erro}') from erro

    if resultado.returncode != 0:
        raise ErroConversao(
            f'{navegador.name} terminou com código {resultado.returncode}.\n'
            f'{resultado.stderr.strip()}')

    if not saida.exists():
        raise ErroConversao(
            f'{navegador.name} terminou sem erro, mas {saida} não foi criado.\n'
            f'{resultado.stderr.strip()}')


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

    entrada = Path(args[0]).resolve()
    if not entrada.exists():
        print(f'Não achei {entrada}.', file=sys.stderr)
        return 1

    saida = Path(args[1]).resolve() if len(args) > 1 else entrada.with_suffix('.pdf')

    try:
        navegador = achar_navegador()
    except ErroNavegadorNaoEncontrado as erro:
        print(str(erro), file=sys.stderr)
        return 1

    try:
        converter(entrada, saida, navegador)
    except ErroConversao as erro:
        print(str(erro), file=sys.stderr)
        return 1

    print(f'gerado: {saida}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

```bash
python "plugins/kbr-docs/tests/test_converter_pdf.py" -v
```

Esperado: todos os testes em `ok` (os que dependem de navegador de verdade rodam nesta máquina, já confirmado que Edge está instalado; em uma máquina sem nenhum navegador, eles aparecem como `skipped` em vez de falhar).

- [ ] **Step 5: Rodar a suíte inteira do plugin**

```bash
cd "E:\Projetos\Kinto Brasil\src\github\KBR-Claude-Plugins"
python scripts/testar.py
python scripts/validar.py --strict
```

Esperado: número de testes MAIOR que o total antes desta task (279), todos OK; validador limpo.

- [ ] **Step 6: Acrescentar a menção no `SKILL.md`**

Em `plugins/kbr-docs/skills/report-creator/SKILL.md`, confirme que existe, hoje, exatamente isto:

```markdown
Para um documento **único**, gere assim mesmo e use só `documento-modelo.html`: a sidebar vira
a lista de seções e o Front Matter pode entrar como primeira seção.

## O que existe nesta skill
```

Troque por:

```markdown
Para um documento **único**, gere assim mesmo e use só `documento-modelo.html`: a sidebar vira
a lista de seções e o Front Matter pode entrar como primeira seção.

### Exportar para PDF

```bash
python "${CLAUDE_PLUGIN_ROOT}/skills/report-creator/scripts/converter_pdf.py" docs/<assunto>/index.html
```

Útil pra quem vai anexar o documento em algum lugar que não abre HTML inline (ex.: ServiceDesk —
o portal baixa `.html` como arquivo bruto em vez de pré-visualizar). Chama um navegador Chromium
já instalado na máquina — sem depender de nenhuma ferramenta nova. Sem o segundo argumento, o PDF
nasce ao lado do HTML, com o mesmo nome.

## O que existe nesta skill
```

Também confirme que existe, hoje, exatamente isto (dentro do bloco `scripts/` do inventário):

```
scripts/
  resolver_marca.py      cascata de três níveis (projeto→usuário→placeholder); `python resolver_marca.py <raiz>` mostra o efetivo sem gravar
  descobrir.py           descobre marca/logo/nome e escreve .docs-brand.yml
  aplicar_marca.py        gera o conjunto de documentos a partir do .docs-brand.yml
```

Troque por:

```
scripts/
  resolver_marca.py      cascata de três níveis (projeto→usuário→placeholder); `python resolver_marca.py <raiz>` mostra o efetivo sem gravar
  descobrir.py           descobre marca/logo/nome e escreve .docs-brand.yml
  aplicar_marca.py        gera o conjunto de documentos a partir do .docs-brand.yml
  converter_pdf.py        converte um HTML local em PDF via navegador já instalado na máquina
```

- [ ] **Step 7: Rodar `validar.py --strict` de novo — confirma que o `SKILL.md` continua bem formado**

```bash
python scripts/validar.py --strict
```

- [ ] **Step 8: Commit**

```bash
git add plugins/kbr-docs/skills/report-creator/scripts/converter_pdf.py plugins/kbr-docs/tests/test_converter_pdf.py plugins/kbr-docs/skills/report-creator/SKILL.md
git commit -m "$(cat <<'EOF'
feat(kbr-docs): converter HTML->PDF via navegador local

Script novo, converter_pdf.py, na skill report-creator: converte um
arquivo HTML local em PDF chamando (via subprocess) um navegador
Chromium ja instalado na maquina, em modo headless -- sem Playwright,
sem nenhuma dependencia Python nova. Motivado pela regra do
gestor-chamados (fora deste repositorio) de nunca anexar HTML ao
ServiceDesk, so PDF (achado no chamado #4845).

achar_navegador(): KBR_DOCS_BROWSER (autoritativa) -> caminhos padrao
do Windows (Edge, Chrome) -> PATH. Testes de integracao reais (sem
mock), pulados com skipUnless quando a maquina nao tem navegador.

$(python "plugins/kbr-docs/tests/test_converter_pdf.py" -v 2>&1 | tail -3)
EOF
)"
```

---

## Self-Review (feito pelo controlador antes de despachar)

**1. Cobertura da spec:** §3 (interface) → Step 3 (`main()`); §4 (descoberta do navegador) →
`achar_navegador()`; §5 (execução/erro) → `converter()`; §6 (testes) → Step 1, todas as
variações listadas (entrada inexistente, `KBR_DOCS_BROWSER` inválido, navegador não achado,
sucesso, `skipUnless`); §7 (documentação) → Step 6; §8 (fora de escopo) → nada desta task toca
`gestor-chamados` nem a memória. Nenhuma lacuna.

**2. Placeholder scan:** nenhum "TBD"/"implementar depois" — todo código é completo e executável.

**3. Consistência de tipo:** `achar_navegador() -> Path` (levanta, não devolve `None`) é usado
de forma consistente em `main()` (bloco `try/except ErroNavegadorNaoEncontrado`) e nos testes
(`_navegador_disponivel()` usa o mesmo padrão try/except). `converter(entrada: Path, saida: Path,
navegador: Path) -> None` (levanta `ErroConversao`) é chamado com essa assinatura exata em todos
os pontos (Step 3's `main()`, e os testes `TesteConverter`).
