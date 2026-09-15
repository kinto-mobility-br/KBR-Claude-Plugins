# Alternador de menu horizontal/vertical (kbr-docs) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dar à pessoa que lê um documento gerado pelo `kbr-docs` um botão, no cabeçalho, para trocar a navegação lateral vertical por uma faixa horizontal full-width — persistido no navegador dela, como o tema.

**Architecture:** Um atributo `data-menu` (`vertical` | `horizontal`) no `<html>`, escrito por `docs.js` e lido em `localStorage` (chave `kinto-menu`) — cópia exata do mecanismo que `data-theme`/`kinto-theme` já usa. Todo o resto é CSS puro sob o seletor `:root[data-menu="horizontal"]`: o grid do `.shell` vira uma coluna, `.side` (mesma marcação de sempre, sem duplicar links) vira uma faixa sticky embaixo do cabeçalho, `.toc` some, e o token `--measure` ganha um limite de leitura.

**Tech Stack:** CSS/HTML/JS estático (sem framework, sem build step) — mesmas três pastas do plugin (`assets/`, `templates/`). Nenhum código Python muda.

## Global Constraints

- Spec aprovada: `docs/superpowers/specs/2026-09-15-menu-horizontal-toggle-design.md` — qualquer dúvida de comportamento, essa é a fonte da verdade.
- PT-BR em todo texto/comentário novo (regra do `CLAUDE.md` do repositório).
- `python scripts/testar.py` (257 testes) e `python scripts/validar.py --strict`, rodados da raiz do repositório (`E:\Projetos\Kinto Brasil\src\github\KBR-Claude-Plugins`), precisam continuar limpos depois de CADA task — é o jeito de provar que nada em Python foi tocado.
- Trabalho direto na `main`, sem branch isolada — mesmo padrão já usado nas três fatias anteriores desta sessão (redução de escala, rodapé, e a correção de link/rótulo antes dela).
- Nenhum commit tem push — só local. O push fica para o Fábio decidir, junto com a tag `kbr-docs--v0.1.1` que já está pendente das fatias anteriores.
- **Nunca `git add -A`.** Nomeie os caminhos exatos.
- Arquivos tocados, sempre pelo caminho completo a partir da raiz do repositório:
  - `plugins/kbr-docs/skills/report-creator/assets/docs.css`
  - `plugins/kbr-docs/skills/report-creator/assets/docs.js`
  - `plugins/kbr-docs/skills/report-creator/templates/documento-modelo.html`
  - `plugins/kbr-docs/skills/report-creator/templates/front-matter.html`
  - `plugins/kbr-docs/skills/report-creator/templates/index.html`
- **Não existe suíte de teste Python para HTML/CSS/JS.** A verificação de cada task é visual, real, no navegador, via Playwright (MCP `mcp__plugin_playwright_playwright__*`) — sem isso, "parece certo" não vale como prova. `file://` é bloqueado no Playwright: sirva a pasta por HTTP (`python -m http.server`) antes de navegar.
- Repita o mesmo comando `mktemp -d` (ou equivalente) em cada task que precisar de pasta de teste — nunca reaproveite pasta de task anterior sem regenerar (evita "funcionou por acaso com HTML velho").

---

## Setup usado em toda task de verificação visual

Cada task abaixo que precisa ver o resultado no navegador segue este roteiro. Os comandos usam `bash` (Git Bash) — troque `$SCRATCH` pelo caminho que `mktemp -d` devolver.

```bash
SCRATCH=$(mktemp -d)
cd "$SCRATCH"
python "/e/Projetos/Kinto Brasil/src/github/KBR-Claude-Plugins/plugins/kbr-docs/skills/report-creator/scripts/descobrir.py" . --escrever
python "/e/Projetos/Kinto Brasil/src/github/KBR-Claude-Plugins/plugins/kbr-docs/skills/report-creator/scripts/aplicar_marca.py" docs/x --raiz=.
cd docs/x
python -m http.server 8799 --bind 127.0.0.1 &
```

Depois, navegue com Playwright para `http://127.0.0.1:8799/documento-modelo.html` (ou `front-matter.html`/`index.html`). Ao terminar a task, mate o servidor:

```bash
kill %1
```

---

### Task 1: CSS — layout do menu horizontal (`.shell`/`.side`/`.toc`/`--measure`)

