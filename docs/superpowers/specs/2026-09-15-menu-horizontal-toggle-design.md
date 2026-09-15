# Spec de design — alternador de menu horizontal/vertical no design system do `kbr-docs`

**Data:** 2026-09-15
**Status:** aprovado (brainstorming com o Fábio nesta sessão)
**Repositório:** `kinto-mobility-br/KBR-Claude-Plugins` (privado)

---

## 1. Objetivo

Depois de reduzir a escala do design system e refazer o rodapé numa faixa só (sessão de
2026-09-15), o Fábio pediu duas coisas relacionadas, olhando o relatório de teste no
navegador:

1. o menu (a navegação lateral esquerda, hoje uma sidebar vertical fixa) deveria poder
   ocupar 100% da largura da página;
2. um botão, no mesmo estilo do alternador de tema, para a pessoa que está lendo escolher
   entre menu vertical (o de hoje) e menu horizontal (o novo).

### Critérios de sucesso

1. Um botão novo, pílula de 2 ícones igual ao alternador de tema, ao lado dele no cabeçalho,
   alterna entre os dois modos.
2. Modo horizontal: os mesmos links de navegação (Front Matter / Índice / Documento / …)
   saem da sidebar e formam uma faixa 100% da largura, colada embaixo do cabeçalho, sempre
   visível ao rolar (sticky). **O TOC da direita permanece nos dois modos** (revisto em
   2026-09-15, depois do Fábio ver o resultado — decisão original era esconder o TOC no modo
   horizontal, revertida) — conteúdo e TOC formam duas colunas na linha de baixo, com a faixa
   do menu ocupando as duas por cima. O texto corrido ganha uma margem de leitura razoável
   (não fica esparramado de ponta a ponta) — tabelas, código e callouts continuam podendo usar
   a largura toda, como já fazem hoje.
3. Modo vertical: exatamente o comportamento de hoje, sem nenhuma mudança visual.
4. A escolha persiste no navegador de quem lê (mesmo mecanismo do tema — `localStorage`),
   valendo para as páginas do mesmo conjunto de documentos. Sem escolha salva, abre no modo
   vertical (o padrão de hoje não muda por default).
5. Nenhum teste Python quebra (`testar.py` continua 257/257) e `validar.py --strict` continua
   limpo — é mudança de CSS/JS/HTML, os scripts Python não tocam nisso.

### Decisões já tomadas (brainstorming de 2026-09-15)

| Decisão | Escolha | Por quê |
|---|---|---|
| Formato do modo horizontal | Faixa full-width colada embaixo do cabeçalho | Opção escolhida entre essa e "abas dentro do próprio cabeçalho" — mantém o cabeçalho intocado, mais simples de isolar em CSS |
| TOC no modo horizontal | Permanece (revisto 2026-09-15, depois do Fábio ver o resultado) | Decisão original era esconder — o Fábio pediu pra manter nos dois menus depois de ver o formato pronto no navegador |
| Margem de leitura no modo horizontal | Sim, via token `--measure` | Pedido explícito ("respeitando uma margem razoável") — reaproveita o token que os componentes de texto corrido já leem, sem tocar em tabela/código/callout |
| Comportamento ao rolar | Sticky, colado no cabeçalho | Opção escolhida entre essa e "rola junto com o conteúdo" |
| Estado inicial (sem escolha salva) | Vertical | Não muda o padrão de quem já usa o plugin hoje |
| Persistência | `localStorage`, mesmo padrão do tema | Mesma expectativa de UX que o alternador de tema já criou |
| Estilo do botão | Pílula de 2 ícones, igual ao `.theme-toggle` | Opção escolhida entre essa e "botão único que troca de ícone" — mantém o cabeçalho visualmente consistente |
| Duplicar a lista de links em dois lugares (sidebar E barra horizontal) | Não — uma marcação só, transformada por CSS | Seguindo a regra que o próprio `SKILL.md` já registra ("nunca duplicar a mesma navegação nos dois") |

---

## 2. O que muda

Local: `plugins/kbr-docs/skills/report-creator/{assets/docs.css, assets/docs.js,
templates/*.html}`.

### 2.1 Atributo de estado — mesmo padrão do tema

`docs.js` já faz isso para tema (`data-theme` no `<html>`, chave `kinto-theme` no
`localStorage`). O menu ganha o par exato: `data-menu` no `<html>` (`vertical` — padrão —
ou `horizontal`), chave `kinto-menu`.

```js
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
```

Sem a lógica de `theme-switching` (aquela classe que suspende transições durante a troca de
tema) — a troca de menu já é instantânea o bastante sem precisar disso; se algum flash
aparecer na implementação, essa é a primeira coisa a copiar.

### 2.2 Botão novo no cabeçalho (`.hdr-actions`, ao lado do `.theme-toggle`)

Mesma marcação/CSS do `.theme-toggle`, com uma classe própria (`.menu-toggle`) e dois ícones
SVG novos (sidebar vertical vs. barra horizontal — inline, no mesmo estilo `stroke=
currentColor` dos outros ícones do design system). Entra nos três templates
(`documento-modelo.html`, `front-matter.html`, `index.html`), sempre à esquerda do alternador
de tema.

