# kbr-servicedesk

Gestor de chamados do ServiceDesk Plus Cloud da KINTO, dentro do Claude Code.

## Skills

- **`/kbr-servicedesk:sdp`** — o painel: lista seus chamados, mostra detalhe, adiciona nota,
  muda status e resolve. Nada é gravado sem você confirmar.
- **`/kbr-servicedesk:configurar`** — o passo a passo que te ensina a criar as próprias chaves
  de acesso, em 8 etapas. Feito para quem nunca ouviu falar de OAuth. Tem também uma visão
  geral, se você quiser só entender o que está envolvido antes de começar.

## Primeira vez

Abra `/kbr-servicedesk:sdp` e escolha a opção 6. O wizard leva uns 15 minutos e você precisa
de: acesso ao portal do ServiceDesk, um navegador e o Bloco de Notas.

Ao final você terá um **Self Client** individual na Zoho — uma chave só sua, que pode ser
revogada a qualquer momento sem afetar ninguém.

## O que ele guarda, e onde

| Onde | O quê |
|---|---|
| `~/.kbr/secrets.env` | `SDP_CLIENT_ID`, `SDP_CLIENT_SECRET`, `SDP_REFRESH_TOKEN` — protegidos pelo `kbr-core` |
| `~/.kbr/config.json` | seu nome e e-mail de técnico, e os endereços da API — não são segredo |
| `~/.kbr/cache/` | o token de acesso de 1 hora, renovado sozinho |

Nada disso entra em repositório nenhum.

## Escopos OAuth

O wizard manda marcar exatamente estes três, e nenhum a mais:

```
SDPOnDemand.requests.READ,SDPOnDemand.requests.CREATE,SDPOnDemand.requests.UPDATE
```

`python scripts/sdp_api.py escopos` imprime a lista pronta para copiar.

## Pré-requisitos

Python 3.10 ou superior no `PATH` e o plugin `kbr-core` (instalado junto, por dependência).

## Fora de escopo nesta versão

Documentação local de chamados em `tasks/`, anexos, criação de chamado, e qualquer data center
da Zoho fora do americano.