Só o CSS estrutural, sob `:root[data-menu="horizontal"]` — sem botão, sem JS ainda. Testável ligando o atributo manualmente pelo Playwright.

**Files:**
- Modify: `plugins/kbr-docs/skills/report-creator/assets/docs.css`

**Interfaces:**
- Produces: o seletor `:root[data-menu="horizontal"]` — as tasks 2 e 3 vão fazer o JS escrever esse atributo no `<html>`.

- [ ] **Step 1: Ler o trecho atual do `.content` que antecede o primeiro `@media`**

Confirme que existe, hoje, exatamente isto (linhas ~232-233 de `docs.css`):

```css
.content{min-height:calc(100vh - var(--hdr-h));padding:var(--gap-xl) var(--gap-2xl) 0}
@media(max-width:1200px){.shell{--side-w:210px;--toc-w:0px;grid-template-columns:var(--side-w) 1fr}.toc{display:none}}
```

- [ ] **Step 2: Inserir o bloco novo entre essas duas linhas**

Usando o `Edit` tool (ou `sed`/edição manual), troque:

```css
.content{min-height:calc(100vh - var(--hdr-h));padding:var(--gap-xl) var(--gap-2xl) 0}
@media(max-width:1200px){.shell{--side-w:210px;--toc-w:0px;grid-template-columns:var(--side-w) 1fr}.toc{display:none}}
```

por:

```css
.content{min-height:calc(100vh - var(--hdr-h));padding:var(--gap-xl) var(--gap-2xl) 0}

/* =====================================================================
   MENU HORIZONTAL — alternativa à sidebar vertical. Ligado por
   data-menu="horizontal" no <html>, escrito por docs.js e persistido em
   localStorage (chave kinto-menu) — mesmo mecanismo do data-theme.
   ===================================================================== */
:root[data-menu="horizontal"]{--measure:760px}
:root[data-menu="horizontal"] .shell{--side-w:0px;--toc-w:0px;grid-template-columns:1fr}
:root[data-menu="horizontal"] .toc{display:none}
:root[data-menu="horizontal"] .side{
  position:sticky;top:0;z-index:40;overflow:hidden;
  border-right:0;border-bottom:1px solid var(--border);
  padding:0 var(--gap-lg);height:48px;max-height:none;
  display:flex;align-items:center;
}
:root[data-menu="horizontal"] .side h6{display:none}
:root[data-menu="horizontal"] .side nav{width:100%;overflow-x:auto}
:root[data-menu="horizontal"] .side ul{display:flex;flex-direction:row;gap:6px;white-space:nowrap}
:root[data-menu="horizontal"] .side li a{white-space:nowrap}

@media(max-width:1200px){.shell{--side-w:210px;--toc-w:0px;grid-template-columns:var(--side-w) 1fr}.toc{display:none}}
```

Note que `.shell` sem `.toc` (que fica `display:none`) e com `grid-template-columns:1fr` empilha `.side` e `.content` em duas LINHAS pela ordem em que já aparecem no HTML — não precisa de `grid-template-areas` nem `grid-template-rows` explícitos.

`top:0`, e não `top:var(--hdr-h)`: o contêiner de rolagem do `position:sticky` do `.side` é o `.shell` (que já tem `overflow-y:auto`), não o viewport — e o `.shell` já começa exatamente onde o `.hdr` termina (`.hdr` é um `sticky` à parte, fora do `.shell`). `top:0` cola o `.side` na borda superior do PRÓPRIO `.shell`, que visualmente já é a borda inferior do cabeçalho — exatamente como o modo vertical já faz hoje (`.side{position:sticky;top:0;...}`, veja a regra sem o `data-menu`). Somar `var(--hdr-h)` de novo aqui contaria a altura do cabeçalho duas vezes e abriria um vão permanente de 56px entre o cabeçalho e a faixa, em qualquer posição de rolagem — não é um detalhe cosmético do carregamento inicial, é a lacuna que apareceria sempre.

`overflow:hidden` no `.side`: sem isso, a regra base do `.side` (fora deste bloco) já define `overflow:auto`, herdada aqui — com a altura fixa em 48px, uma lista de navegação mais longa poderia abrir uma barra de rolagem vertical indesejada na própria faixa. Quem rola horizontalmente é o `<nav>` interno (`overflow-x:auto`, linha acima), não o `.side`.

