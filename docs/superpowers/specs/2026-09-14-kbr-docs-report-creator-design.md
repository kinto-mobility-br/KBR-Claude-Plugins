# Spec de design — plugin `kbr-docs`, skill `report-creator`

**Data:** 2026-09-14
**Status:** rascunho para revisão
**Repositório:** `kinto-mobility-br/KBR-Claude-Plugins` (privado)

---

## 1. Objetivo

Trazer a geração de documentação em HTML — hoje duas skills pessoais do Fábio, em
`~/.claude/skills/docs-html` e `~/.claude/skills/docs-init` — para dentro do marketplace
`kinto-brasil`, como um plugin novo (`kbr-docs`) instalável por qualquer técnico da KINTO,
com o mesmo padrão de qualidade (testes, `${CLAUDE_PLUGIN_ROOT}`, `claude plugin validate
--strict`) já estabelecido em `kbr-core`/`kbr-servicedesk`.

As duas skills existentes — descoberta de marca e geração do documento — viram **uma única
skill**, `report-creator`, que decide sozinha se precisa descobrir a marca primeiro ou se já
pode gerar direto.

### Critérios de sucesso

1. `/kbr-docs:report-creator`, num projeto sem `.docs-brand.yml`, descobre a marca (logo, cor,
   nome), confirma com a pessoa o que não deu para descobrir sozinho, grava o arquivo, e **na
   mesma invocação** já gera o conjunto de documentos — sem precisar de um segundo comando.
2. Num projeto que já tem `.docs-brand.yml`, pula direto para a geração.
3. Todo o comportamento hoje coberto pelas duas skills originais continua idêntico — é
   migração, não redesenho. Nenhuma regra de negócio muda.
4. `python scripts/testar.py` cobre os dois scripts (`descobrir.py`, `aplicar_marca.py`), que
   hoje não têm teste nenhum — mesmo padrão de rigor do resto do marketplace.
5. Nenhuma dependência externa obrigatória — `pip install` continua proibido pela regra do
   repositório. O uso opcional de Pillow (ver seção 3) precisa continuar opcional.

### Decisões já tomadas (brainstorming de 2026-09-14)

| Decisão | Escolha | Por quê |
|---|---|---|
| Formato desta fatia | Só HTML | PDF e apresentações (PPTX) ficam fora — `presentation-creator` é uma fatia futura própria, com perguntas de design que ainda não foram exploradas (biblioteca, layout, tema) |
| Skills globais originais | Mantidas, intocadas | `~/.claude/skills/docs-html`/`docs-init` continuam servindo os outros projetos do Fábio fora da KINTO. Risco aceito: as duas cópias (skill global e plugin) podem divergir com o tempo — não há sincronização automática entre elas |
| `kb-doc-creator` | Fora de escopo | É outra coisa (docs `.md` padronizados tipo ADR/runbook, RAG-ready) — não faz parte desta migração |
| Estrutura da skill | Uma skill só (`report-creator`), não duas | Pedido explícito do Fábio. As duas skills de hoje já são sequenciais (`docs-html` manda parar e rodar `docs-init` primeiro se faltar o YAML) — consolidar é só não parar, rodar a descoberta ali mesmo |
| Cobertura de teste | Sim, nova, do zero | Os dois scripts (284 e 375 linhas) nunca tiveram teste. Fábio pediu o mesmo padrão do `kbr-servicedesk` — TDD, mocks/fixtures, sem chamada de rede |
| Nome do plugin | `kbr-docs` | Já combinado antes desta sessão (memória do projeto) e confirmado nesta conversa pelo próprio Fábio (`kbr-docs:report-creator`) |
| Dependência de `kbr-core` | Nenhuma | `report-creator` não lida com segredo nenhum |

---

## 2. O que existe hoje (fonte da migração)

### 2.1 `~/.claude/skills/docs-init/`

```
SKILL.md
scripts/descobrir.py     (375 linhas)
```

`descobrir.py`:
- varre o repositório procurando arquivo de imagem cujo nome/caminho fale em
  logo/marca/brand/símbolo/wordmark, ignorando `node_modules`, `dist`, `obj`, `.venv` e afins;
- decide qual logo serve a qual fundo (claro/escuro) por nome, e no empate por **luminância
  média** dos pixels opacos;
