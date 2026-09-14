---
name: query
description: Extrai chamados de toda a operação do ServiceDesk Plus da KINTO — todos os técnicos, não só os seus — filtrados por período, para um arquivo CSV local que abre no Excel. Diferente da skill sdp (que responde perguntas rápidas sobre os SEUS chamados em texto), esta gera um arquivo para quem vai analisar fora do chat. Use quando o usuário pedir "exportar chamados", "planilha de chamados", "relatório de chamados em CSV", "extrair dados do ServiceDesk", "dados para o dashboard do ServiceDesk", "quero uma listagem de todos os chamados abertos em 09/2026", "chamados de toda a operação", ou invocar /kbr-servicedesk:query.
---

# Query — extração de dados do ServiceDesk KINTO

Você gera um **arquivo**, não uma resposta de chat. O escopo é **toda a operação** — todos os
técnicos, não só quem está conversando com você.

## Regras duras (não violar)

- 📖 **Sempre leitura.** Este comando nunca grava no ServiceDesk — não existe flag de
  confirmação porque não existe nada a confirmar.
- 🚫 **Nunca ação em massa.** Se o pedido envolver mudar algo ("fecha todos os de setembro",
  "atualiza o status de todos os abertos"), explique que aqui só se **extrai** dado — mudar
  chamado é sempre pela skill `sdp`, opções 3/4/5, um de cada vez, com confirmação. Ofereça
  levar a pessoa para lá.
- 📂 **Sempre diga o caminho absoluto do arquivo**, no fim da resposta — é o campo `arquivo`
  da saída do comando.
- ⚠️ **Se vier `truncado: true`**, avise antes de declarar a extração completa: a busca bateu
  no teto interno de 10 mil chamados. Diga que o arquivo tem pelo menos as primeiras linhas
  coletadas, não a base inteira do período.
- 🔒 **Segredo nunca no chat.** Se faltar credencial, leve para a skill `sdp`, opção 6.
- 🇧🇷 Tudo em PT-BR, com acentuação correta.
- 👤 **Se o pedido for claramente só sobre os SEUS chamados** ("meus chamados de setembro",
  "os que eu resolvi este mês") — este comando não filtra por técnico, ele sempre traz toda
  a operação. Ou redirecione para a skill `sdp`, opção 7 (resposta em texto, sem arquivo,
  só dos seus chamados), ou rode a query mesmo assim e avise claramente, antes de entregar o
  arquivo, que ele contém os chamados de TODOS os técnicos, não só os da pessoa.

## Como chamar o script

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/sdp_api.py" query [--de AAAA-MM-DD --ate AAAA-MM-DD] [--campo-data created_time|resolved_time] [--status "<nome exato>" | --abertos] [--arquivo <caminho.csv>]
```

- `--de`/`--ate` vêm **juntos ou nenhum dos dois**. `--ate` é **exclusivo** — o dia seguinte
  ao último dia desejado. Sem os dois, a busca não filtra por data (é o caso da opção 5).
- `--campo-data` escolhe se o período é sobre quando o chamado foi **criado** (padrão) ou
  **resolvido**.
- `--status` e `--abertos` são mutuamente exclusivos: `--status "On Hold"` filtra por um
  status exato; `--abertos` traz tudo que ainda não é Resolved/Closed/Canceled. Sem nenhum
  dos dois, não filtra por status — traz tudo, inclusive já finalizado (é o padrão certo para
  dado histórico).
- `--arquivo` é opcional. Sem ele, o nome é `chamados_<de>_a_<ate>.csv` (ou `chamados.csv`
  sem período), gravado na pasta atual.

A saída é sempre JSON: `{"arquivo": "...", "linhas": N, "truncado": bool}`. Se vier
`{"erro": "..."}`, mostre o texto como está — já foi escrito em PT-BR — e siga a mesma tabela
de diagnóstico da skill `sdp` (menciona `/kbr-servicedesk:configurar` quando é credencial).

## Antes de calcular qualquer período: descubra a data de hoje

Nunca confie na sua própria noção de "hoje" para calcular "este mês"/"mês passado" — rode:

```bash
python -c "from datetime import date; print(date.today().isoformat())"
```

## O menu

```
🧮 QUERY — Extração de dados do ServiceDesk
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📅 1. Chamados criados este mês
📅 2. Chamados criados no mês passado
✅ 3. Chamados resolvidos este mês
✅ 4. Chamados resolvidos no mês passado
📂 5. Todos os chamados ainda abertos (toda a operação)
✍️ 6. Período personalizado — descreva o que você quer

🚪 0. Sair
```

| Opção | Comando |
|---|---|
| 1 | `query --de <dia 01 do mês corrente> --ate <dia 01 do mês seguinte>` |
| 2 | `query --de <dia 01 do mês anterior> --ate <dia 01 do mês corrente>` |
| 3 | `query --campo-data resolved_time --de <dia 01 do mês corrente> --ate <dia 01 do mês seguinte>` |
| 4 | `query --campo-data resolved_time --de <dia 01 do mês anterior> --ate <dia 01 do mês corrente>` |
| 5 | `query --abertos` |
| 6 | interpretado da fala — veja abaixo |

**Mês corrente/anterior:** a partir da data de hoje (seção acima). "Mês corrente" vai do dia
01 do mês de hoje até o dia 01 do mês seguinte (exclusivo). "Mês anterior" vai do dia 01 do mês
passado até o dia 01 do mês de hoje. Exemplo: hoje `2026-09-14` → este mês é
`--de 2026-09-01 --ate 2026-10-01`; mês passado é `--de 2026-08-01 --ate 2026-09-01`.

## Opção 6 — período personalizado

Aceita frases como "chamados abertos em 09/2026", "resolvidos entre 1º e 15 de agosto",
"tudo desde julho até hoje". Regras:

- Converta para `--de`/`--ate` em ISO, com `--ate` sempre **um dia depois** do último dia
  desejado (se a pessoa disse "até 15 de agosto", `--ate` é `2026-08-16`).
- Se a frase falar em "resolvido"/"fechado"/"concluído", use `--campo-data resolved_time`;
  se falar em "criado"/"aberto"/"registrado" (ou não especificar), use o padrão
  (`created_time`).
- Se a frase pedir só os que ainda estão em aberto, use `--abertos` em vez de um período —
  ou combine os dois se a pessoa quiser "abertos criados em setembro", por exemplo.
- **Nunca invente um filtro que a pessoa não pediu.** Se a frase for ambígua sobre o período
  ou o campo de data, pergunte antes de rodar — não adivinhe.

## Depois de gerar o arquivo

Diga, numa frase: quantas linhas (`linhas`), o caminho absoluto (`arquivo`), e se veio
`truncado: true`, o aviso de que a lista pode estar incompleta. Pergunte se a pessoa quer
gerar outra extração (volte ao menu) ou já terminou.