- [ ] **Step 3: Rodar `testar.py` e `validar.py --strict` — nada em Python muda, então nada deve quebrar**

```bash
cd "E:\Projetos\Kinto Brasil\src\github\KBR-Claude-Plugins"
python scripts/testar.py
python scripts/validar.py --strict
```

Esperado: `Ran 257 tests ... OK (skipped=1)` e `marketplace e todos os plugins existentes passaram na validação`.

- [ ] **Step 4: Gerar uma pasta de teste e servir por HTTP (roteiro do topo do plano)**

```bash
SCRATCH=$(mktemp -d)
cd "$SCRATCH"
python "/e/Projetos/Kinto Brasil/src/github/KBR-Claude-Plugins/plugins/kbr-docs/skills/report-creator/scripts/descobrir.py" . --escrever
python "/e/Projetos/Kinto Brasil/src/github/KBR-Claude-Plugins/plugins/kbr-docs/skills/report-creator/scripts/aplicar_marca.py" docs/x --raiz=.
cd docs/x
python -m http.server 8799 --bind 127.0.0.1 &
```

- [ ] **Step 5: Navegar e ligar o modo horizontal manualmente (ainda sem botão)**

Com o Playwright MCP:

1. `mcp__plugin_playwright_playwright__browser_navigate` para `http://127.0.0.1:8799/documento-modelo.html`.
2. `mcp__plugin_playwright_playwright__browser_run_code_unsafe` com:

```js
async (page) => {
  await page.evaluate(() => document.documentElement.setAttribute('data-menu', 'horizontal'));
  await page.waitForTimeout(150);
  return await page.evaluate(() => {
    const side = document.querySelector('.side').getBoundingClientRect();
    const toc = getComputedStyle(document.querySelector('.toc')).display;
    const lead = getComputedStyle(document.querySelector('.doc-lead')).maxWidth;
    const calloutP = getComputedStyle(document.querySelector('.callout p')).maxWidth;
    return { sideTop: side.top, sideHeight: side.height, sideWidth: side.width, tocDisplay: toc, leadMaxWidth: lead, calloutPMaxWidth: calloutP };
  });
}
```

Esperado: `sideTop` igual à altura do header (56), `sideHeight` 48, `sideWidth` igual à largura da viewport (a faixa ocupa 100%), `tocDisplay` `"none"`, `leadMaxWidth` `"760px"`, `calloutPMaxWidth` `"none"` (o callout continua sem limite — só o texto corrido é que ganhou a margem).

- [ ] **Step 6: Tirar um screenshot pra confirmar visualmente**

`mcp__plugin_playwright_playwright__browser_take_screenshot` com `fullPage: true`. Confira: a faixa da sidebar (com os 3 links) agora é horizontal, ocupando a largura toda, colada embaixo do cabeçalho; o TOC desapareceu; o texto do `doc-lead` não se estica até a borda.

- [ ] **Step 7: Encerrar o servidor**

```bash
kill %1
```

- [ ] **Step 8: Commit**

```bash
cd "E:\Projetos\Kinto Brasil\src\github\KBR-Claude-Plugins"
git add plugins/kbr-docs/skills/report-creator/assets/docs.css
git commit -m "feat(kbr-docs): CSS do menu horizontal (data-menu=horizontal)

Faixa full-width sticky no lugar da sidebar vertical, TOC escondido, e
--measure limitando a largura do texto corrido — tudo sob
:root[data-menu=\"horizontal\"]. Ainda sem botao/JS (task seguinte).
Verificado ligando o atributo manualmente via Playwright: sidebar vira
faixa de 48px 100% da largura, colada nos 56px do cabecalho; TOC some;
doc-lead limitado a 760px; callout continua sem limite."
```

---

### Task 2: Botão no cabeçalho + `docs.js` — controle completo, no `documento-modelo.html`

O botão (CSS + marcação) e a lógica (JS) só fazem sentido testados juntos — é isso que torna a task completa e testável de ponta a ponta. Entra primeiro só no `documento-modelo.html`; a Task 3 propaga para os outros dois.

**Files:**
- Modify: `plugins/kbr-docs/skills/report-creator/assets/docs.css`
- Modify: `plugins/kbr-docs/skills/report-creator/assets/docs.js`
- Modify: `plugins/kbr-docs/skills/report-creator/templates/documento-modelo.html`

