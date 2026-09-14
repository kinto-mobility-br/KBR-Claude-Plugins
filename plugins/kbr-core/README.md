# kbr-core

Base dos plugins KINTO: segredos por usuário e a proteção que impede o modelo de lê-los.

## O que ele instala

- **Skill `/kbr-core:secrets`** — cria o arquivo de segredos, diz o que está preenchido, abre
  para edição e ativa a proteção.
- **Hook `PreToolUse`** — nega qualquer tentativa de acessar algo dentro de `~/.kbr/`, exceto
  `config.json` sozinho (sem nada depois). Roda antes de Read, Edit, Write, MultiEdit,
  NotebookEdit, Grep, Glob e Bash. Ver "Limites da proteção" abaixo para o que isso cobre de
  fato.
- **Quatro regras `deny`** — gravadas em `~/.claude/settings.json` por
  `/kbr-core:secrets proteger`: `Read` e `Edit` em `~/.kbr/secrets.env`, e `Read` e `Edit` em
  `~/.kbr/cache/**`. Reforçam o hook pelo mecanismo de permissões do próprio Claude Code,
  numa camada independente dele.

## Onde ficam os arquivos

```
~/.kbr/
├── secrets.env   segredos — protegido
├── config.json   preferências não sensíveis — legível
└── cache/        tokens de curta duração — protegido
```

No Windows, `~` é `%USERPROFILE%`. A pasta fica fora de qualquer repositório: nenhum
`git status` jamais mostra o arquivo de segredos.

## Formato do `secrets.env`

`CHAVE=valor`, uma por linha. Comentário começa com `#`. Aspas em volta do valor são
removidas. Chave repetida: vale a última.

Quem tem o **1Password CLI** pode escrever a referência no lugar do valor:

```dotenv
SDP_CLIENT_ID=op://Cofre/Nome do item/campo
```

O valor é resolvido na hora com `op read` e cacheado pelo tempo do processo. Quando um script
precisa gravar numa chave assim, ele grava no cofre com `op item edit` — a referência nunca
vira valor literal no arquivo. Quem não usa 1Password não precisa de nada disso.

## Ordem de resolução

1. Variável de ambiente de mesmo nome — automação, CI e Claude Code na nuvem.
2. `~/.kbr/secrets.env`.

## Limites da proteção

O hook e as regras `deny` são **barreiras contra exposição acidental no transcript**, não uma
fronteira de segurança:

- Um script escrito na hora que abra o arquivo por dentro passa — é exatamente assim que os
  scripts dos plugins leem os segredos.
- Em repouso, o arquivo tem a mesma postura de `~/.aws/credentials`: protegido por permissão
  do sistema de arquivos, não criptografado.
- **Na dúvida, o hook nega — mesmo em prosa.** Em qualquer campo, inclusive o `command` do
  Bash, ele nega sempre que `.kbr` aparece como segmento de caminho completo, não importa o
  que vem antes. Isso vale também para uma **menção solta em texto**: uma mensagem de commit
  que só *cita* `~/.kbr`, ou um `echo` com a pasta no meio da frase, é negada do mesmo jeito
  que um comando que de fato lê o arquivo — não dá para distinguir os dois casos sem
  interpretar aspas de shell, e o hook deliberadamente não faz isso. Entre negar à toa uma
  frase (o usuário reformula) e deixar passar um comando que expõe o segredo de verdade, a
  escolha é negar. Pelo mesmo motivo, qualquer `command` do Bash que cite `secrets.env` por
  extenso também é negado, mesmo quando a grafia da pasta escapa do marcador acima (aspas no
  meio do nome, variável de shell, coringa).
- Um comando ofuscado — codificado em base64, por exemplo, ou de qualquer forma que não
  exiba o caminho como texto — passa: o hook não decodifica nem interpreta o shell.

A ameaça que isso trata é segredo vazando para o contexto, para log ou para o git — não um
atacante com acesso à máquina.

## Pré-requisitos

Python 3.10 ou superior no `PATH`. Nada de `pip install`.