- extrai a **cor de marca**: de SVG por regex (hex mais repetido, sem dependência nenhuma); de
  PNG/raster, pela cor mais frequente entre os pixels opacos e não-neutros — **só se o Pillow
  estiver instalado** (`from PIL import Image` dentro de um `try/except ImportError`, os dois
  pontos do arquivo onde isso acontece já retornam `None` sem Pillow, e o resto do script
  trata `None` como "não descoberto", nunca como erro);
- descobre o nome do projeto via `package.json`, `.csproj`, título do `CLAUDE.md`, ou o nome da
  pasta;
- em modo leitura (sem `--escrever`), só mostra o que achou; em `--escrever`, grava
  `.docs-brand.yml` na raiz — **nunca sobrescreve** um já existente;
- todo valor que o script não conseguiu confirmar entra no YAML comentado como
  `# SUGESTÃO — confira`.

Único uso de `subprocess`: chamar `git` (não é dependência nova — já é exigido em todo o
resto do fluxo). Sem outro import fora da biblioteca padrão.

### 2.2 `~/.claude/skills/docs-html/`

```
SKILL.md
assets/{docs.css, docs.js, logo-claro.svg, logo-escuro.svg}
templates/{documento-modelo.html, front-matter.html, index.html}
referencia/componentes.html
scripts/aplicar_marca.py     (284 linhas)
```

`aplicar_marca.py`:
- exige `.docs-brand.yml` na raiz (hoje: se não existir, para e manda rodar `docs-init`
  primeiro — na skill consolidada, isso deixa de ser um erro e vira o gatilho para rodar a
  descoberta inline, ver seção 3);
- copia `assets/` (design system completo — CSS, JS, os dois SVGs placeholder) para o destino;
- instala os logos do projeto por cima dos placeholders (mantendo a extensão original) e a
  foto do autor no selo do rodapé — sem foto, ficam as iniciais;
- escreve `assets/brand.css` com os tokens de marca, carregado **depois** de `docs.css` (uma
  atualização da skill nunca apaga a marca de ninguém);
- gera os HTML a partir dos templates, substituindo `{{PROJETO}}`, `{{RODAPE}}`, `{{AUTOR}}` e
  companhia;
- **nunca sobrescreve** arquivo que já existe;
- avisa (não bloqueia) quando o logo passa de 500 KB ou a foto do autor passa de 300 KB;
- com `tipografia.fontes_externas: false` no YAML, remove os links do Google Fonts (Inter,
  JetBrains Mono) — para documento que precisa circular sem internet.

Único uso de `subprocess`: `git rev-parse --show-toplevel` (mesmo caso do item anterior).

### 2.3 Fatos que tornam a migração mecânica, não um redesenho

- **Nenhum caminho absoluto embutido na lógica dos dois scripts.** Os dois já se localizam
  via `Path(__file__).resolve().parent...` — funcionam de qualquer pasta em que forem
  instalados, plugin ou skill global, sem mudança de código.
- Os únicos lugares com `~/.claude/skills/<nome>/scripts/...` hardcoded são os **exemplos de
  comando** dentro dos dois `SKILL.md`, e um comentário-exemplo dentro de `descobrir.py`
  (linha ~258, um docstring/comentário que cita o comando do `aplicar_marca.py` como próximo
  passo — não é código executado, só precisa de texto atualizado).
- Nenhum import fora da biblioteca padrão é **obrigatório**. Pillow é o único opcional, e já
  degrada de forma limpa.

---

## 3. A skill consolidada `report-creator`

**Local:** `plugins/kbr-docs/skills/report-creator/`

```
SKILL.md
scripts/
  descobrir.py          (movido de docs-init, sem mudança de lógica)
  aplicar_marca.py       (movido de docs-html, sem mudança de lógica)
assets/{docs.css, docs.js, logo-claro.svg, logo-escuro.svg}
templates/{documento-modelo.html, front-matter.html, index.html}
referencia/componentes.html
```

### Fluxo (novo — é a única coisa realmente nova desta fatia)

1. Ao ser invocada, checa se `.docs-brand.yml` existe na raiz do projeto (mesma checagem que
   `aplicar_marca.py` já faz sozinho ao rodar sem o arquivo).
2. **Não existe:**
   a. roda `descobrir.py <raiz>` (sem `--escrever` — só leitura);
   b. mostra o que foi encontrado (logo, cor, nome) e pergunta à pessoa o que o script não tem
      como saber (subtítulo, área, classificação, texto de rodapé, autor, revisor) — mesmo
      texto/ordem que a skill `docs-init` já usa hoje;
   c. roda `descobrir.py <raiz> --escrever` para gravar;
   d. segue para o passo 3.