**Interfaces:**
- Consumes: o seletor `:root[data-menu="horizontal"]` da Task 1.
- Produces: a classe `.menu-toggle` (marcação e CSS) e a chave `localStorage` `kinto-menu` — a Task 3 replica a MESMA marcação HTML nos outros dois templates.

- [ ] **Step 1: Adicionar o CSS do botão — cópia do `.theme-toggle`, classe nova**

Em `plugins/kbr-docs/skills/report-creator/assets/docs.css`, confirme que existe, hoje, exatamente isto:

```css
.theme-toggle button svg{width:14px;height:14px}

/* Sidebar nav */
```

Troque por:

```css
.theme-toggle button svg{width:14px;height:14px}

/* Menu toggle — mesmo componente visual do theme-toggle, classe própria */
.menu-toggle{
  display:inline-grid;grid-template-columns:1fr 1fr;
  background:var(--surface-3);border:1px solid var(--border);
  border-radius:var(--r-pill);padding:3px;cursor:pointer;
  font-family:var(--font);
}
.menu-toggle button{
  background:transparent;border:0;cursor:pointer;
  padding:4px 8px;border-radius:var(--r-pill);
  color:var(--meta);font-size:12px;display:inline-flex;align-items:center;gap:4px;
  transition:all .2s ease;
}
:root[data-menu="vertical"]   .menu-toggle button[data-set="vertical"],
:root[data-menu="horizontal"] .menu-toggle button[data-set="horizontal"]{
  background:var(--surface);color:var(--brand);box-shadow:var(--shadow-1);font-weight:600;
}
.menu-toggle button svg{width:14px;height:14px}

/* Sidebar nav */
```

- [ ] **Step 2: Adicionar a lógica em `docs.js` — mesmo padrão do tema**

Em `plugins/kbr-docs/skills/report-creator/assets/docs.js`, confirme que existe, hoje, exatamente isto:

```js
  // Toggle de tema
  document.querySelectorAll('.theme-toggle button').forEach(b => {
    b.addEventListener('click', () => {
      const next = b.getAttribute('data-set');
      root.classList.add('theme-switching');
      root.setAttribute('data-theme', next);
      localStorage.setItem(KEY, next);
      requestAnimationFrame(() => requestAnimationFrame(() => root.classList.remove('theme-switching')));
    });
  });

  // Copy de blocos de código
```

Troque por:

```js
  // Toggle de tema
  document.querySelectorAll('.theme-toggle button').forEach(b => {
    b.addEventListener('click', () => {
      const next = b.getAttribute('data-set');
      root.classList.add('theme-switching');
      root.setAttribute('data-theme', next);
      localStorage.setItem(KEY, next);
      requestAnimationFrame(() => requestAnimationFrame(() => root.classList.remove('theme-switching')));
    });
  });

  // Menu horizontal/vertical — mesmo padrão do tema, sem transição especial
  const KEY_MENU = 'kinto-menu';
  const savedMenu = localStorage.getItem(KEY_MENU) || 'vertical';
  root.setAttribute('data-menu', savedMenu);
  document.querySelectorAll('.menu-toggle button').forEach(b => {
    b.addEventListener('click', () => {
      const next = b.getAttribute('data-set');
      root.setAttribute('data-menu', next);
      localStorage.setItem(KEY_MENU, next);
    });
  });

  // Copy de blocos de código
```

- [ ] **Step 3: Adicionar a marcação do botão em `documento-modelo.html`**

Em `plugins/kbr-docs/skills/report-creator/templates/documento-modelo.html`, confirme que existe, hoje, exatamente isto:

```html
  <div class="hdr-actions">
    <div class="theme-toggle" role="group" aria-label="Tema">
```

Troque por:

```html
  <div class="hdr-actions">
    <div class="menu-toggle" role="group" aria-label="Menu">
      <button data-set="vertical" aria-label="Menu vertical">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="9" y1="3" x2="9" y2="21"/></svg>
      </button>
      <button data-set="horizontal" aria-label="Menu horizontal">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/></svg>
      </button>
    </div>
    <div class="theme-toggle" role="group" aria-label="Tema">
```

- [ ] **Step 4: Rodar `testar.py` e `validar.py --strict`**

```bash
cd "E:\Projetos\Kinto Brasil\src\github\KBR-Claude-Plugins"
python scripts/testar.py
python scripts/validar.py --strict
```

