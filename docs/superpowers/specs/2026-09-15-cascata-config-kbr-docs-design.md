# Spec de design — cascata de prioridade projeto/usuário/plugin no `kbr-docs`

**Data:** 2026-09-15
**Status:** aprovado (brainstorming com o Fábio nesta sessão)
**Repositório:** `kinto-mobility-br/KBR-Claude-Plugins` (privado)

---

## 1. Objetivo

Hoje o `kbr-docs` só sabe olhar pra UM lugar: `.docs-brand.yml` na raiz do projeto documentado.
Se o campo não estiver lá, ele fica vazio (ou cai no placeholder da skill, no caso do logo). O
Fábio quer uma cascata de três níveis pra buscar cada campo de marca — dando a ele (e a
qualquer outro técnico) um jeito de guardar um **default pessoal** (nome, cargo, e-mail, e até
um logo/cor próprios) que se aplica a qualquer projeto que não tenha configurado a própria
marca, sem precisar preencher tudo de novo a cada repositório.

### Critérios de sucesso

1. Cada campo do `.docs-brand.yml` é resolvido, na ordem: **projeto → usuário → placeholder do
   plugin** (este último só pra logo). Projeto com o campo preenchido sempre vence; campo vazio
   no projeto cai pro nível de usuário; os dois vazios ficam vazios (comportamento de hoje).
2. O nível de projeto muda de lugar: `<projeto>/.claude/plugins-data/kbr-docs/docs-brand.yml`
   passa a ser o canônico. O `.docs-brand.yml` da raiz (lugar de hoje) continua funcionando
   como alternativa — quem ainda não migrou não quebra.
3. O nível de usuário é novo: `~/.claude/plugins-data/kbr-docs/docs-brand.yml`, preenchido à
   mão (sem descoberta automática nesta fatia).
4. Caminho de arquivo (logo, avatar) resolve relativo à pasta de ONDE O CAMPO VEIO — um logo
   pessoal em `~/.claude/plugins-data/kbr-docs/` funciona mesmo quando o projeto não define
   logo nenhum.
5. `descobrir.py --escrever` grava só no novo local do projeto, e nunca escreve valor do nível
   de usuário dentro do arquivo do projeto — a mescla acontece a cada geração, não uma vez só
   (se o Fábio trocar o e-mail pessoal, todo projeto sem e-mail próprio já reflete isso na
   próxima geração, sem precisar tocar em nenhum `.docs-brand.yml` de projeto).
6. Nenhum teste Python quebra (`testar.py` continua verde) e `validar.py --strict` continua
   limpo.

### Decisões já tomadas (brainstorming de 2026-09-15)

| Decisão | Escolha | Por quê |
|---|---|---|
| Ordem e escopo original ("Idea 1" setup guiado vs. "Idea 2" cascata) | Só a cascata nesta fatia; a skill de setup guiado fica pra outra spec, depois | A cascata é o mecanismo concreto; a skill de setup depende de saber como ele funciona pra explicar direito — e bate de frente com a regra de plugin autocontido (nenhum plugin enumera os outros instalados), que merece design próprio |
| Onde fica o nível de projeto | Dentro de `.claude/`, num subdiretório `plugins-data/<plugin>/` | Opção escolhida entre essa e "criar uma pasta oculta própria na raiz" — mantém tudo relacionado a Claude Code junto, e o padrão `.claude/plugins-data/<nome-do-plugin>/` serve pra qualquer plugin futuro com dado não-sensível pra cascatear, não só o `kbr-docs` |
| Onde fica o nível de usuário | `~/.claude/plugins-data/kbr-docs/`, mesmo padrão do projeto | Consistência — mesma estrutura relativa em qualquer nível |
| Granularidade da mescla | Campo a campo (recursivo, inclusive dentro de `marca.claro`/`marca.escuro`) | Opção escolhida entre essa e "primeiro arquivo que existir vence por completo" — permite o projeto definir só o logo e herdar autoria/contato do nível pessoal |
| Retrocompatibilidade do `.docs-brand.yml` da raiz | Mantida, sem prazo pra sumir | Já existem projetos reais publicados assim (`kbr-nfms-admin-portal`, `KBR-Telematics-Integrations`) — migrar é opcional, quando o Fábio quiser |
| kbr-core (segredos) nesta fatia | Fora — segredo continua só em `~/.kbr/secrets.env`, sem nível de projeto | O próprio Fábio, ao pensar no caso de uso, concluiu que segredo não deveria cascatear por projeto (risco de comitar credencial); o kbr-core hoje não tem nenhuma informação NÃO-sensível pra cascatear |
| Descoberta automática do nível de usuário | Fora desta fatia — preenchido à mão | Faz parte da futura skill de setup guiado (Idea 1), não desta |
| Ferramenta de migração dos 2 projetos existentes | Fora — a retrocompatibilidade já resolve | Migrar é manual, quando o Fábio quiser, não é bloqueante |

