# Spec de design — Fundação do marketplace + plugin ServiceDesk

**Data:** 2026-09-13
**Status:** rascunho para revisão
**Repositório:** `kinto-mobility-br/KBR-Claude-Plugins` (privado)
**Fatia:** 1 de 3 — as fatias 2 (`kbr-docs`) e 3 (`kbr-dynamics-bc`) terão specs próprias.

---

## 1. Objetivo

Criar o repositório que centraliza os plugins do Claude Code da KINTO Brasil, publicá-lo como
marketplace privado e entregar os dois primeiros plugins:

- **`kbr-core`** — o mecanismo de segredos por usuário e o hook que impede o modelo de ler o
  arquivo de segredos.
- **`kbr-servicedesk`** — um gestor de chamados genérico do ServiceDesk Plus Cloud (SDP), operado
  por menu, com um wizard passo a passo para pessoas leigas configurarem o próprio acesso.

### Critérios de sucesso

Uma pessoa da KINTO, num Windows limpo com Claude Code e Python instalados, consegue:

1. adicionar o marketplace e instalar `kbr-servicedesk` com dois comandos, e o `kbr-core` vem junto
   por dependência;
2. abrir `/kbr-servicedesk:sdp`, ser levada ao wizard por não ter credenciais, e concluir a
   configuração em até 15 minutos usando só o guia, sem ajuda de ninguém;
3. listar os próprios chamados abertos, ver o detalhe de um, adicionar nota, mudar status e
   resolver, sempre com confirmação antes de gravar;
4. em nenhum momento ver um valor de segredo no chat, e uma tentativa do modelo de ler
   `~/.kbr/secrets.env` por qualquer ferramenta é negada com explicação;
5. `git status` em qualquer repositório nunca mostra o arquivo de segredos, porque ele vive fora
   de todos eles.

### Decisões já tomadas (brainstorming de 2026-09-13)

| Decisão | Escolha | Alternativas descartadas |
|---|---|---|
| Formato de distribuição | Um repositório que é marketplace e monorepo de plugins | Um repo por plugin; plugin monolítico |
| Granularidade | Um plugin por domínio | Um plugin por skill |
| Público da 1ª versão | Quem usa Claude Code (TI e Dados) | Empacotar também para o claude.ai (fica para depois, estrutura preparada) |
| Segredos | Arquivo `.env` por usuário em `~/.kbr/secrets.env`, fora de qualquer repo | 1Password (só o Fábio tem); cofre do SO via `keyring` (dependência pip); `userConfig` nativo (escrita única, só leitura pelo plugin) |
| Proteção do arquivo | Hook `PreToolUse` distribuído pelo plugin + ACL do arquivo + regra `deny` opcional no settings do usuário | Só regra `deny` (plugin não consegue distribuir) |
| Formato do arquivo | `CHAVE=valor` por linha | YAML (exige PyYAML); JSON estilo AppSettings (ruim de editar à mão) |
| OAuth Zoho | Self Client individual por técnico | Cliente corporativo registrado pela TI (fica para depois; grava as mesmas chaves) |
| Escopo do gestor | Núcleo genérico: operações que qualquer técnico usa | Fluxo de documentação em `tasks/` do Fábio (vira modo opcional em versão futura) |
| Acesso à API | Scripts Python só com biblioteca padrão, chamados pela skill | Servidor MCP (processo residente, mais código); `curl` pelo modelo (segredo passaria pelo comando) |

---

## 2. Repositório e marketplace

### 2.1 Estrutura

