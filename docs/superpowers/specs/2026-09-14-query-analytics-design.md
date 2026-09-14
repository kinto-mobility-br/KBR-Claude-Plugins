# Spec de design — `/kbr-servicedesk:query`, extração de dados para analytics

**Data:** 2026-09-14
**Status:** rascunho para revisão
**Repositório:** `kinto-mobility-br/KBR-Claude-Plugins` (privado)
**Depende de:** `kbr-servicedesk` v0.3.1 (já publicado — API client, skill `sdp`, wizard `configurar`)

---

## 1. Objetivo

Dar à KINTO uma forma de extrair dados do ServiceDesk Plus para alimentar análise e dashboards,
sem escrever um pipeline novo. A skill `sdp` já existente responde perguntas pontuais sobre os
**próprios** chamados de um técnico, na hora, em texto. Esta skill é outra coisa: extrai um
**arquivo** com dados de **toda a operação**, filtrado por período, para quem vai analisar fora
do chat — Excel, Power BI, o que for.

### Critérios de sucesso

1. `/kbr-servicedesk:query` pede um período (ou oferece uma das cinco opções prontas) e devolve
   um arquivo CSV com os chamados daquele período, de qualquer técnico.
2. O filtro por data acontece no **servidor** do ServiceDesk, não trazendo tudo para filtrar
   depois — importante porque a base já passa de 3.700 chamados e cresce todo dia.
3. Nenhuma credencial nova é necessária. A conta que já existe (Self Client individual, três
   escopos já concedidos) enxerga a operação inteira — confirmado ao vivo nesta sessão.
4. O arquivo abre direto no Excel, sem precisar instalar nada — mantendo a regra do repositório
   de nunca exigir `pip install`.

### Decisões já tomadas (brainstorming de 2026-09-14)

| Decisão | Escolha | Por quê |
|---|---|---|
| Escopo dos dados | Toda a operação, todos os técnicos | Confirmado ao vivo: a conta pessoal do Fábio já enxerga 3.714+ chamados de outras pessoas sem filtro de técnico — não precisa de perfil novo nem de aprovação da TI |
| Destino da extração | Arquivo local (CSV) sob demanda | Sem pipeline S3/Athena/Power BI nesta fase; a pessoa pede pelo chat e recebe o arquivo na hora |
| Formato do arquivo | CSV, UTF-8 | `.xlsx` de verdade exigiria biblioteca fora da padrão do Python, violando a regra do repositório; CSV abre nativamente no Excel |
| Onde vive | Skill nova dentro do `kbr-servicedesk`, não plugin à parte | Mesmo domínio; mas separada da skill `sdp`, porque o trabalho é outro (arquivo, não resposta de chat; toda a operação, não só os próprios chamados) |
| Nome | `/kbr-servicedesk:query` | Escolhido pelo Fábio |
| Alternativa considerada e descartada | Habilitar o ManageEngine Analytics Plus (produto de BI nativo, com dashboards prontos) | Real e mais barato em código, mas exige administrador do ServiceDesk habilitar "Advanced Analytics" e não há confirmação de custo — fica registrado como opção futura, fora desta spec |

---

## 2. Fatos verificados contra a API real (não documentação, não suposição)

Tudo nesta seção foi testado ao vivo, com a credencial já configurada, em 2026-09-14. Onde a
forma "óbvia" de ler a documentação e a forma que realmente funciona divergem, as duas estão
registradas — porque este projeto já foi mordido por essa distância antes.

### 2.1 Escopo dos dados

Uma busca em `/requests` **sem** o critério `technician.name` devolveu `total_count: 3714`,
com chamados de Felipe Juventude Moreira, Lucas Ferreira Rodrigues, Henrique Lavieri Facio —
nenhum deles o Fábio. Os três escopos OAuth já concedidos (`requests.READ/CREATE/UPDATE`) bastam;
a restrição por técnico que a skill `sdp` aplica é uma escolha de código, não um limite da conta.

### 2.2 Filtro por data — a forma que funciona, e a que não funciona

O campo é `created_time` (ou `resolved_time`, `due_by_time` — mesma mecânica), valor em
**timestamp Unix em milissegundos**, como string.

**Funciona** — uma única condição `between` com `values: [início, fim]`:
```json
{"field": "created_time", "condition": "between", "values": ["1756684800000", "1759276800000"]}
```
Testado: devolveu `total_count: 93`, todos os chamados realmente de setembro/2026.

> **Nota pós-implementação (2026-09-14):** os dois valores acima são meia-noite em **UTC**
> (`1756684800000` = 2025-09-01T00:00:00Z). Na revisão final desta fatia, o Fábio pediu que a
> fronteira do filtro fosse meia-noite em **horário de Brasília** (UTC-3 fixo) em vez de UTC,
> para que "setembro" no arquivo bata com "setembro" no calendário de quem pediu —
> `_data_para_ms` no código usa essa fronteira, não a desta seção. O *mecanismo* do `between`
> (validado aqui) continua o mesmo; só os valores numéricos mudam.