Esperado: os mesmos 257 testes e a validação limpa de sempre.

- [ ] **Step 5: Gerar a pasta de teste e servir por HTTP (roteiro do topo do plano)**

```bash
SCRATCH=$(mktemp -d)
cd "$SCRATCH"
python "/e/Projetos/Kinto Brasil/src/github/KBR-Claude-Plugins/plugins/kbr-docs/skills/report-creator/scripts/descobrir.py" . --escrever
python "/e/Projetos/Kinto Brasil/src/github/KBR-Claude-Plugins/plugins/kbr-docs/skills/report-creator/scripts/aplicar_marca.py" docs/x --raiz=.
cd docs/x
python -m http.server 8799 --bind 127.0.0.1 &
```

- [ ] **Step 6: Clicar no botão de verdade e confirmar o efeito + a persistência**

Com o Playwright MCP, navegue para `http://127.0.0.1:8799/documento-modelo.html`, depois:

```js
async (page) => {
  await page.click('.menu-toggle button[data-set="horizontal"]');
  await page.waitForTimeout(150);
  const antes = await page.evaluate(() => ({
    menu: document.documentElement.getAttribute('data-menu'),
    ls: localStorage.getItem('kinto-menu'),
    sideHeight: document.querySelector('.side').getBoundingClientRect().height,
  }));
  await page.reload();
  await page.waitForTimeout(150);
  const depois = await page.evaluate(() => ({
    menu: document.documentElement.getAttribute('data-menu'),
    sideHeight: document.querySelector('.side').getBoundingClientRect().height,
  }));
  return { antes, depois };
}
```

Esperado: `antes.menu` e `depois.menu` iguais a `"horizontal"`, `antes.ls` igual a `"horizontal"`, e `sideHeight` 48 nos dois — ou seja, o clique mudou o layout E o reload (nova carga de página) manteve a escolha, sem precisar clicar de novo.

- [ ] **Step 7: Clicar de volta em "vertical" e confirmar que volta ao layout de hoje**

```js
async (page) => {
  await page.click('.menu-toggle button[data-set="vertical"]');
  await page.waitForTimeout(150);
  return await page.evaluate(() => ({
    menu: document.documentElement.getAttribute('data-menu'),
    sideWidth: document.querySelector('.side').getBoundingClientRect().width,
    tocDisplay: getComputedStyle(document.querySelector('.toc')).display,
  }));
}
```

Esperado: `menu` `"vertical"`, `sideWidth` de volta a ~224 (a largura fixa da sidebar, não mais 100% da página), `tocDisplay` diferente de `"none"` (o TOC volta a aparecer).

- [ ] **Step 8: Screenshot dos dois estados, pra registro visual**

Tire um `browser_take_screenshot` (`fullPage: true`) com o menu em `"horizontal"` e outro em `"vertical"`, confirmando visualmente o botão novo ao lado do alternador de tema, com o ícone certo destacado em cada estado.

- [ ] **Step 9: Encerrar o servidor**

```bash
kill %1
```

- [ ] **Step 10: Commit**

```bash
cd "E:\Projetos\Kinto Brasil\src\github\KBR-Claude-Plugins"
git add plugins/kbr-docs/skills/report-creator/assets/docs.css plugins/kbr-docs/skills/report-creator/assets/docs.js plugins/kbr-docs/skills/report-creator/templates/documento-modelo.html
git commit -m "feat(kbr-docs): botao de menu horizontal/vertical (documento-modelo.html)

Pilula de 2 icones ao lado do alternador de tema, mesmo componente
visual (.menu-toggle). docs.js grava data-menu no <html> e persiste em
localStorage (chave kinto-menu), mesmo padrao do data-theme/kinto-theme.
Ainda so no documento-modelo.html -- front-matter.html e index.html
ganham o mesmo botao na task seguinte.

Verificado clicando de verdade no navegador: liga horizontal (sidebar
vira faixa de 48px, TOC some), sobrevive a um reload da pagina, e volta
pra vertical (sidebar 224px, TOC de volta) ao clicar no outro botao."
```

---

### Task 3: Propagar o botão para `front-matter.html` e `index.html`

Mesma marcação exata da Task 3 (Step 3 da Task 2) — mecânica, sem lógica nova.