```
KBR-Claude-Plugins/
├── .claude-plugin/
│   └── marketplace.json            catálogo: nome, owner, lista de plugins
├── plugins/
│   ├── kbr-core/
│   │   ├── .claude-plugin/plugin.json
│   │   ├── skills/secrets/SKILL.md
│   │   ├── scripts/kbr_secrets.py          cópia sincronizada de shared/
│   │   ├── hooks/hooks.json
│   │   ├── hooks/proteger_secrets.py
│   │   ├── tests/
│   │   └── README.md
│   └── kbr-servicedesk/
│       ├── .claude-plugin/plugin.json      dependencies: ["kbr-core"]
│       ├── skills/sdp/SKILL.md             menu do gestor
│       ├── skills/configurar/SKILL.md      wizard
│       ├── scripts/kbr_secrets.py          cópia sincronizada de shared/
│       ├── scripts/sdp_api.py
│       ├── guia/                           guia HTML do wizard (design system KINTO)
│       │   ├── index.html
│       │   ├── assets/
│       │   └── img/                        capturas de tela do console Zoho
│       ├── tests/
│       └── README.md
├── shared/
│   └── kbr_secrets.py                  fonte única; nunca é executado daqui
├── scripts/
│   ├── sincronizar_shared.py           copia shared/ para cada plugin que o declara
│   ├── verificar_shared.py             falha se alguma cópia divergir da fonte
│   ├── validar.py                      roda `claude plugin validate` em todos os plugins
│   └── criar_tag.py                    lê a versão do plugin.json e cria a tag `<plugin>--v<versão>`
├── docs/superpowers/specs/             specs de design (esta e as próximas)
├── .github/workflows/validar.yml
├── .gitignore
├── CLAUDE.md                           regras para quem mantém o repo
└── README.md                           catálogo, instalação, snippet para os repos KBR
```

### 2.2 `marketplace.json`

```json
{
  "name": "kinto-brasil",
  "description": "Plugins do Claude Code da KINTO Brasil: documentação, ServiceDesk, design systems",
  "owner": { "name": "KINTO Brasil — TI" },
  "plugins": [
    {
      "name": "kbr-core",
      "description": "Segredos por usuário em ~/.kbr/secrets.env e proteção contra leitura pelo modelo",
      "source": "./plugins/kbr-core",
      "category": "productivity"
    },
    {
      "name": "kbr-servicedesk",
      "description": "Gestor de chamados do ServiceDesk Plus por menu, com wizard de configuração",
      "source": "./plugins/kbr-servicedesk",
      "category": "productivity"
    }
  ]
}
```

O nome do marketplace é `kinto-brasil`; o comando de instalação fica
`/plugin install kbr-servicedesk@kinto-brasil`.

### 2.3 Regras do repositório (vão para o `CLAUDE.md`)

- **PT-BR em tudo**: SKILL.md, mensagens dos scripts, comentários, commits, README. Identificadores
  de código e termos técnicos (OAuth, refresh token, Self Client) ficam no original.
- **Python só com biblioteca padrão.** Nenhum `pip install` para usar os plugins. `urllib`,
  `json`, `pathlib`, `subprocess`, `unittest`. Cada script segue a convenção do workspace:
  `def main()` + `raise SystemExit(main())`.
- **Portável, Windows primeiro.** Caminhos por `pathlib`, `Path.home()`, nada de barra fixa. Testado
  no Windows; não pode quebrar no Mac nem no Linux.
- **Plugin é autocontido.** Um plugin nunca lê arquivo de outro em tempo de execução. Código
  compartilhado vive em `shared/` e é copiado para cada plugin por `scripts/sincronizar_shared.py`.
  Edita-se só a fonte; a CI falha se uma cópia divergir.
- **Caminhos dentro de skills sempre via `${CLAUDE_PLUGIN_ROOT}`.** Nunca `~/.claude/skills/...`.
- **Nunca `git add -A`.** Nomear os caminhos e conferir `git status --short` antes de commitar.

### 2.4 Versionamento e publicação

- Cada plugin tem `version` semver no próprio `plugin.json`. Os dois nascem em `0.1.0`.
- Publicar uma versão é criar a tag `<plugin>--v<versão>` (ex.: `kbr-core--v0.1.0`) e dar push.
  É esse padrão de tag que o Claude Code lê para detectar atualização em marketplace baseado em git.
  `scripts/criar_tag.py <plugin>` lê a versão e cria a tag; recusa se a tag já existir.
