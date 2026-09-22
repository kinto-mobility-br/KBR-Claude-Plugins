# CLAUDE.md — KBR-Claude-Plugins

Marketplace de plugins do Claude Code da KINTO Brasil. Este repositório é ao mesmo
tempo o catálogo (`.claude-plugin/marketplace.json`) e o monorepo dos plugins (`plugins/`).

> ⚠️ **Repositório PÚBLICO desde 22/09/2026.** Foi aberto para que os plugins pudessem ser
> instalados por quem não tem acesso ao GitHub corporativo. Isso muda o peso das regras de
> segredo abaixo: um valor commitado por engano fica exposto no instante do push e permanece
> no histórico, em forks e em caches — **exige rotação, não apenas remoção**. Antes de publicar
> qualquer versão, rode a auditoria de segredos (procedimento em
> `projects/servicedesk-api/kb/draft/rb-auditar-segredos-plugins.md`, no workspace da KINTO).

Design aprovado em `docs/superpowers/specs/2026-09-13-fundacao-servicedesk-design.md`.

## Regras duras

- **PT-BR em tudo** — SKILL.md, mensagens de script, comentários, commits, README. Identificadores
  de código e termos técnicos (OAuth, refresh token, display_id) ficam no original.
- **Python ≥ 3.10, só biblioteca padrão.** Ninguém pode precisar de `pip install` para usar um plugin.
- **Todo script:** `def main() -> int` + `raise SystemExit(main())`.
- **Portável, Windows primeiro.** `pathlib` sempre; nunca barra fixa.
- **Plugin é autocontido.** Nenhum plugin lê arquivo de outro em tempo de execução.
  `shared/kbr_secrets.py` é a fonte única; as cópias em `plugins/*/scripts/` são geradas por
  `python scripts/sincronizar_shared.py`. **Nunca edite uma cópia** — a CI compara byte a byte.
- **Caminhos em skills sempre via `${CLAUDE_PLUGIN_ROOT}`.**
- **Segredo nunca é impresso** por script nenhum, nem em mensagem de erro.
- **Escrita no ServiceDesk só com `--confirmar`.**
- **Cuidado com `: ` na `description` de um SKILL.md.** A frontmatter é YAML: dois-pontos
  seguido de espaço dentro de um valor sem aspas quebra o parse, e o Claude Code carrega a
  skill com metadados vazios — ela simplesmente nunca dispara, sem erro visível em lugar
  nenhum. Prefira travessão. `claude plugin validate --strict` pega isso, e a CI roda esse
  comando; rode antes de commitar.
- **Nunca `git add -A`.** Nomeie os caminhos e confira `git status --short`.

## Comandos

```bash
python scripts/sincronizar_shared.py    # propaga shared/ para os plugins
python scripts/verificar_shared.py      # falha se alguma cópia divergiu
python scripts/testar.py                # roda os testes de todos os plugins
python scripts/validar.py               # claude plugin validate em tudo
python scripts/criar_tag.py <plugin>    # cria a tag <plugin>--v<versão>
```

`python -m unittest discover -s plugins` **não funciona**: as pastas dos plugins têm hífen no
nome e não podem ser pacotes Python. Use `scripts/testar.py`.

## Versionamento

Cada plugin tem `version` semver no próprio `plugin.json`. Publicar é criar a tag
`<plugin>--v<versão>` e dar push — é esse padrão que o Claude Code lê para detectar
atualização. Mudança em `shared/` obriga a subir a versão de todos os plugins que a vendorizam.