### 2.3 CSS — `.shell` com dois layouts, TOC preservado

Hoje: `.shell{grid-template-columns:var(--side-w) minmax(0,1fr) var(--toc-w)}`, três colunas
lado a lado (`side | content | toc`).

Modo horizontal (`:root[data-menu="horizontal"] .shell`): duas colunas (`content | toc`,
`grid-template-columns:minmax(0,1fr) var(--toc-w)` — o TOC mantém a largura de sempre), com
`.side` em `grid-column:1 / -1` pra ocupar as duas na linha de cima (a faixa do menu). Só
`--side-w` zera (o rodapé usa essa variável pra calcular a sangria à esquerda — ver 2.5);
`--toc-w` continua com o valor normal, porque o TOC não sai do layout, só desce pra debaixo da
faixa do menu junto com o conteúdo.

### 2.4 CSS — `.side` como barra horizontal

Sob `:root[data-menu="horizontal"]`, `.side`:
- vira `position:sticky;top:0` — o contêiner de rolagem do sticky é o `.shell` (que já começa
  exatamente onde o cabeçalho termina), não o viewport; `top:0` cola na borda superior do
  próprio `.shell`, mesma regra que o modo vertical já usa hoje. `top:var(--hdr-h)` contaria a
  altura do cabeçalho duas vezes e abriria um vão permanente entre header e faixa — achado na
  revisão da Task 1, corrigido antes da Task 2;
- o `<nav>`/`<ul>` internos viram `display:flex;flex-direction:row`, com os `<li><a>` como
  pills horizontais (`overflow-x:auto` na linha, pra não quebrar em telas estreitas — mesmo
  padrão de "não wrap, rola" que outras faixas do design system já usam, ex. `.codetabs-bar`);
- o rótulo `<h6>Documentação · Projeto</h6>` some (`display:none`) — não cabe, e as próprias
  pills já dizem o que são.

### 2.5 CSS — margem de leitura e rodapé

`--measure` (hoje `none`, token compartilhado que `.doc p`, `.doc-lead`, `.doc ul/ol` e
`.callout` já leem) ganha um valor sob `:root[data-menu="horizontal"]` — um `max-width` fixo,
tipo 760px, escolhido pra ficar confortável de ler sem sidebar/TOC descontando espaço. Tabela,
código e callout continuam com `max-width:none` onde já está assim hoje — não mudam.

O rodapé (`.content > .ds-footer`) já bleeda por baixo da sidebar/TOC via margem negativa
calculada a partir de `--side-w`/`--toc-w`. Como só `--side-w` zera no modo horizontal (2.3;
`--toc-w` continua normal, porque o TOC fica), a sangria à esquerda passa a ir até a borda da
página, e a sangria à direita continua igual à do modo vertical (por baixo do TOC, que
permanece do mesmo tamanho) — sem ajuste extra na fórmula.

### 2.6 O que NÃO muda

- Marcação da lista de links (`<nav><ul><li><a>`) — a mesma, só reestilizada por CSS.
- `.hdr` e `.ds-footer` — intocados (o botão novo entra dentro do `.hdr-actions` já
  existente).
- Modo vertical — nenhuma regra de hoje muda; tudo entra sob o seletor
  `:root[data-menu="horizontal"]`.
- Nenhum script Python (`descobrir.py`, `aplicar_marca.py`) muda — placeholders
  (`{{PROJETO}}`, `{{AVATAR}}` etc.) continuam os mesmos, só a marcação estática ao redor deles
  ganha o botão novo.

---

## 3. Responsivo

No breakpoint que já existe (`max-width:820px`, onde a sidebar vertical já vira estática e o
TOC já desaparece), o modo horizontal continua funcionando pela mesma regra de
`overflow-x:auto` da barra de pills (2.4) — não precisa de um breakpoint dedicado.

---

## 4. Testes / verificação

Sem teste Python novo (CSS/JS/HTML estático, fora do que `testar.py` cobre). Verificação:

- `testar.py` (257 testes) e `validar.py --strict` continuam limpos — nada em Python muda.
- Verificação visual real no navegador (Playwright, como nas mudanças anteriores desta
  sessão): os dois modos, os dois temas (claro/escuro), nas 3 páginas geradas, confirmando
  — barra horizontal sticky ocupando conteúdo+TOC, TOC presente e com a largura normal nos
  dois modos, margem de leitura aplicada, rodapé sangrando até a borda, e o modo vertical
  **idêntico** ao que já estava antes desta mudança.

---

## 5. Fora de escopo

- Qualquer terceiro modo de menu (ex. colapsável, "mini" sidebar apenas com ícones).
- Persistir a escolha do lado do autor (`.docs-brand.yml`) — é preferência de quem LÊ, não do
  projeto.
- Mudar o comportamento do TOC além de escondê-lo no modo horizontal.
- Tocar na skill pessoal `~/.claude/skills/docs-html` (fora do plugin, sem sincronização
  automática — risco já aceito e registrado na spec anterior do `kbr-docs`).