- Quem consome atualiza com `/plugin marketplace update kinto-brasil` e `/plugin update <plugin>@kinto-brasil`.
- Mudança em `shared/kbr_secrets.py` obriga a subir a versão de todos os plugins que o vendorizam.

### 2.5 Distribuição

O `README.md` traz:

1. **Instalação manual** — `/plugin marketplace add kinto-mobility-br/KBR-Claude-Plugins` e
   `/plugin install kbr-servicedesk@kinto-brasil`. O repo é privado: funciona com as credenciais
   git que a pessoa já usa para clonar os repos da KINTO.
2. **Snippet para os repositórios KBR** — trecho de `.claude/settings.json` com
   `extraKnownMarketplaces` apontando para o marketplace e `enabledPlugins` com os plugins que
   aquele repo usa. Quem abre o repo recebe a sugestão de instalar.
3. **Pré-requisitos por máquina** — Claude Code, Python 3.10 ou superior no `PATH`, acesso git ao
   repo. Nada de pip.

### 2.6 CI (`.github/workflows/validar.yml`)

Em todo push e pull request:

1. `python scripts/verificar_shared.py` — cópias idênticas à fonte;
2. `python -m unittest discover -s plugins -p "test_*.py"` — testes dos dois plugins;
3. instala o Claude Code CLI e roda `python scripts/validar.py`, que executa
   `claude plugin validate` em cada pasta de `plugins/` e no marketplace.

---

## 3. Plugin `kbr-core`

### 3.1 Arquivos por usuário

```
~/.kbr/
├── secrets.env        segredos — PROTEGIDO (modelo não lê)
├── config.json        preferências não sensíveis — modelo pode ler
└── cache/             tokens de curta duração — PROTEGIDO
```

No Windows, `~` é `%USERPROFILE%`. A pasta fica fora de qualquer repositório, então nunca entra
em `git status`.

**Permissões.** No Windows: `icacls` na pasta com herança removida e controle total só para o
usuário atual, herdado pelos filhos (`(OI)(CI)F`). No Mac e Linux: `chmod 700` na pasta e `600`
no arquivo. Aplicado por `init` e conferido por `status`.

### 3.2 Formato de `secrets.env`

```dotenv
# ============================================================
# Segredos dos plugins KINTO — este arquivo é seu e fica fora do git.
# Preencha os valores depois do "=" e salve. Não compartilhe.
# ============================================================

# --- kbr-servicedesk ---
SDP_CLIENT_ID=
SDP_CLIENT_SECRET=
SDP_GRANT_CODE=
SDP_REFRESH_TOKEN=
```

Regras de leitura, e é isso que os testes cobrem:

- BOM UTF-8 e `\r\n` são ignorados.
- Linha vazia ou começando com `#` é ignorada.
- A chave vai até o primeiro `=`; espaços em volta da chave e do valor são removidos.
- Valor entre aspas simples ou duplas perde as aspas. Não há interpolação nem escape.
- Chave válida: `[A-Z][A-Z0-9_]*`. Linha que não casa gera aviso no `status` e é ignorada na leitura.
- Chave repetida: vale a última.

### 3.3 Módulo `kbr_secrets.py`

Fonte em `shared/`, vendorizado em cada plugin. Uma única responsabilidade: dar acesso aos
segredos aos scripts sem que o valor passe pelo modelo.

**API para os outros scripts:**

```python
obter(nome: str, obrigatorio: bool = True) -> str | None
```

Ordem de resolução: (1) variável de ambiente com o mesmo nome — serve para automação, CI e para o
Claude Code na nuvem, onde não há arquivo; (2) `~/.kbr/secrets.env`. Se `obrigatorio` e não
encontrou, lança `SegredoAusente(nome)`, cuja mensagem diz qual comando rodar
(`/kbr-core:secrets status` e, para chaves `SDP_*`, `/kbr-servicedesk:configurar`).

