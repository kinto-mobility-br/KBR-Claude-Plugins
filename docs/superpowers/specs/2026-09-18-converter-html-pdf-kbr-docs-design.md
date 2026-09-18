# Converter HTML → PDF no kbr-docs — Design

## 1. Contexto e motivação

O `gestor-chamados` (skill do workspace da KINTO Brasil, fora deste repositório) precisa anexar
relatórios ao ServiceDesk sempre em PDF — nunca em HTML, porque o portal do SDP baixa `.html`
como arquivo bruto em vez de pré-visualizar (achado no chamado #4845, já registrado na memória
`feedback_sdp_anexar_discovery_e_solucao`). Até agora, a conversão era feita manualmente por
Claude, dirigindo o Playwright desta sessão (`emulateMedia('print')` + `page.pdf(...)`) — funciona,
mas não é algo que um script consiga chamar sozinho, e não é reprodutível sem um agente no meio.

Esta fatia dá ao `kbr-docs` um script de conversão HTML→PDF autocontido (sem depender de
Playwright nem de nenhuma dependência Python nova), que qualquer automação — inclusive o
`gestor-chamados`, que não é um plugin e não tem acesso a `${CLAUDE_PLUGIN_ROOT}` — consegue
chamar diretamente.

## 2. Decisões

| Decisão | Escolha |
|---|---|
| Mecanismo de conversão | `subprocess` chamando um navegador Chromium **já instalado** na máquina (`--headless --print-to-pdf`), nunca Playwright/pip install |
| Onde entra no plugin | Script novo dentro da skill `report-creator` já existente (`scripts/converter_pdf.py`), não uma skill nova |
| Escopo da conversão | Um arquivo HTML por vez — pasta/lote fica fora desta fatia (YAGNI) |
| Ligação do lado do `gestor-chamados` | Fora do plano de implementação do plugin — feita depois, manualmente, como edição de texto no `SKILL.md` daquela skill (que fica noutro repositório) |
| Atualização da memória `feedback_sdp_anexar_discovery_e_solucao` | Idem — feita depois, apontando pro script novo em vez da receita manual de Playwright |

## 3. Interface do script

```bash
python converter_pdf.py <entrada.html> [saida.pdf]
```

- `entrada.html`: caminho pro arquivo HTML local. Obrigatório.
- `saida.pdf`: caminho de saída. Opcional — se omitido, usa o mesmo nome de `entrada.html` com a
  extensão trocada pra `.pdf`, na mesma pasta.
- O script converte o arquivo passando `file:///<entrada-absoluta>` pro navegador — assets
  relativos (CSS, imagens, `assets/`) resolvem normalmente, do mesmo jeito que abrir o arquivo
  direto no navegador. Logos em base64 embutidos no próprio HTML (como o `gestor-chamados` já usa
  nos relatórios de solução) também funcionam sem nenhum tratamento especial.
- O `@media print` do design system entra em ação automaticamente — é o mesmo CSS que já esconde
  header/sidebar/TOC/botão de copiar ao imprimir pelo navegador (Ctrl+P); o script não precisa
  saber nada sobre isso, é comportamento nativo do PDF headless do Chromium.

`def main() -> int` + `raise SystemExit(main())`, como todo script deste repositório.

## 4. Descoberta do navegador

Função `achar_navegador() -> Path`, nesta ordem:

1. Variável de ambiente `KBR_DOCS_BROWSER` — caminho explícito, override manual (útil em máquina
   atípica ou em teste).
2. Lista de caminhos padrão do Windows, na ordem: Edge (`Program Files (x86)` depois
   `Program Files`), Chrome (mesma ordem). Esses dois já foram confirmados presentes na máquina do
   Fábio durante o brainstorming.
3. `shutil.which("msedge")`, `shutil.which("chrome")`, `shutil.which("chromium")`, nessa ordem —
   cobre quem tem o navegador só no PATH, ou uma instalação fora do padrão do Windows.

Se nada for achado, erro claro em PT-BR listando os caminhos/`shutil.which` tentados, saída 1 —
nunca um traceback cru.

## 5. Execução e tratamento de erro

```python
subprocess.run([
    str(navegador),
    "--headless",
    "--disable-gpu",
    f"--print-to-pdf={saida}",
    "--no-pdf-header-footer",
    f"file:///{entrada.resolve().as_posix()}",
], timeout=60, capture_output=True, text=True)
```

- Entrada inexistente → erro claro, saída 1, sem chamar o navegador.
- Navegador não achado → erro do §4, saída 1.
- Processo do navegador falha (código ≠ 0) OU termina OK mas o PDF não nasceu no caminho esperado
  → erro claro citando o `stderr` do navegador, saída 1.
- Sucesso → imprime o caminho do PDF gerado, saída 0.

## 6. Testes

Integração real, sem mock — gera um HTML mínimo de verdade num diretório temporário, roda o
script, e confirma:
- código de saída 0;
- o arquivo de saída existe;
- os primeiros bytes do arquivo são `%PDF` (assinatura do formato — prova que é um PDF de
  verdade, não um arquivo vazio ou um erro disfarçado).

Também testa os caminhos de erro: entrada inexistente (saída 1, sem tentar navegador nenhum) e
`KBR_DOCS_BROWSER` apontando pra um caminho que não existe (saída 1, mensagem clara).

Toda a classe de testes que depende de achar um navegador de verdade usa
`@unittest.skipUnless(achar_navegador_disponivel(), "nenhum navegador Chromium encontrado")` —
mesmo padrão já usado pro teste de `git init` da fatia anterior (mockar teria testado o mock, não
o comportamento real).

## 7. Documentação

`SKILL.md` do `report-creator` ganha um parágrafo curto, depois da seção "2. Gerar o documento":
depois de gerar um relatório, `python converter_pdf.py <arquivo.html>` exporta pra PDF — útil pra
quem vai anexar o documento em algum lugar que não abre HTML inline (ex.: ServiceDesk).

## 8. Fora de escopo desta fatia

- Converter uma pasta inteira / múltiplos arquivos de uma vez.
- Qualquer dependência Python nova (Playwright incluído) — o script inteiro é biblioteca padrão.
- Mudar o `SKILL.md` do `gestor-chamados` ou a memória `feedback_sdp_anexar_discovery_e_solucao`
  — feito manualmente, fora deste plano, depois que o script existir e for revisado.
- Integração automática do `kbr-docs` chamando isso sozinho ao gerar um documento — a conversão
  continua sendo um passo explícito, separado, chamado sob demanda.
