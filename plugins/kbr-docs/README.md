# kbr-docs

Gera documentação em HTML com o design system oficial da KINTO, dentro do Claude Code.

## Skills

- **`/kbr-docs:report-creator`** — descobre a marca do projeto (logo, cor, nome) na primeira
  vez e cria o `.docs-brand.yml` sozinho; nas vezes seguintes, gera direto a partir dele. Um
  documento único ou um conjunto inteiro (visão, arquitetura, operação...), sempre no mesmo
  template — header, sidebar, TOC, Front Matter como página própria, tema claro/escuro.

## Primeira vez num projeto

Abra `/kbr-docs:report-creator` e peça um documento qualquer — a skill percebe sozinha que
falta o `.docs-brand.yml`, descobre o que existe no repositório (logo, nome), confirma com
você o que não deu para descobrir sozinho, e já segue para gerar o documento.

## O que ele guarda, e onde

| Onde | O quê |
|---|---|
| `.docs-brand.yml`, na raiz do projeto documentado | identidade visual — logo, cor, nome, autoria. Não é segredo; versione. |
| `docs/<assunto>/` (ou o destino pedido) | os HTML gerados, com `assets/` copiado junto |

Nada disso entra em `kbr-docs` — cada projeto documentado guarda a própria identidade.

## Pré-requisitos

Python 3.10 ou superior no `PATH`. Nenhuma biblioteca externa é obrigatória — a leitura do
`.docs-brand.yml` usa um parser próprio, sem PyYAML. Pillow é **opcional**: sem ele, a
detecção automática de cor/luminância de logo em PNG (não em SVG) fica marcada como
sugestão a conferir, em vez de preenchida sozinha.

## Fora de escopo nesta versão

PDF, apresentações (PPTX — fica para um plugin/skill futuro, `presentation-creator`), e
`kb-doc-creator` (documentos `.md` padronizados tipo ADR/runbook — outra ferramenta, outro
propósito).