`caminho_arquivo()` e `caminho_config()` centralizam os caminhos; nada mais no repo os monta.

**Linha de comando** (o que a skill chama):

| Subcomando | O que faz |
|---|---|
| `init` | Cria `~/.kbr/`, `secrets.env` com o cabeçalho, `config.json` vazio e `cache/`; aplica as permissões. Idempotente. |
| `registrar --plugin <nome> --chaves A,B,C` | Acrescenta o bloco `# --- <nome> ---` com as chaves que faltam, valor vazio. Nunca altera valor existente nem reordena. Idempotente. |
| `status [--plugin <nome>]` | Para cada chave: `preenchida` ou `vazia`, nunca o valor. Confere permissões, avisa linhas inválidas, e diz se o hook está ativo e se a regra `deny` existe no settings do usuário. Sai com código 1 se algo essencial faltar. |
| `editar` | Abre `secrets.env` no editor padrão do sistema por dentro do Python (`os.startfile` no Windows; `open` ou `xdg-open` nos outros). O caminho nunca aparece num comando do chat. |
| `proteger` | Grava `Read(~/.kbr/secrets.env)`, `Edit(~/.kbr/secrets.env)`, `Read(~/.kbr/cache/**)` e `Edit(~/.kbr/cache/**)` em `permissions.deny` do `~/.claude/settings.json`, preservando o resto do arquivo. `config.json` fica de fora, como no hook. Só é chamado depois de o usuário confirmar no chat. |

**Não existe** subcomando que devolva o valor de uma chave. Isso é deliberado.

### 3.4 Hook `PreToolUse`

`hooks/hooks.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Read|Edit|Write|MultiEdit|NotebookEdit|Grep|Glob|Bash",
        "hooks": [
          { "type": "command", "command": "python \"${CLAUDE_PLUGIN_ROOT}/hooks/proteger_secrets.py\"" }
        ]
      }
    ]
  }
}
```

`proteger_secrets.py` lê o JSON da ferramenta pela entrada padrão e decide:

1. Junta os campos candidatos de `tool_input`: `file_path`, `notebook_path`, `path`, `pattern`,
   `command`.
