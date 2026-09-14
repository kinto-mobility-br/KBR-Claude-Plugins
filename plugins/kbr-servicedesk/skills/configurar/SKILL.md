---
name: configurar
description: Wizard passo a passo que configura o acesso de uma pessoa ao ServiceDesk Plus da KINTO — cria o Self Client na Zoho, guarda as credenciais no arquivo de segredos e testa a conexão. Escrito para quem nunca ouviu falar de OAuth, terminal ou Python. Use quando o usuário pedir "configurar o ServiceDesk", "não consigo acessar os chamados", disser que apareceu um erro de credencial ou autenticação, escolher a opção 6 do gestor de chamados, ou quando qualquer comando do ServiceDesk reclamar de credencial ausente, inválida ou revogada.
---

# Wizard — configurar o acesso ao ServiceDesk

Quem está do outro lado **usa o ServiceDesk pelo navegador e nunca mexeu com OAuth, terminal ou
Python**. Sabe abrir um site, copiar e colar, e abrir o Bloco de Notas. Escreva para essa pessoa.

## Regras duras

- 🐢 **Um passo por turno.** Nunca despeje dois passos de uma vez.
- 🔒 **Nunca peça um segredo no chat.** Client ID, Client Secret e código de autorização vão
  **direto para o arquivo**, pelo editor. Se a pessoa colar um no chat mesmo assim: avise que
  aquele valor ficou registrado na conversa, e que o certo é **apagar o Self Client na Zoho e
  criar outro**. Não siga fingindo que não viu.
- 🔑 **1Password é opt-in, nunca oferecido, e nunca para o código de autorização.** Só fale
  nisso se a pessoa perguntar. Quando perguntar: `SDP_CLIENT_ID` e `SDP_CLIENT_SECRET` podem
  virar uma referência `op://...` no arquivo. `SDP_GRANT_CODE` **nunca** — o passo 6 apaga esse
  campo escrevendo um valor vazio por cima da linha, porque o código é de uso único; se a linha
  fosse uma referência do 1Password, isso destruiria a referência em vez de só limpar o valor.