3. **Já existe (ou acabou de ser criado no passo 2):** roda `aplicar_marca.py <destino>
   --raiz=<raiz>` — mesmo comando que `docs-html` já documenta hoje.
4. Reporta o resultado (de onde veio cada logo, avisos de arquivo grande, o que caiu em
   placeholder) — mesmo relatório que `aplicar_marca.py` já imprime.

Os dois scripts continuam com assinaturas de linha de comando **diferentes entre si**
(`descobrir.py` recebe a raiz como posicional e uma flag `--escrever`; `aplicar_marca.py`
recebe o destino como posicional e a raiz como `--raiz=`) — a consolidação é só a skill que os
orquestra em sequência; os dois scripts não são unificados nem ganham uma CLI comum. Fazer
isso seria redesenho, fora do que foi pedido.

### `SKILL.md` — frontmatter

`name: report-creator`. `description` precisa cobrir os dois gatilhos que hoje disparam as
skills separadas (criar documento HTML, inicializar a marca do projeto) e, como sempre,
nenhum `: ` (dois-pontos + espaço) dentro do valor sem aspas — travessão no lugar de
dois-pontos onde precisar de pausa.

---

## 4. `.claude-plugin/plugin.json`

```json
{
  "name": "kbr-docs",
  "displayName": "KINTO — Documentação",
  "version": "0.1.0",
  "description": "Gera documentação em HTML com o design system oficial da KINTO — descobre a marca do projeto na primeira vez e gera os documentos a partir daí.",
  "author": { "name": "KINTO Brasil — TI" },
  "keywords": ["documentacao", "html", "relatorio", "design-system", "kinto"]
}
```

Sem `dependencies` — não depende de `kbr-core`. Entrada nova em
`.claude-plugin/marketplace.json` (raiz do repositório), mesmo padrão das duas entradas já
existentes.

---

## 5. Testes

Novo — os dois scripts nunca tiveram teste. Mesmo padrão de rigor do resto do marketplace:
sem chamada de rede (nenhum dos dois scripts fala com rede nenhuma, então não precisa de
duplo/mocks de rede como no `kbr-servicedesk` — só arquivos e pastas temporárias),
TDD, casos de borda tratados como parte do design, não como ocorrência.

**`descobrir.py`:**
- acha logo por nome/caminho; ignora `node_modules`/`dist`/`obj`/`.venv`;
- decide claro/escuro por nome, e por luminância no empate;
- extrai cor de SVG (regex, sempre disponível);
- com Pillow ausente (simular removendo do `sys.modules`/interceptando o import), a extração
  de cor/luminância de PNG devolve `None` sem levantar exceção, e o resto do fluxo trata isso
  como "não descoberto", não como erro;
- nome do projeto: `package.json`, `.csproj`, título do `CLAUDE.md`, pasta — nessa ordem de
  prioridade (confirmar a ordem real lendo o código na hora do plano);
- modo leitura não grava nada; `--escrever` grava; rodar `--escrever` de novo com o arquivo já
  existente não sobrescreve;
- valor não descoberto entra comentado como `# SUGESTÃO — confira`.

**`aplicar_marca.py`:**
- sem `.docs-brand.yml`: falha limpa (a mensagem exata que a skill consolidada não deve mais
  precisar mostrar ao usuário, já que passa a rodar a descoberta antes — mas o script em si
  continua tendo esse comportamento, testável isoladamente);
- copia `assets/` para o destino;
- instala logo do projeto por cima do placeholder, mantendo extensão; sem logo, mantém
  placeholder;
- gera `assets/brand.css` com os tokens do YAML;
- nunca sobrescreve arquivo que já existe (rodar duas vezes não apaga edição manual);
- avisa (sem falhar) quando logo/avatar passam do tamanho limite;
- `fontes_externas: false` remove os links do Google Fonts dos HTML gerados.

---

## 6. Fora de escopo desta fatia

- `presentation-creator` (PPTX/apresentações) — fatia futura própria, com brainstorming
  próprio (formato de saída, biblioteca, tema, layout).
- PDF.
- `kb-doc-creator` (docs `.md` padronizados) — continua onde está, sem mudança.
- Qualquer mudança de comportamento nos dois scripts além da relocação e dos ajustes de
  caminho (`${CLAUDE_PLUGIN_ROOT}`) necessários para funcionar como plugin.
- Sincronização automática entre a cópia global (`~/.claude/skills/`) e a cópia do plugin —
  risco aceito, registrado na seção 1.
- Unificar a interface de linha de comando dos dois scripts.