**Files:**
- Modify: `plugins/kbr-docs/skills/report-creator/templates/front-matter.html`
- Modify: `plugins/kbr-docs/skills/report-creator/templates/index.html`

**Interfaces:**
- Consumes: `.menu-toggle` (CSS da Task 2) e a lógica de `docs.js` (Task 2) — nenhuma das duas muda aqui.

- [ ] **Step 1: `front-matter.html`**

Confirme que existe, hoje, exatamente isto:

```html
  <div class="hdr-actions">
    <div class="theme-toggle" role="group" aria-label="Tema">
```

Troque por:

```html
  <div class="hdr-actions">
    <div class="menu-toggle" role="group" aria-label="Menu">
      <button data-set="vertical" aria-label="Menu vertical">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="9" y1="3" x2="9" y2="21"/></svg>
      </button>
      <button data-set="horizontal" aria-label="Menu horizontal">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/></svg>
      </button>
    </div>
    <div class="theme-toggle" role="group" aria-label="Tema">
```

- [ ] **Step 2: `index.html`**

Confirme que existe, hoje, exatamente isto:

```html
  <div class="hdr-actions">
    <div class="theme-toggle" role="group" aria-label="Tema">
```

Troque por:

```html
  <div class="hdr-actions">
    <div class="menu-toggle" role="group" aria-label="Menu">
      <button data-set="vertical" aria-label="Menu vertical">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="9" y1="3" x2="9" y2="21"/></svg>
      </button>
      <button data-set="horizontal" aria-label="Menu horizontal">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/></svg>
      </button>
    </div>
    <div class="theme-toggle" role="group" aria-label="Tema">
```

- [ ] **Step 3: Rodar `testar.py` e `validar.py --strict`**

```bash
cd "E:\Projetos\Kinto Brasil\src\github\KBR-Claude-Plugins"
python scripts/testar.py
python scripts/validar.py --strict
```

- [ ] **Step 4: Gerar a pasta de teste (roteiro do topo do plano) e verificar as duas páginas**

```bash
SCRATCH=$(mktemp -d)
cd "$SCRATCH"
python "/e/Projetos/Kinto Brasil/src/github/KBR-Claude-Plugins/plugins/kbr-docs/skills/report-creator/scripts/descobrir.py" . --escrever
python "/e/Projetos/Kinto Brasil/src/github/KBR-Claude-Plugins/plugins/kbr-docs/skills/report-creator/scripts/aplicar_marca.py" docs/x --raiz=.
cd docs/x
python -m http.server 8799 --bind 127.0.0.1 &
```

Com o Playwright: navegue para `http://127.0.0.1:8799/front-matter.html`, clique em `.menu-toggle button[data-set="horizontal"]`, confirme (mesma asserção do Step 6 da Task 2) que `.side` vira a faixa de 48px. Repita para `index.html`.

- [ ] **Step 5: Confirmar que a escolha atravessa páginas do MESMO conjunto**

Ainda no navegador Playwright (mesma aba, não recarregue do zero): depois de ligar `"horizontal"` em `front-matter.html`, navegue para `documento-modelo.html` (`browser_navigate`) e confira:

```js
async (page) => {
  return await page.evaluate(() => ({
    menu: document.documentElement.getAttribute('data-menu'),
    sideHeight: document.querySelector('.side').getBoundingClientRect().height,
  }));
}
```

Esperado: `menu` `"horizontal"` e `sideHeight` 48 — a escolha feita numa página vale nas outras do mesmo conjunto, sem precisar clicar de novo (é o `localStorage`, compartilhado pela mesma origem `http://127.0.0.1:8799`).

- [ ] **Step 6: Encerrar o servidor**

```bash
kill %1
```

- [ ] **Step 7: Commit**

```bash
cd "E:\Projetos\Kinto Brasil\src\github\KBR-Claude-Plugins"
git add plugins/kbr-docs/skills/report-creator/templates/front-matter.html plugins/kbr-docs/skills/report-creator/templates/index.html
git commit -m "feat(kbr-docs): propagar o botao de menu horizontal/vertical

Mesma marcacao da task anterior, agora em front-matter.html e
index.html. Verificado que a escolha feita numa pagina vale nas outras
do mesmo conjunto (mesmo localStorage, mesma origem)."
```

---

### Task 4: Verificação final — as 3 páginas, os 2 temas, os 2 modos de menu