2. Normaliza cada um: minúsculas, `\` vira `/`, `~`, `$HOME`, `$env:USERPROFILE` e
   `%USERPROFILE%` viram o caminho real da home.
3. **Nega** se algum campo contém o caminho normalizado de `~/.kbr/` ou o trecho `.kbr/`,
   **exceto** quando toda referência a `.kbr/` é a `config.json`.
4. Ao negar, imprime JSON com `permissionDecision: "deny"` e uma
   `permissionDecisionReason` em português: explica que o arquivo guarda segredos pessoais, que os
   scripts dos plugins o leem sozinhos, e aponta `/kbr-core:secrets status` para conferir sem expor.
5. Caso contrário, sai com código 0 sem imprimir nada.

O hook cobre `cat`, `type`, `Get-Content`, `sed`, redirecionamentos e qualquer outro comando,
porque olha o texto inteiro. Não bloqueia os próprios scripts dos plugins, porque eles são
chamados por `${CLAUDE_PLUGIN_ROOT}/scripts/...` e leem o arquivo por dentro, sem o caminho no
comando.

**Limites conhecidos, registrados no README.** O hook e a regra `deny` são barreiras contra
exposição acidental no transcript, não uma fronteira de segurança: um script escrito na hora que
abra o arquivo por dentro passa. O arquivo em repouso tem a mesma postura de
`~/.aws/credentials`. Se o Python não estiver no `PATH`, o hook falha e o Claude Code segue sem
bloquear; `status` avisa isso.

### 3.5 Skill `/kbr-core:secrets`

Skill curta, em PT-BR, que traduz `init`, `status`, `editar` e `proteger` em conversa:

- `secrets` sem argumento ou `status` → roda `status` e explica o resultado em uma frase por chave.
- `init` → roda `init`, mostra o que criou e **pergunta** se pode gravar a regra `deny` no settings
  do usuário; só chama `proteger` depois do sim.
- `editar` → roda `editar` e orienta: "cole os valores no editor, salve, feche e me avise".
- Regra dura da skill: nunca pedir um valor de segredo no chat; se o usuário colar um por conta
  própria, orientar a apagar do arquivo e gerar outro, porque já está no transcript.

---

## 4. Plugin `kbr-servicedesk`

### 4.1 `plugin.json`

```json
{
  "name": "kbr-servicedesk",
  "version": "0.1.0",
  "description": "Gestor de chamados do ServiceDesk Plus Cloud por menu, com wizard de configuração para leigos",
  "author": { "name": "KINTO Brasil — TI" },
  "dependencies": ["kbr-core"],
  "keywords": ["servicedesk", "sdp", "chamados", "kinto"]
}
```

### 4.2 `config.json` (parte do ServiceDesk)

```json
{
  "servicedesk": {
    "tecnico_nome": "Nome Sobrenome",
    "tecnico_email": "nome@kintomobility.com.br",
    "data_center": "us",
    "api_base": "https://sdpondemand.manageengine.com/api/v3",
    "token_url": "https://accounts.zoho.com/oauth/v2/token"
  }
}
```

`data_center` fixa `us` na primeira versão; os dois URLs derivam dele e ficam gravados para
diagnóstico. Não é segredo, o modelo pode ler.

### 4.3 Módulo `sdp_api.py`

Só biblioteca padrão. Reaproveita o que `tasks/_sync_sdp.py` e `tasks/_tok.py` do workspace já
fazem, mas lendo os segredos por `kbr_secrets.obter`.

**Autenticação.** `SDP_REFRESH_TOKEN` + `SDP_CLIENT_ID` + `SDP_CLIENT_SECRET` → `POST token_url`
com `grant_type=refresh_token` → access token válido por 1 hora, guardado em
`~/.kbr/cache/sdp_access_token.json` com o instante de expiração. Renova só quando faltarem menos
de 5 minutos. Cabeçalhos das chamadas: `Authorization: Zoho-oauthtoken <access>` e
`Accept: application/vnd.manageengine.sdp.v3+json`.

**Subcomandos.** Saída sempre JSON em UTF-8, sem credenciais, sem cabeçalhos HTTP:

| Subcomando | Chamada SDP | Observações |
|---|---|---|
| `testar` | `GET /requests` filtrando pelo técnico do `config.json` | Devolve nome do técnico e contagem de chamados; é o teste final do wizard. |
| `listar [--status <s>] [--todos]` | `GET /requests` com `search_criteria` por técnico | Padrão: só status não finais (exclui Resolved, Closed, Cancelled). Campos: nº, assunto, solicitante, status, criado em, urgência. |
| `detalhe <nº>` | `GET /requests/<id>` + `GET /requests/<id>/notes` | Converte a descrição HTML em texto; lista as últimas notas. Resolve o nº de exibição para o id interno e nunca mostra o id interno. |
| `nota <nº> --arquivo <html> [--visivel-solicitante] --confirmar` | `POST /requests/<id>/notes` | Sem `--confirmar` só valida e mostra o que faria. |
| `status <nº> "<status>" [--comentario <txt>] --confirmar` | `PUT /requests/<id>` | Status de espera (On Hold, Aguardando Aprovação) exigem `--comentario`, que vai em `onhold_scheduler`. |
| `resolver <nº> --arquivo <html> --confirmar` | `PUT /requests/<id>` com `resolution` + status `Resolved` | |
| `autorizar` | `POST token_url` com `grant_type=authorization_code` | Passo 6 do wizard: lê `SDP_GRANT_CODE`, `SDP_CLIENT_ID` e `SDP_CLIENT_SECRET`, grava `SDP_REFRESH_TOKEN` e apaga o grant code do arquivo. |

**Confirmação.** Nenhuma escrita acontece sem `--confirmar`. A skill só passa a flag depois de
mostrar exatamente o que vai enviar e receber "s" do usuário.

**Erros traduzidos.** O módulo mapeia os erros da Zoho e do SDP para mensagens em português com
a ação a tomar:

| Origem | Mensagem ao usuário |
|---|---|
| `invalid_code` na troca do grant code | "O código expirou ou já foi usado. Ele vale 10 minutos. Gere outro no console (passo 5) e cole de novo." |
| `invalid_client` | "Client ID ou Client Secret incorretos. Confira se copiou os dois inteiros, sem espaços (passo 4)." |
| `invalid_client` com dica de data center | "Parece que o cliente foi criado no console de outro país. A KINTO usa o console americano: api-console.zoho.com." |
| HTTP 401 numa chamada de API | "O acesso foi revogado ou o token venceu. Refaça os passos 5 e 6 do wizard." |
| HTTP 403 ou erro de escopo | "O cliente não tem permissão para esta operação. Gere um novo código com a lista completa de escopos (passo 5)." |
| Chave `SDP_*` vazia | "Falta preencher `<chave>`. Abra o wizard com a opção 6." |
| Falha de rede | "Não consegui falar com o ServiceDesk. Confira a conexão e a VPN, se usar, e tente de novo." |

**Escopos OAuth** que o wizard manda a pessoa marcar, na ordem exata:
`SDPOnDemand.requests.READ`, `SDPOnDemand.requests.CREATE`, `SDPOnDemand.requests.UPDATE`.
São os três que o cliente atual do Fábio usa. O plano inclui uma tarefa de confirmar essa lista
contra o console antes de escrever o guia; se faltar algum para `notes` ou `resolution`, entra na
lista e no guia ao mesmo tempo.

### 4.4 Skill `/kbr-servicedesk:sdp` — o gestor

Chatbot com menu, no molde do `gestor-chamados` do workspace, sem o fluxo de documentação local.

```
🗂️  GESTOR DE CHAMADOS — ServiceDesk KINTO
    Técnico: <nome> · chamados abertos: <N>