---

## 2. O que muda

Local: `plugins/kbr-docs/skills/report-creator/scripts/` (novo módulo) +
`descobrir.py` + `aplicar_marca.py` (ajustados pra usar o módulo novo) + `SKILL.md` (fluxo de
perguntas).

### 2.1 Módulo novo — `resolver_marca.py`

Fica no mesmo `scripts/` dos outros dois (mesmo plugin — não é o caso de "plugin autocontido"
que proíbe ler arquivo de OUTRO plugin; aqui é código dividido dentro do MESMO plugin, prática
já aceita no repositório). `descobrir.py` e `aplicar_marca.py` importam dele — é código Python
normal, sem subprocess, sem duplicar a lógica de mescla em cada script.

```python
def caminho_projeto(raiz: Path) -> Path:
    """<raiz>/.claude/plugins-data/kbr-docs/docs-brand.yml — o canônico."""

def caminho_projeto_legado(raiz: Path) -> Path:
    """<raiz>/.docs-brand.yml — retrocompatibilidade."""

def caminho_usuario() -> Path:
    """~/.claude/plugins-data/kbr-docs/docs-brand.yml."""

def resolver(raiz: Path) -> tuple[dict, list[str]]:
    """
    Config efetivo, campo a campo: projeto (canônico, senão legado) → usuário →
    vazio. Devolve (config_mesclado, notas) — notas descreve de onde cada
    campo de arquivo (logo.claro/escuro, autoria.avatar) veio, pra
    aplicar_marca.py relatar igual já relata hoje ("logo claro: ... → ...").

    Caminhos de arquivo (logo.claro, logo.escuro, autoria.avatar) são
    resolvidos pra ABSOLUTO, contra a pasta de onde aquele campo específico
    veio, ANTES da mescla — assim um logo do nível de usuário nunca é
    resolvido, por engano, contra a raiz do projeto.
    """
```

A mescla é recursiva: para cada chave de um dict (`marca.claro`, por exemplo), desce um nível e
repete a mesma regra campo a campo — não é "a seção toda de um lado ou a seção toda do outro".

Como os outros dois scripts do plugin, ganha `def main() -> int` + `raise SystemExit(main())`
próprios — invocável standalone pra inspeção, sem gravar nada:

```
python resolver_marca.py <raiz>
```

Imprime o config efetivo (já mesclado, com os campos de arquivo já absolutos) e, pra cada
campo que não veio do nível de projeto, de onde veio (`usuário` ou `vazio`) — é isso que o
`SKILL.md` (2.4) instrui a rodar antes de perguntar ao humano o que falta.

### 2.2 `descobrir.py`

- `--escrever` passa a gravar em `caminho_projeto(raiz)` (cria `.claude/plugins-data/kbr-docs/`
  se faltar) — nunca mais na raiz. Continua nunca sobrescrevendo um arquivo que já exista nesse
  local novo (mesma regra de hoje, só o lugar muda).
- Continua escaneando só a árvore do projeto — a heurística de achar logo/cor/nome não muda
  em nada.
- **Novo passo, antes de perguntar o que não achou:** roda `resolver_marca.resolver(raiz)` e
  só pergunta ao humano os campos que os DOIS níveis (projeto recém-descoberto + usuário)
  deixaram vazios. Ex.: se `~/.claude/plugins-data/kbr-docs/docs-brand.yml` já tem
  `autoria.autor`/`cargo`/`email`, a skill não pergunta esses três de novo.

### 2.3 `aplicar_marca.py`

