# KBR-Claude-Plugins

Marketplace de plugins do [Claude Code](https://claude.com/claude-code) da KINTO Brasil.

Três plugins que colocam no Claude Code o que o time usa todo dia: gestão de chamados do
ServiceDesk, geração de documentação no padrão da casa, e o guarda de segredos que os dois usam.

## Antes de começar

Você precisa de duas coisas na máquina:

- **Claude Code** instalado
- **Python 3.10 ou superior** no `PATH` — os plugins usam só a biblioteca padrão, então não há
  `pip install` nenhum para fazer

Para conferir o Python, no terminal:

```bash
python --version
```

Se aparecer `3.10` ou maior, está pronto. Se o comando não for encontrado, instale o Python pelo
[python.org](https://www.python.org/downloads/) marcando a opção **"Add Python to PATH"**.

## Instalar

São dois comandos, digitados **dentro do Claude Code**. Não é preciso ter conta no GitHub nem
saber usar git.

### 1. Registrar o marketplace (uma vez por máquina)

```
/plugin marketplace add kinto-mobility-br/KBR-Claude-Plugins
```

Isso ensina ao Claude Code onde encontrar os plugins da KINTO.

### 2. Instalar o que você for usar

```
/plugin install kbr-servicedesk@kinto-brasil
/plugin install kbr-docs@kinto-brasil
```

Instale só o que fizer sentido para o seu trabalho — os dois são independentes.

> O `kbr-core` **não precisa ser instalado**: ele é dependência dos outros e vem junto
> automaticamente.

### 3. Reabrir o Claude Code

Feche e abra de novo. **Os plugins só carregam na sessão seguinte** — se você tentar usar antes
disso, parece que a instalação não funcionou.

### Conferir se deu certo

Digite `/` e comece a escrever `kbr`. Devem aparecer os comandos dos plugins instalados
(`/kbr-servicedesk:sdp`, `/kbr-docs:report-creator`, e assim por diante).

Se preferir o caminho visual, o comando `/plugin` sozinho abre um gerenciador com menu, onde dá
para instalar, atualizar e desinstalar sem digitar nada.

## Catálogo

| Plugin | O que faz | Comandos |
|---|---|---|
| **`kbr-servicedesk`** | Gestor de chamados do ServiceDesk Plus por menu: lista os seus chamados, mostra detalhes, responde ao solicitante por e-mail, muda status e resolve. Inclui um assistente que ensina você a criar as próprias chaves de acesso. | `/kbr-servicedesk:sdp`<br>`/kbr-servicedesk:configurar`<br>`/kbr-servicedesk:query` |
| **`kbr-docs`** | Gera documentação em HTML com o design system oficial da KINTO, descobrindo a marca do projeto sozinho. | `/kbr-docs:report-creator` |
| **`kbr-core`** | Guarda os seus segredos (tokens de API) num arquivo pessoal e impede que o modelo os leia. Instalado junto com os outros, por dependência. | `/kbr-core:secrets` |

## Configurar o acesso ao ServiceDesk

O `kbr-servicedesk` precisa de uma **chave de acesso individual** para falar com o ServiceDesk.
É uma espécie de crachá que serve só para programas — diferente da sua senha, guardado na sua
máquina, e que pode ser cancelado a qualquer momento sem afetar mais ninguém.

**Você não precisa entender de OAuth nem de API para fazer isso.** Existe um assistente que
conduz o processo inteiro:

```
/kbr-servicedesk:configurar
```

Ele pergunta, antes de começar, se você prefere **só entender o que vai acontecer** ou **fazer
agora, passo a passo**.

### O que esperar

São **19 passos pequenos**, cerca de **15 minutos**. A maior parte o assistente executa; em
alguns você mexe no site da Zoho ou no Bloco de Notas.

| Etapa | Passos | Quem faz |
|---|---|---|
| Preparação | 001 a 004 | o assistente confere, você responde duas perguntas |
| Arquivo e proteção | 005 a 007 | o assistente |
| Criar a chave na Zoho | 008 a 011 | **você**, no navegador |
| Autorizar | 012 a 016 | você gera o código, o assistente troca pelo acesso |
| Identificação e teste | 017 a 019 | você informa o nome, o assistente testa |

### O que ter em mãos

- Login do **portal do ServiceDesk** da KINTO (o mesmo que você usa no dia a dia)
- Acesso ao **[api-console.zoho.com](https://api-console.zoho.com)** com esse mesmo login
- Uns 15 minutos sem interrupção — dá para parar no meio e retomar depois

### Três garantias

- **Nada secreto é digitado na conversa.** As partes secretas você cola direto no Bloco de
  Notas, que o assistente abre para você
- **Nada é executado sem você autorizar.** Em cada passo com comando, você escolhe se o
  assistente roda ou se você mesmo faz
- **Dá para parar em qualquer ponto.** Ao voltar, o assistente retoma de onde você estava

### Se algo der errado

Chame `/kbr-servicedesk:configurar` de novo — ele detecta em que ponto você está e continua dali.
Para ver o que já está preenchido sem expor nenhum valor:

```
/kbr-core:secrets status
```

### Passo a passo detalhado

📄 **[`docs/configurar-servicedesk.md`](docs/configurar-servicedesk.md)** — o que acontece por
baixo do assistente: o Self Client na Zoho, os escopos e por que o de exclusão fica de fora, a
troca do código pelo acesso permanente, as duas camadas de permissão que explicam a maioria dos
erros, e o que fazer em cada mensagem de falha.

Leia se quiser entender o processo, conferir o que foi feito, executar manualmente, ou
diagnosticar um problema.

## Atualizar

São **dois** comandos, nessa ordem:

```
/plugin marketplace update kinto-brasil
/plugin update kbr-servicedesk@kinto-brasil
```

> ⚠️ O segundo sozinho não funciona. Sem atualizar o marketplace antes, o Claude Code continua
> enxergando a versão antiga e responde que já está atualizado.

Reabra o Claude Code depois.

## Para um repositório da KINTO sugerir os plugins

Acrescente ao `.claude/settings.json` do repositório:

```json
{
  "extraKnownMarketplaces": {
    "kinto-brasil": {
      "source": { "source": "github", "repo": "kinto-mobility-br/KBR-Claude-Plugins" }
    }
  },
  "enabledPlugins": {
    "kbr-servicedesk@kinto-brasil": true
  }
}
```

Quem abrir o repositório recebe a sugestão de instalar.

## Desenvolver

Leia o [`CLAUDE.md`](CLAUDE.md). Em resumo:

```bash
python scripts/sincronizar_shared.py          # depois de editar shared/
python scripts/verificar_shared.py            # falha se alguma cópia divergiu
python scripts/testar.py                      # testes de todos os plugins
python scripts/validar.py                     # claude plugin validate --strict
python scripts/criar_tag.py kbr-core --push   # publicar — dá push da tag, visível a todo mundo
```

Cada plugin tem versão própria em `plugins/<nome>/.claude-plugin/plugin.json`. Publicar é criar a
tag `<plugin>--v<versão>` e dar push: é esse padrão que o Claude Code lê para detectar que há
versão nova.

### Segredos

Nenhum segredo entra neste repositório. Os plugins leem credenciais de variável de ambiente ou
de um arquivo na pasta pessoal do usuário, fora de qualquer repositório, e um hook impede que o
modelo leia esse arquivo. Antes de publicar, rode a auditoria descrita no runbook de segurança do
projeto `servicedesk-api`.