1. Meus chamados abertos          4. Mudar status de um chamado
2. Ver detalhe de um chamado      5. Resolver chamado
3. Adicionar nota a um chamado    6. Configurar acesso ao ServiceDesk
0. Sair
```

Regras duras da skill:

- **Sempre termina com um menu.** Nunca deixa o usuário sem próximos passos.
- **Aceita texto livre.** "mostra o 4942" é a opção 2 no chamado 4942. Se ambíguo, oferece as
  duas ou três leituras mais prováveis em vez de adivinhar.
- **Nunca grava sem confirmação explícita no mesmo turno.** Mostra o texto ou a mudança e pergunta
  "confirmar? (s/n)". Só então chama o script com `--confirmar`.
- **Credenciais ausentes ou inválidas** em qualquer opção: explica em uma frase e oferece a opção 6.
- **Números de chamado** sempre pelo nº de exibição do SDP; id interno nunca aparece.
- **Notas e textos de resolução** em HTML simples (parágrafos, listas, negrito), na primeira
  pessoa do singular, tom cordial. A skill redige a partir do que o usuário ditar, mostra a prévia
  em texto, e só envia depois do sim. O HTML vai num arquivo temporário no scratchpad da sessão,
  apagado depois do envio.
- **Segredo nunca no chat.** A skill não pede, não mostra, não repete valor de `SDP_*`.
- **PT-BR** em tudo.

Fluxo de cada opção:

1. **Meus chamados abertos** → `listar` → tabela com nº, assunto, solicitante, status, criado em,
   urgência. Oferece filtrar por status ou incluir finalizados.
2. **Detalhe** → pede o nº se não veio → `detalhe` → assunto, solicitante, status, datas,
   descrição em texto, últimas notas. Oferece as ações 3, 4 e 5 sobre este chamado.
3. **Nota** → pede o texto e se o solicitante deve ver → redige HTML → prévia → confirmação → `nota`.
4. **Status** → lista os status válidos do SDP da KINTO (Open, In Progress, On Hold, Aguardando
   Aprovação, Resolved, Closed) → pede comentário quando o status exigir → confirmação → `status`.
5. **Resolver** → pede o texto de conclusão → HTML → prévia → confirmação → `resolver`.
6. **Configurar** → invoca a skill `configurar`.

### 4.5 Skill `/kbr-servicedesk:configurar` — o wizard

Público: pessoa que usa o ServiceDesk pelo navegador e nunca ouviu falar de OAuth, terminal ou
Python. Premissas: sabe abrir um site, copiar e colar, e abrir o Bloco de Notas.

**Forma.** Um passo por turno. Cada turno explica o passo em linguagem simples, diz exatamente o
que a pessoa faz agora, executa o que é automático, e termina com o mini-menu:

```
1. Feito, próximo passo   2. Explicar de novo   3. Estou com erro   0. Sair (posso voltar depois)
```

"Estou com erro" abre um diagnóstico do passo atual com as causas mais comuns, e volta ao mesmo
passo. Sair a qualquer momento não estraga nada: rodar de novo detecta o que já está pronto e
pula para o primeiro passo pendente.

**Dois canais.** Além do chat, o wizard abre no navegador o **guia HTML** (`guia/index.html`),
com uma seção por passo e uma captura de tela por tela do console da Zoho, com a área de clicar
destacada. O chat diz "veja a figura 4.2 do guia" quando o passo envolve o console.

**Os oito passos:**

| # | Passo | Automático | A pessoa faz | Verificação |
|---|---|---|---|---|
| 1 | Pré-requisitos | `python --version`; `kbr_secrets.py status`; pergunta se consegue entrar no portal do ServiceDesk | Instala Python pela Microsoft Store se faltar (link e prints no guia) | Python ≥ 3.10 no `PATH`; hook do `kbr-core` ativo |
| 2 | Entender o que vai acontecer | — | Lê a explicação: "cliente" é uma chave que só você tem; o arquivo de segredos é seu e fica fora do chat; nada será digitado aqui | Confirma que entendeu |
| 3 | Criar o arquivo de segredos | `init` + `registrar --plugin kbr-servicedesk --chaves SDP_CLIENT_ID,SDP_CLIENT_SECRET,SDP_GRANT_CODE,SDP_REFRESH_TOKEN`; abre o guia no navegador | — | `status` mostra as 4 chaves vazias |
| 4 | Criar o Self Client na Zoho | `editar` abre o arquivo no editor | No console americano: Add Client → Self Client → Create → copia Client ID e Client Secret → cola no arquivo → salva → fecha | `status`: `SDP_CLIENT_ID` e `SDP_CLIENT_SECRET` preenchidas |
| 5 | Gerar o código de autorização | `editar` | Aba Generate Code → cola a lista de escopos → duração 10 minutos → descrição livre → Create → copia o código → cola em `SDP_GRANT_CODE` → salva | `status`: `SDP_GRANT_CODE` preenchida; aviso do prazo de 10 minutos |
| 6 | Trocar o código pelo acesso permanente | `autorizar` | — | `SDP_REFRESH_TOKEN` preenchida e `SDP_GRANT_CODE` apagada; erros traduzidos (tabela 4.3) |
| 7 | Identificar o técnico | Grava nome e e-mail em `config.json`; `testar` | Informa nome e e-mail corporativo | "Conectado como <nome>. Você tem N chamados atribuídos." |
| 8 | Proteção e resumo | `status`; oferece `proteger` | Diz sim ou não à regra `deny` | Resumo do que ficou pronto e como abrir o gestor |

Nome e e-mail não são segredo, então passam pelo chat normalmente.

### 4.6 Guia HTML

Gerado com a skill `docs-html` do workspace, no design system KINTO, e versionado já renderizado
em `guia/` para não depender de gerar nada na máquina do usuário. Abre por `file://`.