- Troca a leitura direta de `carregar_yaml(raiz / '.docs-brand.yml')` por
  `resolver_marca.resolver(raiz)` — devolve o config já mesclado, com os campos de arquivo já
  absolutos.
- `instalar_logos`/`instalar_avatar` deixam de receber `raiz` pra resolver caminho relativo —
  passam a receber o caminho já absoluto (ou vazio) que `resolver()` devolveu, e só cuidam de
  copiar/avisar tamanho, como já fazem. Assinatura muda de
  `instalar_logos(cfg, raiz, destino)` pra `instalar_logos(cfg, destino)` (idem `instalar_avatar`).
- O relatório impresso (`logo claro: ... → ...`, `avatar: ... → ...`) passa a citar de qual
  nível o valor veio, quando não for o do projeto (ex.: `logo claro: ~/.claude/plugins-data/
  kbr-docs/minha-logo.svg (nível de usuário) → assets/logo-claro.svg`).

### 2.4 `SKILL.md`

- Documenta os três níveis e a ordem, com os dois caminhos exatos (canônico + legado) e o
  caminho do usuário.
- Instrui: antes de perguntar o que não descobriu, checar o efetivo (via `resolver_marca.py`
  chamado standalone, ou o próprio relatório do `descobrir.py`) e só perguntar o que sobrou
  vazio nos dois níveis.

---

## 3. O que NÃO muda

- Formato do YAML (campos, comentários, `# SUGESTÃO — confira`) — o mesmo em qualquer nível.
- Comportamento de "nunca sobrescreve arquivo existente" — só passou a valer pro local novo.
- Heurística de descoberta (logo por nome/luminância, cor de SVG, nome do projeto) — inalterada.
- `kbr-core`, `kbr-servicedesk` — nenhum dos dois muda nesta fatia.
- O placeholder de logo do plugin — continua sendo o último recurso, só pra campo de imagem.

---

## 4. Testes

Novo módulo de teste, `test_resolver_marca.py` (mesmo padrão de rigor do resto — sem chamada de
rede, TDD, casos de borda como parte do design):

- projeto com tudo preenchido → usuário nunca é lido (nem precisa existir);
- projeto vazio (arquivo existe, campos em branco) → usa o efetivo do usuário por completo;
- projeto parcial (só `logo.claro`, por exemplo) → mescla campo a campo, inclusive dentro de
  `marca.claro`/`marca.escuro` (ex.: projeto define `marca.claro.brand` mas não `.hover`/`.tint`
  — cada um resolvido independente);
- nenhum dos dois define logo → placeholder (comportamento de hoje, inalterado);
- logo do nível de usuário resolve contra `~/.claude/plugins-data/kbr-docs/`, não contra a raiz
  do projeto — testado com um caminho relativo que só existiria numa das duas pastas;
- só o `.docs-brand.yml` legado da raiz (sem `.claude/plugins-data/`) → ainda funciona,
  idêntico ao comportamento de hoje;
- projeto tem os dois — canônico e legado — → canônico vence, legado é ignorado por completo
  (não mesclado com ele);
- os dois níveis totalmente ausentes → efetivo vazio, mesmo resultado de "documento sem marca
  nenhuma" de hoje.

Testes existentes de `descobrir.py`/`aplicar_marca.py` que hoje montam um `.docs-brand.yml` na
raiz continuam passando (a retrocompatibilidade é exatamente pra isso) — os que testam
`instalar_logos`/`instalar_avatar` precisam de ajuste de assinatura (remover o argumento
`raiz`), sem mudar o que verificam.

---

## 5. Fora de escopo desta fatia

- `kbr-core` (segredos) — confirmado que não cascateia por projeto.
- A skill de setup guiado que ensina a preencher os três níveis (Idea 1) — spec própria,
  depois desta.
- Descoberta automática do nível de usuário.
- Migrar os 2 projetos que já têm `.docs-brand.yml` na raiz pro local novo — fica manual,
  quando o Fábio quiser, não bloqueia nada.
- Qualquer outro plugin adotar o mesmo padrão `.claude/plugins-data/<plugin>/` — o padrão fica
  documentado (nesta spec e no `SKILL.md`) pra quem quiser copiar depois, mas não é
  implementado em nenhum outro plugin nesta fatia.