- 🗣️ **Sem jargão sem explicar.** "OAuth", "Self Client", "Client ID", "refresh token" são os
  nomes reais dos botões e campos no site da Zoho — use-os quando for apontar para a tela, mas
  explique em uma frase simples na primeira vez ("chave de acesso individual", "código
  temporário", "acesso que não expira"). Nunca jogue o termo sem contexto.
- ✅ **Verifique cada passo antes de avançar.** Nunca diga "deve ter funcionado" — rode o
  comando de verificação e leia o que ele devolveu.
- 🔁 **Rodar de novo não estraga nada.** Ao iniciar, rode a verificação do Passo 1 e pule para o
  primeiro passo pendente, avisando o que já estava pronto (tabela de retomada no Passo 1).
- 🇧🇷 Tudo em PT-BR, com acentuação correta.

## O mini-menu

Cada turno termina assim:

```
1. Feito, próximo passo   2. Explicar de novo   3. Estou com erro   0. Sair (dá para voltar depois)
```

- **2** — reescreva o passo de outro jeito, mais devagar, com outra analogia.
- **3** — abra o diagnóstico do passo atual (tabela no fim desta skill) e **volte ao mesmo passo**.
- **0** — diga onde parou e que `/kbr-servicedesk:configurar` retoma daqui.

## Comandos

Os dois scripts vivem dentro **deste mesmo plugin** — o wizard nunca precisa ler nem executar
nada de dentro da pasta de outro plugin:

```bash
# segredos — kbr_secrets.py vendorizado aqui, cópia idêntica ao do kbr-core
python "${CLAUDE_PLUGIN_ROOT}/scripts/kbr_secrets.py" <init|registrar|status|editar|proteger>
# API do ServiceDesk — deste plugin
python "${CLAUDE_PLUGIN_ROOT}/scripts/sdp_api.py" <escopos|autorizar|testar>
```

Formatos de saída são diferentes entre os dois scripts:

- `sdp_api.py` sempre imprime **JSON**. Erro vem como `{"erro": "..."}` e a saída sai 1 —
  **mostre esse texto como veio**, ele já foi escrito em PT-BR para esta pessoa, nunca reescreva.
- `kbr_secrets.py` imprime **texto simples**, uma linha por informação (não é JSON). `status`
  sai com código 1 sempre que alguma chave ainda está vazia ou a proteção está ausente — isso é
  **normal** até o Passo 8, não é um erro para reagir. O que importa é ler o texto.

---

## Passo 1 — Ver se a máquina está pronta, e por onde retomar

**Diga:** antes de tudo vou conferir se o computador tem o que precisa. Isso é rápido e você
não faz nada agora.

**Execute:**
```bash
python --version
python "${CLAUDE_PLUGIN_ROOT}/scripts/kbr_secrets.py" status --plugin kbr-servicedesk
```

- Python 3.10 ou maior: siga.
- Python ausente ou antigo: **pare** e ensine a instalar pela Microsoft Store (procure
  "Python 3.12", botão Obter). Depois peça para **fechar e reabrir o Claude Code** e rodar o
  wizard de novo.

**Use a saída do `status` para decidir onde retomar** (leia o texto, não espere JSON):

| O que o `status` mostra | Retome no |
|---|---|
| "o arquivo de segredos ainda não existe" | Passo 2 (primeira vez, ainda não viu a explicação) |
| Arquivo existe, mas nenhuma chave `SDP_*` aparece | Passo 3 |
| `SDP_CLIENT_ID` ou `SDP_CLIENT_SECRET` vazia | Passo 4 |
| As duas acima preenchidas, `SDP_GRANT_CODE` vazia | Passo 5 |
| `SDP_GRANT_CODE` preenchida, `SDP_REFRESH_TOKEN` vazia | Passo 6 |
| `SDP_REFRESH_TOKEN` preenchida | Passo 7 — mas confira o nome antes, logo abaixo |
| Tudo preenchido e "proteção ... ativa" | Já está pronto — rode `testar` para confirmar e ofereça sair |

O `status` só enxerga os segredos, nunca o nome do técnico. Quando o `SDP_REFRESH_TOKEN` já
estiver preenchido, confira se o nome já foi gravado antes de repetir o Passo 7:

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/sdp_api.py" testar
```

- Respondeu com o nome do técnico: o Passo 7 já foi feito. **Vá direto ao Passo 8.**
- Disse "Ainda não sei quem é o técnico": faça o Passo 7.
- Qualquer outro erro: leve ao diagnóstico do Passo 7.

Se algo já estava pronto, **diga isso antes de seguir** ("você já tinha o Client ID e o Client
Secret gravados, vamos direto para gerar o código").

**Confirme também** que a pessoa consegue entrar no portal do ServiceDesk pelo navegador. Sem
isso, nada adiante.

## Passo 2 — Entender o que vai acontecer

Sem comando nenhum. Explique, nessa ordem:

1. O ServiceDesk exige uma **chave de acesso individual** para programas — é diferente da sua
   senha, e serve só para esta máquina. O nome técnico dela é **OAuth**; você não precisa saber
   o que isso significa, só que é assim que programas se identificam sem usar sua senha.
2. Vamos criar essa chave no site da Zoho, que é a empresa que hospeda o ServiceDesk.
3. A chave fica guardada **num arquivo seu**, numa pasta protegida do seu usuário. Eu não
   consigo ler esse arquivo; os programas leem por dentro.
4. **Nada de secreto vai ser digitado aqui na conversa.** Você cola tudo no Bloco de Notas.
5. Se um dia quiser cancelar, é só apagar a chave no site da Zoho. Não afeta mais ninguém.

Pergunte se ficou claro antes de seguir.

## Passo 3 — Criar o arquivo de segredos

**Execute:**
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/kbr_secrets.py" init
python "${CLAUDE_PLUGIN_ROOT}/scripts/kbr_secrets.py" registrar --plugin kbr-servicedesk --chaves SDP_CLIENT_ID,SDP_CLIENT_SECRET,SDP_GRANT_CODE,SDP_REFRESH_TOKEN
```

Rodar de novo não faz mal: `registrar` só acrescenta o que falta e nunca toca em valor já
preenchido.

**Abra o guia**, se existir: `${CLAUDE_PLUGIN_ROOT}/guia/index.html` tem a foto de cada tela dos
próximos passos. Confira se o arquivo existe antes de indicá-lo. Se não existir ainda, **não
trate isso como problema** — siga só pelo texto, com a mesma qualidade de instrução.

**Verifique:**
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/kbr_secrets.py" status --plugin kbr-servicedesk
```
deve listar as quatro chaves como vazias.

## Passo 4 — Criar a chave no site da Zoho

**Diga o que fazer, nesta ordem** (figuras 4.1 a 4.4 do guia, se existir):

1. Abra **https://api-console.zoho.com** e entre com o mesmo login do ServiceDesk. Esse é o
   console **americano** — importante para mais tarde, não use `.eu` nem `.in`.
2. Clique em **ADD CLIENT**.
3. Escolha o tipo **Self Client** — é o terceiro cartão. É a opção pensada para quem vai usar a
   própria chave sozinho, sem outra pessoa aprovar. Confirme em **CREATE**.
4. Aparecem duas linhas longas: **Client ID** e **Client Secret**.

**Execute:** `editar` — isso abre o arquivo no Bloco de Notas.
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/kbr_secrets.py" editar
```

**Peça:** cole o Client ID depois de `SDP_CLIENT_ID=` e o Client Secret depois de
`SDP_CLIENT_SECRET=`, sem espaço antes nem depois do `=`. Salve (Ctrl+S) e feche.

⚠️ **Deixe a aba da Zoho aberta**, ela é usada no passo seguinte.

**Verifique:**
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/kbr_secrets.py" status --plugin kbr-servicedesk
```
deve mostrar `SDP_CLIENT_ID` e `SDP_CLIENT_SECRET` como preenchidas.

## Passo 5 — Gerar o código temporário

**Execute primeiro:**
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/sdp_api.py" escopos
```
e mostre o campo `escopos_em_uma_linha` da resposta — é a linha única de permissões para copiar.

**Diga o que fazer** (figuras 5.1 e 5.2, se o guia existir):

1. Na mesma tela da Zoho, abra a aba **Generate Code**.
2. Em **Scope**, cole a linha de permissões que acabei de mostrar.
3. Em **Time Duration**, escolha **10 minutes**.
4. Em **Scope Description**, escreva qualquer coisa, por exemplo "Claude Code KINTO".
5. **CREATE** → escolha seu portal se ele perguntar → copie o código que aparece.

⏱️ **Avise no instante em que o código aparecer:** ele vale **10 minutos** a partir de agora.
Se demorar mais que isso, é só gerar outro — não estraga nada.

**Execute:** `editar`. **Peça:** cole em `SDP_GRANT_CODE=`, salve e feche.

⚠️ **Aqui vai o código em si, nunca uma referência `op://`.** Mesmo que a pessoa use 1Password
e as outras chaves apontem para o cofre, esta não pode — o passo 6 apaga o código depois de
usá-lo, e apagaria a referência junto. Se ela colar uma referência, peça para trocar pelo
código antes de seguir.

**Verifique:**
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/kbr_secrets.py" status --plugin kbr-servicedesk
```
mostra `SDP_GRANT_CODE` preenchida.

## Passo 6 — Trocar o código pelo acesso permanente

**Diga:** agora eu troco esse código temporário por um acesso que não expira (o nome técnico é
**refresh token** — você não precisa lembrar disso). Você não faz nada.

**Execute:**
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/sdp_api.py" autorizar
```

- Sucesso: o refresh token foi gravado e o código temporário apagado (ele é de uso único).
- Erro: **mostre o texto do erro como veio** — ele já explica o que fazer — e volte ao passo
  indicado na tabela de diagnóstico.

**Verifique:**
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/kbr_secrets.py" status --plugin kbr-servicedesk
```
mostra `SDP_REFRESH_TOKEN` preenchida e `SDP_GRANT_CODE` vazia.

## Passo 7 — Dizer quem você é, e testar

**Pergunte:** seu nome completo **exatamente como aparece no ServiceDesk** (é assim que os
chamados são procurados — uma letra diferente já conta como outra pessoa) e seu e-mail
corporativo. Isso não é segredo, pode digitar aqui. Se a pessoa não tiver certeza da grafia
exata, sugira conferir no próprio perfil do ServiceDesk ou num chamado antigo que ela tenha
aberto.

**Execute** — não edite `~/.kbr/config.json` à mão nem peça para a pessoa abrir esse arquivo:
ele também guarda a configuração de outros plugins KINTO, e reescrevê-lo de fora pode apagar o
que não é seu. Use a mesma função que os scripts já usam para gravar só a parte deste plugin,
preservando o resto:
```bash
python -c "import sys; sys.path.insert(0, sys.argv[1]); import sdp_api; sdp_api.gravar_config({'tecnico_nome': sys.argv[2], 'tecnico_email': sys.argv[3]}); print('nome e e-mail gravados')" "${CLAUDE_PLUGIN_ROOT}/scripts" "<nome completo>" "<e-mail>"
```
(troque `<nome completo>` e `<e-mail>` pelos valores que a pessoa informou — eles não são
segredo, podem ir literalmente no comando).

Depois rode:
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/sdp_api.py" testar
```

- Sucesso: monte a frase a partir do JSON — "Conectado como **<tecnico>**. Você tem
  **<chamados_abertos>** chamados abertos." Se `truncado` vier `true` (raríssimo), diga "pelo
  menos N" em vez do número exato.
- Zero chamados **não** é erro: a conexão funcionou.
- "Ainda não sei quem é o técnico": o nome não foi gravado; refaça o comando acima.
- Nome diferente do cadastrado no ServiceDesk: `testar` conecta mas conta zero. Se a pessoa
  esperava ter chamados, peça para conferir a grafia exata no portal e repita o comando acima
  com o nome corrigido.

## Passo 8 — Proteger e encerrar

**Execute:**
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/kbr_secrets.py" status --plugin kbr-servicedesk
```
Se a proteção estiver ausente, **pergunte** se pode ativá-la e explique em uma frase: é uma
regra que impede qualquer sessão do Claude Code de abrir o arquivo de segredos. Só depois do
"sim", rode:
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/kbr_secrets.py" proteger
```

**Feche com um resumo:**

- o que ficou pronto (chave criada, acesso gravado, conexão testada, proteção ativa);
- como usar daqui pra frente: `/kbr-servicedesk:sdp`;
- que para trocar de credencial é só rodar este wizard de novo;
- que a chave é individual e pode ser revogada no site da Zoho quando quiser.

---

## Diagnóstico — "estou com erro"

| Passo | Sintoma | Resposta |
|---|---|---|
| 1 | `python` não é reconhecido | Instale pela Microsoft Store ("Python 3.12", botão Obter) e **reabra o Claude Code** |
| 1 | Python 3.9 ou menor | Instale a versão nova pela Store; as duas convivem |
| 4 | Não acho o **ADD CLIENT** | Confira se entrou em api-console.zoho.com, não no portal do ServiceDesk |
| 4 | Só aparece Client ID | Clique no olho ao lado do Client Secret para revelá-lo |
| 4 | `status` diz vazia depois de colar | O arquivo não foi salvo, ou colou antes do `=`. Rode `editar` de novo |
| 5 | A aba Generate Code não existe | Ela só aparece em cliente do tipo Self Client. Refaça o passo 4 |
| 5 | "Invalid Scope" ao criar | Algum espaço ou quebra entrou na linha colada. Copie de novo com `escopos` |
| 5 | Pediu para escolher o portal | Normal. Escolha o portal da KINTO |
| 6 | "O código de autorização expirou ou já foi usado" | Volte ao passo 5 e gere outro; ele vale 10 minutos |
| 6 | "Client ID ou Client Secret incorretos" | Volte ao passo 4; confira se copiou os dois inteiros, sem espaço antes/depois |
| 6 | O erro menciona console de outro país (`.eu`, `.in`) | O cliente foi criado fora do console americano. Apague e recrie em api-console.zoho.com (passo 4) |
| 6 | "O cliente não tem os escopos necessários" | Volte ao passo 5 e gere um novo código com a lista completa de `escopos` |
| 6 | "... não devolveu um refresh token" | Gere o código de novo no passo 5; confira se o console não limitou o acesso |
| 7 | Conecta mas conta zero | Ou não há chamados abertos, ou o nome está escrito diferente do portal — confira a grafia exata |
| 7 | "Ainda não sei quem é o técnico" | O nome não foi gravado no passo 7; rode o comando de gravação de novo |
| 7 | "O acesso foi revogado ou o token venceu" | O acesso foi revogado na Zoho (o Self Client pode continuar existindo). Refaça os passos 5 e 6 |
| 6 ou 7 | "O acesso foi revogado no 1Password ou na Zoho" | Mesma coisa dita pela Zoho em vez do ServiceDesk. Refaça os passos 5 e 6 |
| 7 | "O cliente não tem permissão para esta operação" | Faltou algum escopo. Refaça os passos 5 e 6 com a lista completa de `escopos` |
| qualquer | "Não consegui falar com o ServiceDesk" | Rede ou VPN. Tente de novo em um minuto |
| qualquer | "... não parece ter sido o ServiceDesk quem respondeu" | Proxy ou portal cativo na frente da rede. Confira a VPN e tente de novo |
