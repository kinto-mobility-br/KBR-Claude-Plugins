---
name: report-creator
description: Gera documentação em HTML com o design system oficial da KINTO — plano, spec, diagnóstico, relatório, manual, avaliação técnica ou conjunto de documentos. Na primeira vez num projeto, descobre a marca (logo, cor, nome) e cria o .docs-brand.yml sozinho; nas vezes seguintes, gera direto a partir dele. Use quando o usuário pedir "documento", "documentação", "relatório em HTML", "gerar relatório", "inicializar a documentação", "configurar a marca do projeto", ou invocar /kbr-docs:report-creator.
---

# Gerador de relatórios — documentação HTML da KINTO

Você gera **documentação em HTML**, sempre a partir do template oficial. **Nunca invente um
layout novo** — se o pedido é um documento, comece por aqui.

## Fluxo

1. Confira se já existe config de marca — em qualquer um dos três níveis (veja
   "Os três níveis" abaixo). O jeito mais rápido é rodar o resolver:
   `python "${CLAUDE_PLUGIN_ROOT}/skills/report-creator/scripts/resolver_marca.py" .`
   — ele mostra o efetivo (projeto mesclado com o nível de usuário) sem gravar nada.
2. **Nada configurado (nem projeto, nem usuário):** descubra a marca do projeto
   primeiro (seção 1 abaixo), depois siga para a geração.
3. **Já existe algo** (mesmo que só no nível de usuário): vá direto para a
   geração (seção 2) — e, ao perguntar o que falta preencher, **não pergunte
   de novo** o que o resolver já mostrou como preenchido pelo nível de usuário.

### 1. Descobrir a marca (só na primeira vez por projeto)

**Descobrir — não grava nada:**
```bash
python "${CLAUDE_PLUGIN_ROOT}/skills/report-creator/scripts/descobrir.py" .
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
python "${CLAUDE_PLUGIN_ROOT}/skills/report-creator/scripts/descobrir.py" . --escrever
```
Não sobrescreve um `.docs-brand.yml` existente. Depois de gravado, a pessoa pode editar à mão
o que faltou — é um YAML (um subconjunto dele, veja "Detalhes que costumam morder"), e os
comentários dizem para que serve cada campo.

### 2. Gerar o documento

```bash
python "${CLAUDE_PLUGIN_ROOT}/skills/report-creator/scripts/aplicar_marca.py" docs/<assunto> --raiz=.
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
  aninhados até 3 níveis, valores entre aspas duplas ou booleano (`true`/`yes`/`on` e
  `false`/`no`/`off`, sem diferenciar maiúsculas), comentários com `#`. Não suporta lista,
  âncora, bloco multilinha nem aspas simples — se o arquivo tiver algo assim (editado à mão
  fora do padrão que a skill gera), a geração pode ler o valor errado.

## Regras do padrão (não negociáveis)

- **Header:** logo (clicável, leva ao índice) + alternador de menu (vertical/horizontal) +
  alternador de tema. Sem "Exportar", sem "Compartilhar", sem busca.
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
  menu DIREITO = âncoras da página atual (TOC). Nunca duplicar a mesma navegação nos dois. O
  alternador de menu no cabeçalho troca o menu esquerdo entre sidebar vertical (padrão) e uma
  faixa horizontal colada no cabeçalho — o TOC continua igual nos dois modos.
- **Layout:** header fixo; sidebar e TOC `sticky`; quem rola é o shell. O `<footer>` fica
  **dentro** do `<main>` (rola junto) e sangra até as bordas da janela.
- **Marca:** nunca escreva cor ou caminho de logo direto no HTML. Tudo vem do
  `.docs-brand.yml` → `assets/brand.css`. Mudou a marca? Edite o YAML e gere de novo.
- **Exemplos de código:** sempre nas três linguagens (Python, Java, C#) pelo componente
  `.codetabs`, quando o assunto comportar.
- **Componentes: COPIE a marcação, não escreva de cabeça.** Abra
  `${CLAUDE_PLUGIN_ROOT}/skills/report-creator/referencia/componentes.html`, copie o bloco do
  componente e troque só o texto. Tem
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
- O tema é escrito em `data-theme` no `<html>`; `docs.js` lembra a escolha em `localStorage`
  (chave `kinto-theme`). O modo do menu segue o mesmo padrão: `data-menu`
  (`vertical`/`horizontal`), chave `kinto-menu`.
- Logo de marca costuma ser um PNG grande. Acima de 500 KB o script avisa — vale gerar uma
  versão reduzida só para a documentação. A foto do autor tem o mesmo aviso a partir de
  300 KB: ela aparece em 32px, recortada no centro.
- **A folha impressa é sempre clara**, mesmo com o leitor no tema escuro: o `@media print`
  redefine os tokens na raiz, e a marca clara é repetida ali porque `brand.css` é carregado
  depois do `docs.css`. Header, sidebar, TOC e o botão de copiar somem; o bloco de código
  continua escuro de propósito.
- **A detecção automática de cor/luminância de logo em PNG precisa do Pillow — que é
  opcional.** Sem Pillow instalado, esses campos do YAML saem como `# SUGESTÃO — confira` em
  vez de preenchidos sozinhos. Logo em `.svg` não depende disso (a cor é lida do próprio
  código do arquivo). Nunca trate a ausência de Pillow como erro — é o comportamento normal.
- Ao publicar um conjunto novo, abra pelo menos uma página no navegador e confira: alternador
  de tema, alternador de menu (vertical e horizontal), links da navegação nos dois modos,
  âncoras do TOC nos dois modos, e a impressão (Ctrl+P).