Sem código novo esperado — é a checagem de regressão completa antes de entregar. Se algo quebrar aqui, corrija e comite antes de encerrar a task.

**Files:** nenhum (verificação) — ou os mesmos da Task 1-3, se algum ajuste for necessário.

- [ ] **Step 1: `testar.py` + `validar.py --strict`, uma última vez**

```bash
cd "E:\Projetos\Kinto Brasil\src\github\KBR-Claude-Plugins"
python scripts/testar.py
python scripts/validar.py --strict
```

- [ ] **Step 2: Gerar a pasta de teste final (roteiro do topo do plano)**

```bash
SCRATCH=$(mktemp -d)
cd "$SCRATCH"
python "/e/Projetos/Kinto Brasil/src/github/KBR-Claude-Plugins/plugins/kbr-docs/skills/report-creator/scripts/descobrir.py" . --escrever
python "/e/Projetos/Kinto Brasil/src/github/KBR-Claude-Plugins/plugins/kbr-docs/skills/report-creator/scripts/aplicar_marca.py" docs/x --raiz=.
cd docs/x
python -m http.server 8799 --bind 127.0.0.1 &
```

- [ ] **Step 3: Matriz de verificação visual (screenshot em cada célula)**

Para cada uma das 3 páginas (`index.html`, `front-matter.html`, `documento-modelo.html`):

1. Navegue até a página.
2. Screenshot no modo vertical + tema claro (estado inicial, nada clicado) — confirme que é **pixel-a-pixel igual** ao que já existia antes desta fatia (cabeçalho 56px, sidebar 224px, TOC visível, rodapé 56px).
3. Clique no botão de tema escuro — screenshot vertical + escuro.
4. Clique no botão de menu horizontal — screenshot horizontal + escuro.
5. Clique no botão de tema claro (mantendo horizontal) — screenshot horizontal + claro.

Confirme em cada screenshot: nos dois temas, a faixa horizontal tem o mesmo contraste do cabeçalho/rodapé (nada de texto ilegível), o link da página atual continua destacado (`class="active"`), e a rolagem horizontal da faixa (se a janela for estreita) não introduz uma barra de rolagem vertical indesejada.

- [ ] **Step 3b: Janela estreita — confirmar que a faixa horizontal rola por dentro, sem quebrar a página**

Ainda em `documento-modelo.html`, com o menu em `"horizontal"`:

```js
async (page) => {
  await page.setViewportSize({ width: 600, height: 800 });
  await page.waitForTimeout(150);
  return await page.evaluate(() => {
    const side = document.querySelector('.side');
    return {
      sideOverflowX: getComputedStyle(side).overflowX,
      sideScrollWidth: side.scrollWidth,
      sideClientWidth: side.clientWidth,
      bodyScrollWidth: document.body.scrollWidth,
      viewportWidth: window.innerWidth,
    };
  });
}
```

Esperado: `sideOverflowX` `"auto"`; `sideScrollWidth` pode ser MAIOR que `sideClientWidth` (os links não cabem e a faixa rola por dentro); `bodyScrollWidth` igual a `viewportWidth` (a página em si não ganhou barra de rolagem horizontal por causa disso). Volte o viewport ao normal (`await page.setViewportSize({ width: 1280, height: 800 })`) antes do próximo step.

- [ ] **Step 4: Conferir que o `--hdr-h` do cabeçalho e do rodapé não mudou**

```js
async (page) => {
  return await page.evaluate(() => ({
    hdr: document.querySelector('.hdr').getBoundingClientRect().height,
    ftr: document.querySelector('.ds-footer').getBoundingClientRect().height,
  }));
}
```

Esperado: os dois em 56 — a fatia do rodapé/cabeçalho (sessão anterior) não regrediu.

- [ ] **Step 5: Encerrar o servidor e apagar a pasta de teste**

```bash
kill %1
rm -rf "$SCRATCH"
```

- [ ] **Step 6: Se algo precisou de correção, commit; senão, task concluída sem commit novo**

```bash
cd "E:\Projetos\Kinto Brasil\src\github\KBR-Claude-Plugins"
git status --short
```

Se vazio, não há nada a commitar — a fatia está pronta, aguardando o Fábio decidir sobre push + tag `kbr-docs--v0.1.1` (mesma pendência das fatias anteriores).