**NÃO funciona** — duas condições encadeadas com `logical_operator: "AND"` (`greater than` +
`less than`), a forma que a documentação sugere como alternativa e que pareceria mais óbvia de
implementar:
```json
[{"field": "created_time", "condition": "greater than", "value": "1756684800000"},
 {"field": "created_time", "condition": "less than", "value": "1759276800000",
  "logical_operator": "AND"}]
```
Testado: devolveu `total_count: 3715` — essencialmente a base inteira, sem filtro nenhum. A API
não recusa essa forma, não devolve erro, só ignora o encadeamento. **Se alguém no futuro "limpar"
o código para usar duas condições em vez de `between`, o filtro quebra em silêncio.**

**Regra desta spec: filtro de data é sempre uma única condição `between`.** Nunca duas
condições `greater than`/`less than` encadeadas.

### 2.3 Filtro por `resolved_time`

Mesma forma `between`, mesmo campo. Testado com setembro/2026: `total_count: 90`, e os cinco
primeiros resultados da amostra eram todos `status: Closed` — evidência de que o filtro compara
o valor real de `resolved_time` no servidor (chamados nunca resolvidos não aparecem), mesmo que
esse valor não venha na resposta por padrão (ver 2.4).

### 2.4 `fields_required` — como pedir colunas extras na listagem

O endpoint de listagem devolve por padrão um conjunto pequeno de campos. Pedir mais exige o
parâmetro `fields_required` dentro de `list_info`, uma lista de nomes de campo:

```json
{"list_info": {"row_count": 100, "search_criteria": [...],
               "fields_required": ["id", "display_id", "subject", "status", "requester",
                                   "technician", "group", "category", "urgency", "priority",
                                   "created_time", "resolved_time"]}}
```

Testado com `resolved_time`, `category`, `group`, `technician`, `urgency` — todos vieram
completos, com objeto `{"name": ..., "id": ...}` para campos de referência (categoria, grupo,
técnico) e `{"value": ..., "display_value": ...}` para campos de data. `priority` foi pedido e
não veio na amostra testada — consistente com o campo estar vazio nesses chamados específicos
(comum quando só urgência é usada); o código de extração precisa tratar qualquer campo pedido
como potencialmente ausente, do mesmo jeito que `campo()` já faz em `sdp_api.py` hoje.

### 2.5 Bug corrigido durante esta pesquisa, já publicado (v0.3.1)

`STATUS_FINAIS` usava `"Cancelled"` (grafia britânica). O ServiceDesk da KINTO usa `"Canceled"`
(grafia americana, coerente com o data center US da Zoho). Com a grafia errada, o filtro
`is not` da opção "Meus chamados abertos" **não dava erro e não excluía nada** — 335 chamados
cancelados apareciam como "abertos" (`total_count` 517 contra os 182 reais). Corrigido e
publicado separadamente desta spec, já que é bug em código existente, não parte deste desenho —
mas a query nova usa a constante já corrigida.

---

## 3. Arquitetura

```
Fábio: "chamados criados em setembro"
   │
   ▼
skill /kbr-servicedesk:query  (interpreta a linguagem natural, monta as datas)
   │
   ▼
python sdp_api.py query --de 2026-09-01 --ate 2026-10-01 [--campo-data ...] [--status ...] [--arquivo ...]
   │
   ├─ access_token() / chamar() — reaproveitados de sdp_api.py, sem mudança
   ├─ paginação com o mesmo teto de 10.000 já usado em listar()
   └─ escreve o CSV
   │
   ▼
"Gravei 93 chamados em chamados_2026-09.csv" — caminho absoluto, sempre
```

Nenhuma escrita no ServiceDesk. `query` só chama `GET`. Não existe `--confirmar` porque não
existe nada a confirmar.

## 4. O comando `query`

**Assinatura:**
```
sdp_api.py query --de AAAA-MM-DD --ate AAAA-MM-DD
                  [--campo-data created_time|resolved_time]   (padrão: created_time)
                  [--status "<nome exato>"]                    (padrão: sem filtro de status)
                  [--arquivo <caminho.csv>]                    (padrão: chamados_<de>_a_<ate>.csv na pasta atual)
```

`--de` e `--ate` são datas ISO simples (`AAAA-MM-DD`); o script converte para milissegundos e
monta o único critério `between` da seção 2.2. `--ate` é exclusivo (o dia seguinte ao último dia
desejado) — a skill calcula isso ao traduzir "setembro" para `--de 2026-09-01 --ate 2026-10-01`.