Conteúdo: uma seção por passo do wizard, com o texto do passo, a captura de tela numerada
(`img/04-1-add-client.png`, `img/04-2-self-client.png`, ...) e a lista de escopos num bloco de
copiar. Sem logo genérico: usa os logos da KINTO já presentes em `assets/design-system/` do
workspace.

**Capturas de tela.** Feitas uma vez, com o Fábio logado no console da Zoho, com dados fictícios
ou borrados onde aparecer segredo. É uma tarefa explícita do plano, com lista das telas
necessárias: console inicial, Add Client, escolha de Self Client, tela com Client ID e Secret,
aba Generate Code preenchida, código gerado.

---

## 5. Fluxo de dados

```
usuário ──chat──▶ skill sdp ──Bash──▶ python sdp_api.py listar
                                          │
                                          ├─ kbr_secrets.obter("SDP_REFRESH_TOKEN")
                                          │     ├─ variável de ambiente?  → usa
                                          │     └─ ~/.kbr/secrets.env     → usa
                                          ├─ ~/.kbr/cache/sdp_access_token.json (renova se preciso)
                                          └─ HTTPS → SDP ──▶ JSON sem segredo ──▶ skill ──▶ tabela no chat
```

O modelo só vê o JSON de saída. O hook do `kbr-core` impede que ele leia `~/.kbr/secrets.env` ou o
cache por qualquer ferramenta.

