# Configurar o acesso ao ServiceDesk — passo a passo detalhado

Este documento descreve **o que acontece por baixo** do assistente
`/kbr-servicedesk:configurar`, para quem quer entender o processo, conferir o que foi feito, ou
executar manualmente.

> 💡 **Na primeira vez, use o assistente.** Ele conduz os 19 passos, explica cada um, executa o
> que dá para executar e protege você de esquecer algo. Este documento é a referência para quem
> quer saber o porquê — ou para diagnosticar quando algo não funcionou.

## O que você vai criar

Uma **chave de acesso individual** para a API do ServiceDesk Plus Cloud. Ela é:

- **sua** — criada com o seu login, herda as suas permissões, e pode ser cancelada sem afetar
  ninguém
- **só para programas** — não substitui nem expõe a sua senha
- **guardada na sua máquina** — num arquivo pessoal, fora de qualquer repositório

O ServiceDesk Plus Cloud é um produto da ManageEngine que usa **OAuth 2.0 da Zoho** para a API.
Por isso a configuração acontece no console da Zoho, e não no portal do ServiceDesk.

## As duas camadas de permissão

Guarde esta ideia — ela explica a maior parte dos erros inesperados:

| Camada | O que controla | Onde se configura |
|---|---|---|
| **Escopo OAuth** | o que a chave *pode* fazer | console da Zoho, ao criar a chave |
| **Permissão do técnico** | o que *você* pode fazer no ServiceDesk | administração do ServiceDesk |

**As duas precisam estar certas.** Um escopo liberado não adianta se o seu usuário não tem a
permissão correspondente no ServiceDesk — e vice-versa. Diante de um erro de permissão
inesperado, confira as duas, não só a chave.

## Antes de começar

- Login do **portal do ServiceDesk** da sua organização
- Acesso ao **[api-console.zoho.com](https://api-console.zoho.com)** com o mesmo login
- **Python 3.10+** no `PATH`
- O plugin instalado e o Claude Code **reaberto** depois da instalação

## Passo a passo

### 1. Confirmar o data center

Todo endereço da Zoho varia por data center (US, EU, IN, AU, JP, CN). Os plugins assumem o
data center **americano**:

| Serviço | Endereço |
|---|---|
| Console de API | `https://api-console.zoho.com` |
| Endpoint de token | `https://accounts.zoho.com/oauth/v2/token` |
| API do ServiceDesk | `https://sdpondemand.manageengine.com/api/v3/` |

> ⚠️ Se a sua organização estiver em outro data center, **os três endereços mudam juntos** —
> não é só o console. Esta versão dos plugins não cobre esse caso.

### 2. Criar o Self Client na Zoho

1. Entre em **[api-console.zoho.com](https://api-console.zoho.com)** com o mesmo login do
   ServiceDesk
2. Escolha **ADD CLIENT** e o tipo **Self Client**

**Por que Self Client:** é o tipo feito para quem vai usar a própria chave, sem tela de
consentimento para terceiros. Não é um aplicativo que outras pessoas autorizam — é um crachá
para os seus próprios scripts.

3. Ao criar, a Zoho mostra **Client ID** e **Client Secret**. Deixe essa aba aberta: ela é usada
   até o passo 5.

### 3. Guardar as duas chaves

O `kbr-core` guarda segredos num arquivo pessoal, na sua pasta de usuário, fora de qualquer
repositório. Para abrir:

```
/kbr-core:secrets editar
```

Registre `SDP_CLIENT_ID` e `SDP_CLIENT_SECRET` com os valores da Zoho.

> 🔒 **Cole os valores direto no editor, nunca na conversa.** Um segredo digitado no chat fica
> registrado ali; o certo, se acontecer, é apagar o Self Client na Zoho e recomeçar.

Para conferir o que está preenchido **sem expor nenhum valor**:

```
/kbr-core:secrets status
```

### 4. Descobrir os escopos necessários

```
python scripts/sdp_api.py escopos
```

Imprime a lista pronta para copiar. Os plugins usam três:

```
SDPOnDemand.requests.READ,SDPOnDemand.requests.CREATE,SDPOnDemand.requests.UPDATE
```

> 🔑 **Note o que não está na lista:** `SDPOnDemand.requests.DELETE` é omitido **de propósito**,
> para que a integração não possa apagar chamados. O preço é não conseguir remover anexos pela
> API — o mesmo escopo governa as duas coisas. Remoção de anexo fica pelo portal.

Sub-tasks de um chamado já funcionam com o escopo `requests`; não é preciso pedir
`SDPOnDemand.tasks` à parte.

### 5. Gerar o código de autorização

Na aba da Zoho, no seu Self Client:

1. Aba **Generate Code**
2. Cole a lista de escopos do passo anterior
3. Escolha a duração (10 minutos basta) e descreva o uso
4. Selecione o portal do ServiceDesk quando pedido
5. **Copie o código gerado**

> ⏱️ O código é **de uso único e expira rápido**. Se demorar, gere outro — não há problema em
> repetir.

### 6. Trocar o código pelo acesso permanente

Guarde o código como `SDP_GRANT_CODE` (mesmo caminho do passo 3) e rode:

```
python scripts/sdp_api.py autorizar
```

O comando troca o código por um **refresh token**, grava-o e **apaga o código**, que já não serve
para nada.

**O que é o refresh token:** a credencial de longa duração. Ele não é usado direto nas chamadas —
serve para obter um *access token* temporário (1 hora) a cada uso. Vale **até ser revogado ou até
os escopos mudarem**.

> 🔑 **Escopo é carimbado no token.** Se um dia precisar de um escopo novo, não existe endpoint
> para ampliar um token já emitido: é refazer o *Generate Code* com a lista atualizada e trocar
> por um refresh token novo.

### 7. Informar quem você é

Alguns comandos precisam saber o seu e-mail de técnico para filtrar os seus chamados e para
excluir você mesmo da lista de destinatários ao responder.

O assistente pergunta isso no passo 017.

### 8. Testar

```
python scripts/sdp_api.py testar
```

Deve responder com o seu nome, o e-mail e a contagem de chamados abertos. Se responder, está
pronto.

## Quando algo dá errado

| Mensagem | O que costuma ser |
|---|---|
| Fala em Client ID ou Client Secret incorretos | Valor colado errado no passo 3 — confira os dois |
| Fala em escopo ou permissão | Falta escopo (passo 4) **ou** falta permissão do seu usuário no ServiceDesk |
| "O acesso foi revogado ou o token venceu" | Refresh token inválido — refaça os passos 5 e 6 |
| Não consegue falar com o ServiceDesk | Rede ou VPN |

> ⚠️ **Erro de autenticação nunca se resolve tentando de novo.** Se a mensagem fala em acesso,
> token, escopo, Client ID ou Client Secret, o caminho é rever a configuração — repetir o comando
> só repete o erro.

Para retomar do ponto em que parou:

```
/kbr-servicedesk:configurar
```

Ele detecta o que já está feito e continua dali.

## Segurança

- **Nenhum segredo entra neste repositório.** Os valores ficam no seu arquivo pessoal, e um hook
  do `kbr-core` impede que o modelo leia esse arquivo
- **Nenhum script imprime segredo**, nem em mensagem de erro
- **Nenhuma escrita no ServiceDesk acontece sem `--confirmar`** — todos os comandos que gravam
  simulam primeiro e mostram o que fariam
- O refresh token é **permanente até ser revogado**: trate-o com a mesma seriedade de uma senha