Ao contrário de `listar`, **`query` não filtra por técnico por padrão** — é para a operação
inteira. Também **não exclui status finais por padrão** — dado histórico para análise
normalmente quer justamente os resolvidos/fechados; quem quiser só os abertos usa a query pronta
5 (seção 5), que passa `--status` adequado.

**Colunas do CSV**, nesta ordem: `numero`, `assunto`, `solicitante`, `tecnico`, `grupo`,
`categoria`, `subcategoria`, `status`, `urgencia`, `prioridade`, `criado_em`, `resolvido_em`.
Igual ao resto do `sdp_api.py`, o número de exibição (`display_id`) é a única identificação do
chamado na saída — o id interno do SDP nunca aparece, nem no CSV.

**Paginação e teto:** mesma constante `LIMITE_PAGINAS` (100 páginas × 100 = 10.000 chamados) já
usada em `listar()`. Se bater no teto, o CSV é escrito do mesmo jeito com o que foi coletado, e
o comando avisa no JSON de retorno (`truncado: true`) — a skill repassa esse aviso antes de
declarar a extração completa.

**Saída do comando** (JSON, como todo o resto de `sdp_api.py`):
```json
{"arquivo": "C:\\...\\chamados_2026-09-01_a_2026-09-30.csv", "linhas": 93, "truncado": false}
```

## 5. A skill `/kbr-servicedesk:query`

Menu com as cinco queries prontas mais a porta livre, apresentado assim:

```
🧮 QUERY — Extração de dados do ServiceDesk
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📅 1. Chamados criados este mês
📅 2. Chamados criados no mês passado
✅ 3. Chamados resolvidos este mês
✅ 4. Chamados resolvidos no mês passado
📂 5. Todos os chamados ainda abertos (toda a operação)
✍️ 6. Período personalizado — descreva o que você quer
```

| Opção | `--campo-data` | Período | `--status` |
|---|---|---|---|
| 1 | `created_time` | mês corrente | — |
| 2 | `created_time` | mês anterior | — |
| 3 | `resolved_time` | mês corrente | — |
| 4 | `resolved_time` | mês anterior | — |
| 5 | — (sem filtro de data) | — | `is not` Resolved/Closed/Canceled (mesma lista de `STATUS_FINAIS`) |
| 6 | interpretado da fala da pessoa | interpretado da fala da pessoa | interpretado, se mencionado |

A opção 6 aceita frases como "chamados abertos em 09/2026", "resolvidos entre 1º e 15 de
agosto", "tudo desde julho até hoje". A skill converte para `--de`/`--ate` (e `--campo-data`
quando a frase falar em "resolvido"/"fechado" em vez de "aberto"/"criado") e roda o comando —
nunca inventa um filtro que a pessoa não pediu; se a frase for ambígua, pergunta antes de rodar.

**Regras duras da skill:**
- Sempre leitura. Um pedido de ação (mudar status, resolver) em cima do resultado é recusado e
  redirecionado à skill `sdp`, opções 3/4/5, chamado a chamado, com confirmação.
- Sempre diz o caminho final do arquivo, absoluto, no fim da resposta.
- Se `truncado: true` vier, avisa antes de declarar a extração completa.
- PT-BR em tudo.

## 6. Testes

Mesmo padrão de TDD com rede simulada do resto do repositório:

- O `between` é a única forma usada para monta o critério de data — teste que inspeciona o
  `search_criteria` da chamada e falha se aparecer `greater than`/`less than` para data.
- `--campo-data resolved_time` usa o campo certo no `search_criteria`.
- `fields_required` inclui todas as colunas do CSV.
- Query sem `--status`: não filtra por status. Com `--status`: filtra exatamente pelo valor
  passado.
- CSV escrito tem cabeçalho e uma linha por chamado, com as colunas na ordem da seção 4.
- Teto de 10.000: comportamento idêntico ao já testado em `listar()` — reaproveitar o padrão do
  teste existente, adaptado para `query`.
- Id interno nunca aparece no CSV nem no JSON de retorno.
- Nenhum comando de escrita (`PUT`/`POST`) é alcançável a partir de `query` — não há flag
  `--confirmar` porque não há chamada de escrita no código.

## 7. Fora de escopo desta fatia

- Pipeline S3/Athena/Power BI — pode vir depois, alimentado pelos mesmos CSVs se fizer sentido.
- Habilitar o ManageEngine Analytics Plus — decisão de produto/custo, não de código; fica
  registrada como alternativa a considerar, não implementada aqui.
- Exportação em `.xlsx` nativo — exigiria dependência fora da biblioteca padrão.
- Extração agendada/recorrente.
- Filtros além de data e status (categoria, grupo, urgência) — a porta livre (opção 6) cobre
  parte disso via interpretação, mas não há flag dedicada no comando ainda.
- Dashboards ou artifacts com gráficos — o entregável desta fatia é o arquivo, não a
  visualização.