---

## 6. Testes

**Unitários** (`unittest`, sem dependências, rodam na CI e localmente com
`python -m unittest discover -s plugins -p "test_*.py"`):

- `kbr_secrets`: parser do `.env` com BOM, `\r\n`, comentários, aspas, espaços, chave repetida,
  linha inválida; ordem de resolução variável de ambiente antes do arquivo; `registrar`
  idempotente e sem tocar valores; `init` idempotente; `status` nunca imprime valor (teste
  procura o valor na saída e falha se achar).
- `proteger_secrets`: nega `Read` de `~/.kbr/secrets.env` com `~`, home absoluta, `%USERPROFILE%`,
  barras invertidas e maiúsculas; nega `Bash` com `cat`, `type`, `Get-Content`, redirecionamento e
  `python -c open(...)` que citem o caminho; permite `~/.kbr/config.json`; permite
  `python ${CLAUDE_PLUGIN_ROOT}/scripts/sdp_api.py listar`; permite qualquer caminho fora de `.kbr`.
- `sdp_api`: montagem de URL, cabeçalhos e `search_criteria`; renovação do access token só quando
  perto de vencer; mapa de erros da tabela 4.3; recusa de escrita sem `--confirmar`; `autorizar`
  grava o refresh token e apaga o grant code. Rede simulada substituindo `urllib.request.urlopen`.

**Integração e validação:**

- `claude plugin validate` nos dois plugins e no marketplace, na CI.
- `verificar_shared.py` na CI.
- Roteiro manual de ponta a ponta antes da primeira tag, num perfil de Windows limpo: instalar o
  marketplace, instalar `kbr-servicedesk`, abrir `/kbr-servicedesk:sdp`, completar o wizard só
  com o guia, listar chamados, adicionar uma nota num chamado de teste, tentar `cat ~/.kbr/secrets.env`
  e ver a negação, conferir que o transcript não tem valor de segredo.

---

## 7. Fora de escopo desta fatia

- Modo de documentação de tasks em `tasks/` (spec, HTML, metadados, estados) — versão futura do
  `kbr-servicedesk`, como modo opcional.
- Cliente OAuth corporativo registrado pela TI, com listener local.
- Plugins `kbr-docs` e `kbr-dynamics-bc` — fatias 2 e 3.
- Empacotamento das skills para upload no claude.ai.
- Criptografia do `secrets.env` em repouso (DPAPI no Windows).
- Servidor MCP para o SDP.
- Injeção de variáveis por hook `SessionStart`.
- Suporte a data centers da Zoho fora do americano.
