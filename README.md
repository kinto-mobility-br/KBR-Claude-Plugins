# KBR-Claude-Plugins

Marketplace privado de plugins do [Claude Code](https://claude.com/claude-code) da KINTO Brasil.

## Instalar

Dentro do Claude Code, uma vez por máquina:

```
/plugin marketplace add kinto-mobility-br/KBR-Claude-Plugins
```

Depois, o que você for usar:

```
/plugin install kbr-servicedesk@kinto-brasil
```

O repositório é privado: a instalação usa as mesmas credenciais git que você já usa para
clonar os repositórios da KINTO.

## Catálogo

| Plugin | O que faz | Skills |
|---|---|---|
| `kbr-core` | Segredos por usuário em `~/.kbr/secrets.env` e a proteção que impede o modelo de lê-los. Instalado junto com os outros, por dependência. | `/kbr-core:secrets` |
| `kbr-servicedesk` | Gestor de chamados do ServiceDesk Plus por menu, com wizard de configuração para quem nunca mexeu com OAuth. | `/kbr-servicedesk:sdp`, `/kbr-servicedesk:configurar` |

## Pré-requisitos por máquina

- Claude Code
- **Python 3.10 ou superior no `PATH`** — os plugins usam só a biblioteca padrão, não há
  `pip install`
- Acesso git a este repositório

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
    "kbr-core@kinto-brasil": true,
    "kbr-servicedesk@kinto-brasil": true
  }
}
```

Quem abrir o repositório recebe a sugestão de instalar.

## Atualizar

```
/plugin marketplace update kinto-brasil
/plugin update kbr-servicedesk@kinto-brasil
```

## Desenvolver

Leia o [`CLAUDE.md`](CLAUDE.md). Em resumo:

```bash
python scripts/sincronizar_shared.py    # depois de editar shared/
python scripts/testar.py                # testes de todos os plugins
python scripts/validar.py               # claude plugin validate
python scripts/criar_tag.py kbr-core --push   # publicar uma versão
```
