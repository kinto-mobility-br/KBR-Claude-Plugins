---
name: secrets
description: Gerencia o arquivo de segredos pessoal em ~/.kbr/secrets.env — cria, confere o que está preenchido, abre para edição e ativa a proteção contra leitura pelo modelo. Use quando o usuário pedir "configurar secrets", "configurar credenciais", "meus segredos", "status dos segredos", disser "não consigo acessar" algo que devia funcionar (causa comum: credencial ausente ou vencida), quando um plugin KINTO reclamar de credencial ausente, ou antes de qualquer tarefa que precise de token de API dos plugins KINTO.
---

# Segredos dos plugins KINTO

O arquivo `~/.kbr/secrets.env` guarda os tokens de API que os plugins KINTO usam. Ele fica
**fora de qualquer repositório** e é lido **só pelos scripts**, por dentro — o valor nunca
passa pela conversa.

## Regras duras

- 🔒 **Nunca peça um valor de segredo no chat.** Nem para "conferir", nem para "testar".
  O caminho é sempre `editar`: o usuário cola no editor dele.
- 🙈 **Nunca tente ler o arquivo.** O hook do próprio plugin nega, e com razão. Para saber o
  que está preenchido, use `status`.
- ⚠️ **Se o usuário colar um segredo no chat por conta própria**, avise que aquele valor está
  no transcript e que o certo é **gerar outro** no serviço de origem, e então gravá-lo pelo
  `editar`. Não finja que não viu.
- 🇧🇷 Tudo em PT-BR.

## Comandos

Rode sempre pelo Python do próprio plugin:

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/kbr_secrets.py" <subcomando>
```

| O usuário quer | Subcomando | Depois |
|---|---|---|
| Começar do zero | `init` | **Pergunte** se pode ativar a proteção; só então rode `proteger` |
| Saber o que falta | `status` | Explique numa frase por chave o que está pendente |
| Preencher ou trocar um valor | `editar` | "cole os valores depois do `=`, salve, feche e me avise" |
| Ativar a proteção | `proteger` | Confirme que as regras entraram no settings |

`status` aceita `--plugin <nome>` para filtrar as chaves de um plugin só.

## Fluxo do `init`

1. Rode `init`. Ele cria a pasta, o arquivo com o cabeçalho e o cache, e restringe tudo ao
   usuário.
2. Mostre o que foi criado.
3. **Pergunte**: "quer que eu grave também a regra que impede qualquer sessão do Claude Code
   de ler esse arquivo? (s/n)". Só rode `proteger` depois do "s".

## Uso avançado — 1Password

Quem tem o 1Password CLI pode escrever a **referência** no lugar do valor:

```dotenv
SDP_CLIENT_ID=op://Cofre/Nome do item/campo
```

O script resolve na hora com `op read`. Referência não é segredo, então você **pode** ajudar a
montá-la a partir do nome do cofre, do item e do campo, se a pessoa pedir. Quem não tem o
1Password não precisa saber que isso existe — não ofereça espontaneamente.

## Quando algo dá errado

| Sintoma | O que dizer |
|---|---|
| `status` diz "vazia" | Falta preencher; ofereça o `editar` |
| `status` diz "1Password CLI: NÃO encontrado" | A chave aponta para o cofre mas o `op` não está instalado nesta máquina |
| `status` avisa sobre permissões | Rode o `init` de novo, que reaplica a restrição |
| `status` diz "proteção ausente" | Ofereça o `proteger` |
