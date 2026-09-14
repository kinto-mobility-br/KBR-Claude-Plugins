# Fundação do marketplace + plugin ServiceDesk — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publicar `kinto-mobility-br/KBR-Claude-Plugins` como marketplace privado do Claude Code, com o plugin `kbr-core` (segredos por usuário e proteção contra leitura pelo modelo) e o plugin `kbr-servicedesk` (gestor de chamados por menu e wizard de configuração para leigos).

**Architecture:** Um repositório é ao mesmo tempo o marketplace (`.claude-plugin/marketplace.json`) e o monorepo dos plugins (`plugins/<nome>/`). Código compartilhado vive em `shared/` e é copiado byte a byte para dentro de cada plugin, porque plugin é autocontido e não lê arquivo de outro em tempo de execução. As skills nunca tocam em segredo: elas chamam scripts Python que leem `~/.kbr/secrets.env` por dentro, e um hook `PreToolUse` nega qualquer tentativa do modelo de ler esse arquivo.

**Tech Stack:** Python 3.10+ somente com biblioteca padrão (`urllib`, `json`, `pathlib`, `subprocess`, `argparse`, `unittest`). Claude Code plugins/skills/hooks. API ServiceDesk Plus Cloud v3 com OAuth Zoho. Sem `pip install`, sem framework, sem servidor.

**Spec:** `docs/superpowers/specs/2026-09-13-fundacao-servicedesk-design.md` (commits `d459619` e `b32428c`).

## Global Constraints

- **PT-BR em tudo** — SKILL.md, mensagens de script, comentários, docstrings, commits, README. Identificadores de código e termos técnicos (OAuth, refresh token, Self Client, display_id) ficam no original. Acentuação correta sempre.
- **Python ≥ 3.10, só biblioteca padrão.** Nenhuma dependência externa. Nenhum `pip install` para usar os plugins.
- **Todo script** segue `def main() -> int` + `if __name__ == "__main__": raise SystemExit(main())`.
- **Portabilidade Windows-first.** Caminhos por `pathlib`; nunca barra fixa; testado no Windows sem quebrar Mac e Linux.
- **Plugin é autocontido.** Um plugin nunca lê arquivo de outro em tempo de execução. `shared/kbr_secrets.py` é a fonte única, copiada byte a byte por `scripts/sincronizar_shared.py`. Editar a cópia é erro; a CI falha.
- **Caminhos em skills sempre via `${CLAUDE_PLUGIN_ROOT}`.** Nunca `~/.claude/skills/...`.
- **Nenhum valor de segredo pode ser impresso, logado ou devolvido por script.** Nem em erro, nem em `--help`, nem em modo verboso.
- **Nenhuma escrita no ServiceDesk sem a flag `--confirmar`.**
- **Nunca `git add -A`.** Nomear os caminhos e conferir `git status --short` antes de commitar.
- **Mensagem de commit** termina com:
  ```
  Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01FxSq1YTHKimYYBJmKABcBa
  ```

## Mapa de arquivos

| Arquivo | Responsabilidade | Task |
|---|---|---|
| `.gitignore`, `CLAUDE.md` | Regras do repositório | 1 |
| `shared/kbr_secrets.py` | Fonte única: parser do `.env`, resolução, `op://`, CLI | 1-4 |
| `scripts/sincronizar_shared.py` / `verificar_shared.py` | Copiar e conferir os vendorizados | 1 |
| `scripts/testar.py` | Descobrir e rodar os testes de todos os plugins | 1 |
| `plugins/kbr-core/tests/test_kbr_secrets.py` | Testes do módulo de segredos | 1-4 |
| `plugins/kbr-core/hooks/proteger_secrets.py` | Decisão do hook `PreToolUse` | 5 |
| `plugins/kbr-core/hooks/hooks.json`, `.claude-plugin/plugin.json`, `skills/secrets/SKILL.md`, `README.md` | Empacotamento do `kbr-core` | 6 |
| `.claude-plugin/marketplace.json`, `scripts/validar.py`, `scripts/criar_tag.py`, `.github/workflows/validar.yml`, `README.md` | Marketplace e CI | 7 |
| `plugins/kbr-servicedesk/scripts/sdp_api.py` | Config, erros, auth, leitura, escrita, `autorizar` | 8-11 |
| `plugins/kbr-servicedesk/.claude-plugin/plugin.json`, `skills/sdp/SKILL.md` | Gestor por menu | 12 |
| `plugins/kbr-servicedesk/skills/configurar/SKILL.md` | Wizard de 8 passos | 13 |
| `plugins/kbr-servicedesk/guia/` | Guia HTML com capturas do console Zoho | 14 |

## Contagem de testes

Os números de testes em cada "Expected" são **estimativas** para você perceber se algum arquivo
deixou de ser coletado. O que importa é: nenhuma falha, nenhum erro, e a contagem **cresce** a
cada task. Divergência de uma ou duas unidades não é problema; queda é.

## Desvio deliberado da spec

A spec previa `python -m unittest discover -s plugins -p "test_*.py"`. Isso **não funciona**: as pastas dos plugins têm hífen no nome (`kbr-core`) e não podem ser pacotes Python, então a descoberta recursiva falha ao importar. A Task 1 entrega `scripts/testar.py`, que roda a descoberta por plugin com `top_level_dir` igual ao próprio diretório de testes. A CI da Task 7 usa esse script. Registrar esse desvio no `CLAUDE.md`.

---

### Task 1: Fundação do repositório, parser do `.env` e resolução de segredo

**Files:**
- Create: `.gitignore`
- Create: `CLAUDE.md`
- Create: `shared/kbr_secrets.py`
- Create: `scripts/sincronizar_shared.py`
- Create: `scripts/verificar_shared.py`
- Create: `scripts/testar.py`
- Create: `plugins/kbr-core/scripts/kbr_secrets.py` (gerado, não editar)
- Test: `plugins/kbr-core/tests/test_kbr_secrets.py`

**Interfaces:**
- Consumes: nada.
- Produces: módulo `kbr_secrets` com `caminho_base() -> Path`, `caminho_arquivo() -> Path`, `caminho_config() -> Path`, `caminho_cache() -> Path`, `analisar(texto: str) -> tuple[dict[str, str], list[str]]`, `ler_arquivo() -> dict[str, str]`, `obter(nome: str, obrigatorio: bool = True) -> str | None`, e as exceções `ErroSegredo`, `SegredoAusente(nome)`, `SegredoInacessivel(nome, motivo)`. Constante `PREFIXO_OP = "op://"`. Variável de ambiente `KBR_HOME` sobrescreve `~/.kbr` (usada pelos testes e por automação).

- [ ] **Step 1: Criar `.gitignore`**

```gitignore
__pycache__/
*.py[cod]
.venv/
*.env
!*.env.exemplo
.DS_Store
Thumbs.db
```

- [ ] **Step 2: Criar `CLAUDE.md` com as regras do repositório**

```markdown
# CLAUDE.md — KBR-Claude-Plugins

Marketplace privado de plugins do Claude Code da KINTO Brasil. Este repositório é ao mesmo
tempo o catálogo (`.claude-plugin/marketplace.json`) e o monorepo dos plugins (`plugins/`).

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
```

- [ ] **Step 3: Escrever o teste do parser e da resolução**

`plugins/kbr-core/tests/test_kbr_secrets.py`:

```python
# -*- coding: utf-8 -*-
"""Testes do módulo de segredos — parser do .env e ordem de resolução."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import kbr_secrets  # noqa: E402


class BaseTemporaria(unittest.TestCase):
    """Redireciona ~/.kbr para uma pasta temporária via KBR_HOME."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name) / ".kbr"
        self.base.mkdir(parents=True)
        self._env_anterior = dict(os.environ)
        os.environ["KBR_HOME"] = str(self.base)
        kbr_secrets._cache_op.clear()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env_anterior)
        self.tmp.cleanup()

    def escrever(self, texto):
        kbr_secrets.caminho_arquivo().write_text(texto, encoding="utf-8")


class TesteParser(unittest.TestCase):
    def test_par_simples(self):
        valores, avisos = kbr_secrets.analisar("SDP_CLIENT_ID=abc123\n")
        self.assertEqual(valores, {"SDP_CLIENT_ID": "abc123"})
        self.assertEqual(avisos, [])

    def test_ignora_bom_e_crlf(self):
        valores, _ = kbr_secrets.analisar("\ufeffA=1\r\nB=2\r\n")
        self.assertEqual(valores, {"A": "1", "B": "2"})

    def test_ignora_comentario_e_linha_vazia(self):
        valores, avisos = kbr_secrets.analisar("# comentário\n\n  # outro\nA=1\n")
        self.assertEqual(valores, {"A": "1"})
        self.assertEqual(avisos, [])

    def test_remove_espacos_em_volta(self):
        valores, _ = kbr_secrets.analisar("  A  =  valor com espaço  \n")
        self.assertEqual(valores, {"A": "valor com espaço"})

    def test_remove_aspas(self):
        valores, _ = kbr_secrets.analisar("A=\"com aspas\"\nB='simples'\n")
        self.assertEqual(valores, {"A": "com aspas", "B": "simples"})

    def test_valor_com_igual_dentro(self):
        valores, _ = kbr_secrets.analisar("A=x=y=z\n")
        self.assertEqual(valores, {"A": "x=y=z"})

    def test_chave_repetida_vale_a_ultima(self):
        valores, _ = kbr_secrets.analisar("A=1\nA=2\n")
        self.assertEqual(valores, {"A": "2"})

    def test_linha_sem_igual_vira_aviso(self):
        valores, avisos = kbr_secrets.analisar("lixo\nA=1\n")
        self.assertEqual(valores, {"A": "1"})
        self.assertEqual(len(avisos), 1)
        self.assertIn("linha 1", avisos[0])

    def test_chave_invalida_vira_aviso(self):
        valores, avisos = kbr_secrets.analisar("minha-chave=1\nA=2\n")
        self.assertEqual(valores, {"A": "2"})
        self.assertEqual(len(avisos), 1)

    def test_valor_vazio_e_preservado(self):
        valores, avisos = kbr_secrets.analisar("A=\n")
        self.assertEqual(valores, {"A": ""})
        self.assertEqual(avisos, [])


class TesteResolucao(BaseTemporaria):
    def test_le_do_arquivo(self):
        self.escrever("SDP_CLIENT_ID=do-arquivo\n")
        self.assertEqual(kbr_secrets.obter("SDP_CLIENT_ID"), "do-arquivo")

    def test_ambiente_ganha_do_arquivo(self):
        self.escrever("SDP_CLIENT_ID=do-arquivo\n")
        os.environ["SDP_CLIENT_ID"] = "do-ambiente"
        self.assertEqual(kbr_secrets.obter("SDP_CLIENT_ID"), "do-ambiente")

    def test_ausente_obrigatorio_levanta(self):
        self.escrever("SDP_CLIENT_ID=\n")
        with self.assertRaises(kbr_secrets.SegredoAusente):
            kbr_secrets.obter("SDP_CLIENT_ID")

    def test_ausente_opcional_devolve_none(self):
        self.escrever("")
        self.assertIsNone(kbr_secrets.obter("SDP_CLIENT_ID", obrigatorio=False))

    def test_mensagem_do_erro_aponta_o_wizard(self):
        self.escrever("")
        with self.assertRaises(kbr_secrets.SegredoAusente) as caso:
            kbr_secrets.obter("SDP_CLIENT_ID")
        self.assertIn("/kbr-servicedesk:configurar", str(caso.exception))

    def test_mensagem_do_erro_nao_vaza_valor(self):
        self.escrever("OUTRO=segredo-secretissimo\n")
        with self.assertRaises(kbr_secrets.SegredoAusente) as caso:
            kbr_secrets.obter("SDP_CLIENT_ID")
        self.assertNotIn("segredo-secretissimo", str(caso.exception))

    def test_arquivo_inexistente_nao_quebra(self):
        self.assertEqual(kbr_secrets.ler_arquivo(), {})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 4: Rodar o teste e ver falhar**

Run: `python plugins/kbr-core/tests/test_kbr_secrets.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'kbr_secrets'`

- [ ] **Step 5: Escrever `shared/kbr_secrets.py` com parser e resolução**

```python
# -*- coding: utf-8 -*-
"""Acesso aos segredos dos plugins KINTO.

FONTE ÚNICA: este arquivo vive em `shared/kbr_secrets.py`. As cópias em
`plugins/*/scripts/kbr_secrets.py` são geradas por `scripts/sincronizar_shared.py`
e NÃO devem ser editadas à mão — a CI compara byte a byte e falha se divergirem.

Ordem de resolução de um segredo:
  1. variável de ambiente de mesmo nome — automação, CI e Claude Code na nuvem;
  2. arquivo `~/.kbr/secrets.env`.

Um valor que começa com `op://` é uma referência ao 1Password e é resolvido na hora
com `op read`. Nenhuma função deste módulo imprime o valor de um segredo.

A variável de ambiente `KBR_HOME` sobrescreve o caminho de `~/.kbr` — usada pelos
testes e por automação.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

PREFIXO_OP = "op://"
_CHAVE_VALIDA = re.compile(r"^[A-Z][A-Z0-9_]*$")
_cache_op: dict[str, str] = {}

CABECALHO = """\
# ============================================================
# Segredos dos plugins KINTO — este arquivo é seu e fica fora do git.
# Preencha os valores depois do "=" e salve. Não compartilhe.
#
# Quem usa o 1Password CLI pode escrever a referência no lugar do valor:
#   SDP_CLIENT_ID=op://Cofre/Nome do item/campo
# ============================================================
"""


class ErroSegredo(Exception):
    """Base dos erros deste módulo."""


class SegredoAusente(ErroSegredo):
    def __init__(self, nome: str) -> None:
        dica = ("/kbr-servicedesk:configurar" if nome.startswith("SDP_")
                else "/kbr-core:secrets status")
        super().__init__(
            f"O segredo {nome} não está preenchido. Rode {dica} para configurar. "
            f"O valor fica no seu arquivo de segredos e nunca passa pelo chat."
        )
        self.nome = nome


class SegredoInacessivel(ErroSegredo):
    def __init__(self, nome: str, motivo: str) -> None:
        super().__init__(
            f"O segredo {nome} aponta para o 1Password, mas não consegui lê-lo: {motivo}. "
            f"Confira se o 1Password CLI (op) está instalado e o cofre desbloqueado."
        )
        self.nome = nome
        self.motivo = motivo


def caminho_base() -> Path:
    override = os.environ.get("KBR_HOME")
    return Path(override) if override else Path.home() / ".kbr"


def caminho_arquivo() -> Path:
    return caminho_base() / "secrets.env"


def caminho_config() -> Path:
    return caminho_base() / "config.json"


def caminho_cache() -> Path:
    return caminho_base() / "cache"


def analisar(texto: str) -> tuple[dict[str, str], list[str]]:
    """Lê o conteúdo de um secrets.env. Devolve (valores, avisos)."""
    valores: dict[str, str] = {}
    avisos: list[str] = []
    if texto.startswith("\ufeff"):
        texto = texto[1:]
    for numero, linha_bruta in enumerate(texto.splitlines(), start=1):
        linha = linha_bruta.strip()
        if not linha or linha.startswith("#"):
            continue
        if "=" not in linha:
            avisos.append(f"linha {numero}: sem '=', ignorada")
            continue
        chave, _, valor = linha.partition("=")
        chave = chave.strip()
        if not _CHAVE_VALIDA.match(chave):
            avisos.append(f"linha {numero}: nome de chave inválido, ignorada")
            continue
        valor = valor.strip()
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
            valor = valor[1:-1]
        valores[chave] = valor
    return valores, avisos


def ler_arquivo() -> dict[str, str]:
    caminho = caminho_arquivo()
    if not caminho.exists():
        return {}
    return analisar(caminho.read_text(encoding="utf-8"))[0]


def obter(nome: str, obrigatorio: bool = True) -> str | None:
    """Devolve o valor do segredo, ou None se ausente e não obrigatório."""
    bruto = (os.environ.get(nome) or ler_arquivo().get(nome, "") or "").strip()
    if not bruto:
        if obrigatorio:
            raise SegredoAusente(nome)
        return None
    if bruto.startswith(PREFIXO_OP):
        return _resolver_op(bruto, nome)
    return bruto


def _resolver_op(referencia: str, nome: str) -> str:
    raise SegredoInacessivel(nome, "suporte a op:// ainda não implementado")
```

- [ ] **Step 6: Rodar o teste e ver passar**

Run: `python plugins/kbr-core/tests/test_kbr_secrets.py -v`
Expected: PASS — 17 testes OK. (Os testes importam de `plugins/kbr-core/scripts/`, que ainda não existe; o Step 7 resolve. Se falhar por import, siga para o Step 7 e volte.)

- [ ] **Step 7: Escrever os scripts de sincronização do `shared/`**

`scripts/sincronizar_shared.py`:

```python
# -*- coding: utf-8 -*-
"""Copia os arquivos de shared/ para dentro de cada plugin que os vendoriza.

Plugin é autocontido: não pode ler arquivo de outro em tempo de execução. Por isso
o código comum vive em shared/ (fonte única) e é COPIADO byte a byte para cada
plugin. Edite só a fonte; rode este script; commite as duas coisas juntas.
"""
from __future__ import annotations

import shutil
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

VENDORIZADOS: dict[str, list[str]] = {
    "shared/kbr_secrets.py": [
        "plugins/kbr-core/scripts/kbr_secrets.py",
        "plugins/kbr-servicedesk/scripts/kbr_secrets.py",
    ],
}


def main() -> int:
    for origem_rel, destinos in VENDORIZADOS.items():
        origem = RAIZ / origem_rel
        if not origem.is_file():
            print(f"ERRO: fonte não encontrada: {origem_rel}")
            return 1
        for destino_rel in destinos:
            destino = RAIZ / destino_rel
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(origem, destino)
            print(f"  {origem_rel} -> {destino_rel}")
    print("sincronização concluída")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`scripts/verificar_shared.py`:

```python
# -*- coding: utf-8 -*-
"""Falha se alguma cópia vendorizada divergir da fonte em shared/."""
from __future__ import annotations

from pathlib import Path

from sincronizar_shared import RAIZ, VENDORIZADOS


def main() -> int:
    divergentes: list[str] = []
    for origem_rel, destinos in VENDORIZADOS.items():
        origem = (RAIZ / origem_rel).read_bytes()
        for destino_rel in destinos:
            destino = RAIZ / destino_rel
            if not destino.is_file():
                divergentes.append(f"{destino_rel} (não existe)")
            elif destino.read_bytes() != origem:
                divergentes.append(f"{destino_rel} (difere de {origem_rel})")
    if divergentes:
        print("cópias fora de sincronia:")
        for item in divergentes:
            print(f"  - {item}")
        print("\nrode: python scripts/sincronizar_shared.py")
        return 1
    print("todas as cópias vendorizadas estão idênticas à fonte")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Nota: `verificar_shared.py` importa `sincronizar_shared` do mesmo diretório, que é `sys.path[0]` quando rodado como `python scripts/verificar_shared.py`.

- [ ] **Step 8: Escrever `scripts/testar.py`**

```python
# -*- coding: utf-8 -*-
"""Roda os testes de todos os plugins.

`python -m unittest discover -s plugins` não funciona: as pastas dos plugins têm
hífen no nome e não podem ser pacotes Python. Aqui a descoberta é feita por plugin,
com top_level_dir igual ao próprio diretório de testes.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def main() -> int:
    pastas = sorted((RAIZ / "plugins").glob("*/tests"))
    if not pastas:
        print("nenhuma pasta de testes encontrada em plugins/*/tests")
        return 1
    carregador = unittest.TestLoader()
    suite = unittest.TestSuite()
    for pasta in pastas:
        print(f"descobrindo testes em {pasta.relative_to(RAIZ)}")
        suite.addTests(carregador.discover(
            start_dir=str(pasta), top_level_dir=str(pasta), pattern="test_*.py"))
    resultado = unittest.TextTestRunner(verbosity=2, stream=sys.stdout).run(suite)
    return 0 if resultado.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 9: Gerar a cópia vendorizada e rodar tudo**

Run:
```bash
python scripts/sincronizar_shared.py
python scripts/verificar_shared.py
python scripts/testar.py
```
Expected: sincroniza 2 destinos (o de `kbr-servicedesk` é criado agora e usado na Task 8); verificação OK; 17 testes PASS.

- [ ] **Step 10: Commit**

```bash
git add .gitignore CLAUDE.md shared/kbr_secrets.py scripts/sincronizar_shared.py scripts/verificar_shared.py scripts/testar.py plugins/kbr-core/scripts/kbr_secrets.py plugins/kbr-servicedesk/scripts/kbr_secrets.py plugins/kbr-core/tests/test_kbr_secrets.py
git status --short
git commit -m "$(cat <<'MSG'
feat(kbr-core): parser do secrets.env e resolução de segredo

Fonte única em shared/, vendorizada nos plugins por script. Ordem de
resolução: variável de ambiente antes do arquivo. Nenhuma função imprime
valor de segredo.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FxSq1YTHKimYYBJmKABcBa
MSG
)"
```

---

### Task 2: Referências `op://` — resolução, cache e gravação

**Files:**
- Modify: `shared/kbr_secrets.py` (substituir o stub `_resolver_op`, acrescentar gravação)
- Modify: `plugins/kbr-core/tests/test_kbr_secrets.py` (acrescentar classe de teste)
- Regenerate: `plugins/kbr-core/scripts/kbr_secrets.py`, `plugins/kbr-servicedesk/scripts/kbr_secrets.py`

**Interfaces:**
- Consumes: da Task 1 — `obter`, `ler_arquivo`, `caminho_arquivo`, `PREFIXO_OP`, `_cache_op`, `SegredoInacessivel`, `SegredoAusente`.
- Produces: `gravar(nome: str, valor: str) -> None` — grava no arquivo, ou no 1Password quando o valor atual da chave é uma referência `op://`, sem nunca trocar a referência por valor literal. `op_disponivel() -> bool`. Helper interno `_partes_op(referencia, nome) -> tuple[str, str, str]` devolvendo `(cofre, item, campo)`.

- [ ] **Step 1: Escrever os testes de `op://`**

Acrescentar ao fim de `plugins/kbr-core/tests/test_kbr_secrets.py`, antes do `if __name__`:

```python
class OpFalso:
    """Substitui subprocess.run para o comando op, registrando as chamadas."""

    def __init__(self, saida="", erro="", codigo=0, ausente=False):
        self.saida, self.erro, self.codigo, self.ausente = saida, erro, codigo, ausente
        self.chamadas = []

    def __call__(self, argumentos, **kwargs):
        if self.ausente:
            raise FileNotFoundError("op")
        self.chamadas.append(list(argumentos))
        return SimpleNamespace(returncode=self.codigo, stdout=self.saida, stderr=self.erro)


class TesteOnePassword(BaseTemporaria):
    def test_resolve_referencia(self):
        self.escrever("SDP_CLIENT_ID=op://Kinto Brasil/Item SDP/client-id\n")
        falso = OpFalso(saida="valor-do-cofre\n")
        kbr_secrets._rodar_op = falso
        self.assertEqual(kbr_secrets.obter("SDP_CLIENT_ID"), "valor-do-cofre")
        self.assertEqual(falso.chamadas[0],
                         ["read", "op://Kinto Brasil/Item SDP/client-id"])

    def test_cacheia_por_processo(self):
        self.escrever("SDP_CLIENT_ID=op://Cofre/Item/campo\n")
        falso = OpFalso(saida="valor\n")
        kbr_secrets._rodar_op = falso
        kbr_secrets.obter("SDP_CLIENT_ID")
        kbr_secrets.obter("SDP_CLIENT_ID")
        self.assertEqual(len(falso.chamadas), 1)

    def test_op_ausente_gera_erro_em_portugues(self):
        self.escrever("SDP_CLIENT_ID=op://Cofre/Item/campo\n")
        kbr_secrets._rodar_op = OpFalso(ausente=True)
        with self.assertRaises(kbr_secrets.SegredoInacessivel) as caso:
            kbr_secrets.obter("SDP_CLIENT_ID")
        self.assertIn("não está instalado", str(caso.exception))

    def test_op_com_erro_usa_so_a_primeira_linha(self):
        self.escrever("SDP_CLIENT_ID=op://Cofre/Item/campo\n")
        kbr_secrets._rodar_op = OpFalso(
            codigo=1, erro="cofre bloqueado\nlinha dois\nlinha três")
        with self.assertRaises(kbr_secrets.SegredoInacessivel) as caso:
            kbr_secrets.obter("SDP_CLIENT_ID")
        self.assertIn("cofre bloqueado", str(caso.exception))
        self.assertNotIn("linha três", str(caso.exception))

    def test_valor_vazio_do_cofre_gera_erro(self):
        self.escrever("SDP_CLIENT_ID=op://Cofre/Item/campo\n")
        kbr_secrets._rodar_op = OpFalso(saida="   \n")
        with self.assertRaises(kbr_secrets.SegredoInacessivel):
            kbr_secrets.obter("SDP_CLIENT_ID")

    def test_referencia_mal_formada(self):
        self.escrever("SDP_CLIENT_ID=op://so-uma-parte\n")
        kbr_secrets._rodar_op = OpFalso(saida="x")
        with self.assertRaises(kbr_secrets.SegredoInacessivel) as caso:
            kbr_secrets.obter("SDP_CLIENT_ID")
        self.assertIn("mal formada", str(caso.exception))

    def test_gravar_em_chave_literal_altera_o_arquivo(self):
        self.escrever("# cabeçalho\nSDP_REFRESH_TOKEN=antigo\nOUTRA=x\n")
        kbr_secrets.gravar("SDP_REFRESH_TOKEN", "novo")
        texto = kbr_secrets.caminho_arquivo().read_text(encoding="utf-8")
        self.assertIn("SDP_REFRESH_TOKEN=novo", texto)
        self.assertIn("# cabeçalho", texto)
        self.assertIn("OUTRA=x", texto)

    def test_gravar_chave_inexistente_acrescenta(self):
        self.escrever("A=1\n")
        kbr_secrets.gravar("B", "2")
        self.assertEqual(kbr_secrets.ler_arquivo()["B"], "2")

    def test_gravar_em_chave_op_vai_para_o_cofre(self):
        self.escrever("SDP_REFRESH_TOKEN=op://Kinto Brasil/Item SDP/refresh-token\n")
        falso = OpFalso(saida="ok")
        kbr_secrets._rodar_op = falso
        kbr_secrets.gravar("SDP_REFRESH_TOKEN", "token-novo")
        self.assertEqual(falso.chamadas[0], [
            "item", "edit", "Item SDP", "--vault", "Kinto Brasil",
            "refresh-token=token-novo"])

    def test_gravar_em_chave_op_preserva_a_referencia(self):
        self.escrever("SDP_REFRESH_TOKEN=op://Cofre/Item/campo\n")
        kbr_secrets._rodar_op = OpFalso(saida="ok")
        kbr_secrets.gravar("SDP_REFRESH_TOKEN", "token-novo")
        texto = kbr_secrets.caminho_arquivo().read_text(encoding="utf-8")
        self.assertIn("op://Cofre/Item/campo", texto)
        self.assertNotIn("token-novo", texto)
```

Acrescentar ao topo do arquivo de teste, junto dos outros imports:

```python
from types import SimpleNamespace
```

E no `setUp` da `BaseTemporaria`, guardar e restaurar o `_rodar_op` original:

```python
        self._rodar_op_original = kbr_secrets._rodar_op
```
e no `tearDown`:
```python
        kbr_secrets._rodar_op = self._rodar_op_original
```

- [ ] **Step 2: Rodar os testes e ver falhar**

Run: `python scripts/testar.py`
Expected: FAIL — `AttributeError: module 'kbr_secrets' has no attribute '_rodar_op'` e `gravar` inexistente.

- [ ] **Step 3: Implementar `op://` em `shared/kbr_secrets.py`**

Acrescentar `import shutil` e `import subprocess` aos imports, e substituir o stub `_resolver_op`:

```python
def _rodar_op(argumentos: list[str]):
    """Chama o 1Password CLI. Isolado numa função para os testes substituírem."""
    return subprocess.run(["op", *argumentos], capture_output=True, text=True)


def op_disponivel() -> bool:
    return shutil.which("op") is not None


def _partes_op(referencia: str, nome: str) -> tuple[str, str, str]:
    partes = referencia[len(PREFIXO_OP):].split("/")
    if len(partes) != 3 or not all(parte.strip() for parte in partes):
        raise SegredoInacessivel(
            nome, f"referência mal formada (esperado op://cofre/item/campo)")
    return partes[0], partes[1], partes[2]


def _motivo_da_falha(processo) -> str:
    linhas = (processo.stderr or "").strip().splitlines()
    return linhas[0] if linhas else f"o comando op saiu com código {processo.returncode}"


def _resolver_op(referencia: str, nome: str) -> str:
    if referencia in _cache_op:
        return _cache_op[referencia]
    _partes_op(referencia, nome)  # valida o formato antes de chamar o op
    try:
        processo = _rodar_op(["read", referencia])
    except FileNotFoundError:
        raise SegredoInacessivel(
            nome, "o comando 'op' não está instalado ou não está no PATH") from None
    if processo.returncode != 0:
        raise SegredoInacessivel(nome, _motivo_da_falha(processo))
    valor = (processo.stdout or "").strip()
    if not valor:
        raise SegredoInacessivel(nome, "o 1Password devolveu um valor vazio")
    _cache_op[referencia] = valor
    return valor


def gravar(nome: str, valor: str) -> None:
    """Grava um segredo. Se a chave aponta para o 1Password, grava lá.

    A referência op:// NUNCA é substituída por valor literal no arquivo.
    """
    atual = (ler_arquivo().get(nome, "") or "").strip()
    if atual.startswith(PREFIXO_OP):
        _gravar_op(atual, valor, nome)
        _cache_op[atual] = valor
        return
    _gravar_arquivo(nome, valor)


def _gravar_op(referencia: str, valor: str, nome: str) -> None:
    cofre, item, campo = _partes_op(referencia, nome)
    try:
        processo = _rodar_op(["item", "edit", item, "--vault", cofre, f"{campo}={valor}"])
    except FileNotFoundError:
        raise SegredoInacessivel(
            nome, "o comando 'op' não está instalado ou não está no PATH") from None
    if processo.returncode != 0:
        raise SegredoInacessivel(nome, _motivo_da_falha(processo))


def _gravar_arquivo(nome: str, valor: str) -> None:
    caminho = caminho_arquivo()
    texto = caminho.read_text(encoding="utf-8") if caminho.exists() else CABECALHO
    linhas = texto.splitlines()
    padrao = re.compile(rf"^\s*{re.escape(nome)}\s*=")
    for indice, linha in enumerate(linhas):
        if padrao.match(linha):
            linhas[indice] = f"{nome}={valor}"
            break
    else:
        linhas.append(f"{nome}={valor}")
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
```

- [ ] **Step 4: Sincronizar e rodar os testes**

Run:
```bash
python scripts/sincronizar_shared.py
python scripts/testar.py
```
Expected: PASS — 28 testes OK.

- [ ] **Step 5: Commit**

```bash
git add shared/kbr_secrets.py plugins/kbr-core/scripts/kbr_secrets.py plugins/kbr-servicedesk/scripts/kbr_secrets.py plugins/kbr-core/tests/test_kbr_secrets.py
git status --short
git commit -m "$(cat <<'MSG'
feat(kbr-core): referências op:// com cache e gravação no cofre

Valor que começa com op:// é resolvido por `op read`, cacheado por processo.
Gravar numa chave assim vai para o 1Password por `op item edit`; a referência
nunca vira valor literal no arquivo.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FxSq1YTHKimYYBJmKABcBa
MSG
)"
```

---

### Task 3: CLI `init` e `registrar`, com permissões do sistema de arquivos

**Files:**
- Modify: `shared/kbr_secrets.py`
- Modify: `plugins/kbr-core/tests/test_kbr_secrets.py`
- Regenerate: as duas cópias vendorizadas

**Interfaces:**
- Consumes: da Task 1 e 2 — caminhos, `CABECALHO`, `analisar`, `ler_arquivo`.
- Produces: `aplicar_permissoes(base: Path) -> list[str]` (devolve avisos), `conferir_permissoes(base: Path) -> list[str]`, `cmd_init(args) -> int`, `cmd_registrar(args) -> int`, e `main() -> int` com os subcomandos `init` e `registrar` via `argparse`. `registrar` recebe `--plugin <nome>` e `--chaves A,B,C`.

- [ ] **Step 1: Escrever os testes de `init` e `registrar`**

Acrescentar ao arquivo de teste:

```python
class TesteInitERegistrar(BaseTemporaria):
    def setUp(self):
        super().setUp()
        # init cria a própria pasta; começa sem ela
        for filho in sorted(self.base.rglob("*"), reverse=True):
            filho.unlink() if filho.is_file() else filho.rmdir()
        self.base.rmdir()

    def executar(self, *argumentos):
        return kbr_secrets.main(list(argumentos))

    def test_init_cria_estrutura(self):
        self.assertEqual(self.executar("init"), 0)
        self.assertTrue(kbr_secrets.caminho_arquivo().is_file())
        self.assertTrue(kbr_secrets.caminho_config().is_file())
        self.assertTrue(kbr_secrets.caminho_cache().is_dir())

    def test_init_escreve_o_cabecalho(self):
        self.executar("init")
        texto = kbr_secrets.caminho_arquivo().read_text(encoding="utf-8")
        self.assertIn("fica fora do git", texto)

    def test_init_e_idempotente_e_nao_apaga_valores(self):
        self.executar("init")
        kbr_secrets.gravar("A", "valor-importante")
        self.executar("init")
        self.assertEqual(kbr_secrets.ler_arquivo()["A"], "valor-importante")

    def test_registrar_acrescenta_chaves_vazias(self):
        self.executar("init")
        self.executar("registrar", "--plugin", "kbr-servicedesk",
                      "--chaves", "SDP_CLIENT_ID,SDP_CLIENT_SECRET")
        valores = kbr_secrets.ler_arquivo()
        self.assertEqual(valores["SDP_CLIENT_ID"], "")
        self.assertEqual(valores["SDP_CLIENT_SECRET"], "")

    def test_registrar_escreve_a_marca_do_plugin(self):
        self.executar("init")
        self.executar("registrar", "--plugin", "kbr-servicedesk", "--chaves", "SDP_A")
        texto = kbr_secrets.caminho_arquivo().read_text(encoding="utf-8")
        self.assertIn("# --- kbr-servicedesk ---", texto)

    def test_registrar_e_idempotente(self):
        self.executar("init")
        self.executar("registrar", "--plugin", "p", "--chaves", "A,B")
        self.executar("registrar", "--plugin", "p", "--chaves", "A,B")
        texto = kbr_secrets.caminho_arquivo().read_text(encoding="utf-8")
        self.assertEqual(texto.count("A="), 1)
        self.assertEqual(texto.count("# --- p ---"), 1)

    def test_registrar_nao_apaga_valor_existente(self):
        self.executar("init")
        self.executar("registrar", "--plugin", "p", "--chaves", "A")
        kbr_secrets.gravar("A", "ja-preenchido")
        self.executar("registrar", "--plugin", "p", "--chaves", "A,B")
        self.assertEqual(kbr_secrets.ler_arquivo()["A"], "ja-preenchido")

    def test_registrar_roda_o_init_sozinho(self):
        self.assertEqual(self.executar("registrar", "--plugin", "p", "--chaves", "A"), 0)
        self.assertTrue(kbr_secrets.caminho_arquivo().is_file())

    @unittest.skipIf(os.name == "nt", "modo POSIX")
    def test_permissoes_posix(self):
        self.executar("init")
        self.assertEqual(kbr_secrets.caminho_base().stat().st_mode & 0o777, 0o700)
        self.assertEqual(kbr_secrets.caminho_arquivo().stat().st_mode & 0o777, 0o600)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python scripts/testar.py`
Expected: FAIL — `AttributeError: module 'kbr_secrets' has no attribute 'main'`

- [ ] **Step 3: Implementar `init`, `registrar` e o esqueleto do `main`**

Acrescentar `import argparse`, `import getpass`, `import sys` aos imports e, ao fim de `shared/kbr_secrets.py`:

```python
def aplicar_permissoes(base: Path) -> list[str]:
    """Restringe a pasta ao usuário atual. Devolve avisos (nunca levanta)."""
    avisos: list[str] = []
    if os.name == "nt":
        usuario = os.environ.get("USERNAME") or getpass.getuser()
        try:
            processo = subprocess.run(
                ["icacls", str(base), "/inheritance:r", "/grant:r", f"{usuario}:(OI)(CI)F"],
                capture_output=True, text=True)
            if processo.returncode != 0:
                avisos.append("não consegui restringir a pasta ao seu usuário com o icacls")
        except FileNotFoundError:
            avisos.append("icacls não encontrado; a pasta ficou com as permissões herdadas")
    else:
        base.chmod(0o700)
        arquivo = base / "secrets.env"
        if arquivo.exists():
            arquivo.chmod(0o600)
    return avisos


_IDENTIDADES_AMPLAS = ("todos", "everyone", "usuários", "usuarios", "users", "authenticated")


def conferir_permissoes(base: Path) -> list[str]:
    """Avisa se a pasta está acessível a mais gente que o usuário atual."""
    if os.name == "nt":
        try:
            processo = subprocess.run(["icacls", str(base)], capture_output=True, text=True)
        except FileNotFoundError:
            return []
        if processo.returncode != 0:
            return []
        texto = (processo.stdout or "").lower()
        if any(marca in texto for marca in _IDENTIDADES_AMPLAS):
            return ["a pasta parece acessível a outros usuários da máquina; "
                    "rode /kbr-core:secrets init de novo para restringir"]
        return []
    modo = base.stat().st_mode & 0o777
    if modo & 0o077:
        return [f"a pasta está com permissões {modo:o}; o esperado é 700"]
    return []


def cmd_init(_args) -> int:
    base = caminho_base()
    base.mkdir(parents=True, exist_ok=True)
    caminho_cache().mkdir(parents=True, exist_ok=True)
    arquivo = caminho_arquivo()
    if not arquivo.exists():
        arquivo.write_text(CABECALHO, encoding="utf-8")
    config = caminho_config()
    if not config.exists():
        config.write_text("{}\n", encoding="utf-8")
    avisos = aplicar_permissoes(base)
    print(f"pasta de configuração: {base}")
    print("arquivo de segredos criado (ou já existia) e restrito ao seu usuário")
    for aviso in avisos:
        print(f"AVISO: {aviso}")
    return 0


def _chaves_pedidas(bruto: str) -> list[str]:
    return [parte.strip() for parte in bruto.split(",") if parte.strip()]


def cmd_registrar(args) -> int:
    cmd_init(args)
    arquivo = caminho_arquivo()
    texto = arquivo.read_text(encoding="utf-8")
    existentes = analisar(texto)[0]
    faltando = [c for c in _chaves_pedidas(args.chaves) if c not in existentes]
    if not faltando:
        print(f"nada a fazer: as chaves de {args.plugin} já estão no arquivo")
        return 0
    marca = f"# --- {args.plugin} ---"
    if not texto.endswith("\n"):
        texto += "\n"
    bloco = "" if marca in texto else f"\n{marca}\n"
    bloco += "".join(f"{chave}=\n" for chave in faltando)
    arquivo.write_text(texto + bloco, encoding="utf-8")
    print(f"chaves acrescentadas para {args.plugin}: {', '.join(faltando)}")
    return 0


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Segredos dos plugins KINTO. Nenhum subcomando imprime o valor de um segredo.")
    sub = parser.add_subparsers(dest="comando", required=True)

    sub.add_parser("init", help="cria ~/.kbr com o arquivo de segredos e restringe o acesso")

    registrar = sub.add_parser("registrar", help="acrescenta as chaves de um plugin ao arquivo")
    registrar.add_argument("--plugin", required=True)
    registrar.add_argument("--chaves", required=True, help="lista separada por vírgula")

    return parser


COMANDOS = {"init": cmd_init, "registrar": cmd_registrar}


def main(argumentos: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = construir_parser().parse_args(argumentos)
    return COMANDOS[args.comando](args)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Sincronizar e rodar os testes**

Run:
```bash
python scripts/sincronizar_shared.py
python scripts/testar.py
```
Expected: PASS — 37 testes OK (no Windows, o teste POSIX é pulado).

- [ ] **Step 5: Conferir o init de verdade numa pasta temporária**

Run (Bash):
```bash
KBR_HOME="$TEMP/kbr-teste-init" python plugins/kbr-core/scripts/kbr_secrets.py init
KBR_HOME="$TEMP/kbr-teste-init" python plugins/kbr-core/scripts/kbr_secrets.py registrar --plugin kbr-servicedesk --chaves SDP_CLIENT_ID,SDP_CLIENT_SECRET,SDP_GRANT_CODE,SDP_REFRESH_TOKEN
cat "$TEMP/kbr-teste-init/secrets.env"
rm -rf "$TEMP/kbr-teste-init"
```
Expected: cabeçalho seguido da marca `# --- kbr-servicedesk ---` e as quatro chaves vazias. Nenhum aviso de permissão.

- [ ] **Step 6: Commit**

```bash
git add shared/kbr_secrets.py plugins/kbr-core/scripts/kbr_secrets.py plugins/kbr-servicedesk/scripts/kbr_secrets.py plugins/kbr-core/tests/test_kbr_secrets.py
git status --short
git commit -m "$(cat <<'MSG'
feat(kbr-core): subcomandos init e registrar com permissões restritas

init cria ~/.kbr, o arquivo de segredos e o cache, e restringe a pasta ao
usuário atual (icacls no Windows, chmod 700/600 no resto). registrar
acrescenta as chaves de um plugin sem tocar em valor já preenchido.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FxSq1YTHKimYYBJmKABcBa
MSG
)"
```

---

### Task 4: CLI `status`, `editar` e `proteger`

**Files:**
- Modify: `shared/kbr_secrets.py`
- Modify: `plugins/kbr-core/tests/test_kbr_secrets.py`
- Regenerate: as duas cópias vendorizadas

**Interfaces:**
- Consumes: das Tasks 1-3 — `analisar`, `caminho_arquivo`, `op_disponivel`, `conferir_permissoes`, `construir_parser`, `COMANDOS`.
- Produces: `cmd_status(args) -> int` (0 se tudo pronto, 1 se falta algo), `cmd_editar(args) -> int`, `cmd_proteger(args) -> int`, `caminho_settings() -> Path`, `deny_configurado() -> bool`, constante `REGRAS_DENY: list[str]`, e `_chaves_do_bloco(texto: str, plugin: str) -> list[str]`. `status` aceita `--plugin <nome>`.

- [ ] **Step 1: Escrever os testes**

```python
class TesteStatus(BaseTemporaria):
    def rodar_status(self, *argumentos):
        captura = io.StringIO()
        with contextlib.redirect_stdout(captura):
            codigo = kbr_secrets.main(["status", *argumentos])
        return codigo, captura.getvalue()

    def test_marca_preenchida_e_vazia_sem_mostrar_valor(self):
        self.escrever("# --- p ---\nA=valor-secretissimo\nB=\n")
        codigo, saida = self.rodar_status()
        self.assertIn("A: preenchida", saida)
        self.assertIn("B: vazia", saida)
        self.assertNotIn("valor-secretissimo", saida)
        self.assertEqual(codigo, 1)

    def test_marca_referencia_do_1password(self):
        self.escrever("A=op://Cofre/Item/campo\n")
        kbr_secrets.op_disponivel = lambda: True
        _, saida = self.rodar_status()
        self.assertIn("A: preenchida (1Password)", saida)
        self.assertNotIn("op://Cofre/Item/campo", saida)

    def test_status_nao_chama_op_read(self):
        self.escrever("A=op://Cofre/Item/campo\n")
        falso = OpFalso(saida="x")
        kbr_secrets._rodar_op = falso
        kbr_secrets.op_disponivel = lambda: True
        self.rodar_status()
        self.assertEqual(falso.chamadas, [])

    def test_avisa_quando_op_falta(self):
        self.escrever("A=op://Cofre/Item/campo\n")
        kbr_secrets.op_disponivel = lambda: False
        codigo, saida = self.rodar_status()
        self.assertIn("NÃO encontrado", saida)
        self.assertEqual(codigo, 1)

    def test_tudo_preenchido_sai_zero(self):
        self.escrever("A=1\nB=2\n")
        codigo, _ = self.rodar_status()
        self.assertEqual(codigo, 0)

    def test_filtra_por_plugin(self):
        self.escrever("# --- p1 ---\nA=1\n\n# --- p2 ---\nB=2\n")
        _, saida = self.rodar_status("--plugin", "p1")
        self.assertIn("A:", saida)
        self.assertNotIn("B:", saida)

    def test_repassa_avisos_de_linha_invalida(self):
        self.escrever("lixo sem igual\nA=1\n")
        _, saida = self.rodar_status()
        self.assertIn("linha 1", saida)

    def test_arquivo_inexistente_orienta_o_init(self):
        codigo, saida = self.rodar_status()
        self.assertEqual(codigo, 1)
        self.assertIn("init", saida)


class TesteProteger(BaseTemporaria):
    def setUp(self):
        super().setUp()
        self.settings = Path(self.tmp.name) / ".claude" / "settings.json"
        kbr_secrets.caminho_settings = lambda: self.settings

    def test_cria_o_settings_com_as_regras(self):
        self.assertEqual(kbr_secrets.main(["proteger"]), 0)
        dados = json.loads(self.settings.read_text(encoding="utf-8"))
        self.assertIn("Read(~/.kbr/secrets.env)", dados["permissions"]["deny"])
        self.assertIn("Edit(~/.kbr/cache/**)", dados["permissions"]["deny"])

    def test_preserva_o_resto_do_settings(self):
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text(
            json.dumps({"model": "opus", "permissions": {"deny": ["Read(./.env)"]}}),
            encoding="utf-8")
        kbr_secrets.main(["proteger"])
        dados = json.loads(self.settings.read_text(encoding="utf-8"))
        self.assertEqual(dados["model"], "opus")
        self.assertIn("Read(./.env)", dados["permissions"]["deny"])

    def test_e_idempotente(self):
        kbr_secrets.main(["proteger"])
        kbr_secrets.main(["proteger"])
        deny = json.loads(self.settings.read_text(encoding="utf-8"))["permissions"]["deny"]
        self.assertEqual(len(deny), len(set(deny)))

    def test_settings_invalido_nao_apaga_nada(self):
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text("{ isso não é json", encoding="utf-8")
        codigo = kbr_secrets.main(["proteger"])
        self.assertEqual(codigo, 1)
        self.assertIn("isso não é json", self.settings.read_text(encoding="utf-8"))
```

Acrescentar aos imports do arquivo de teste: `import contextlib`, `import io`, `import json`.

- [ ] **Step 2: Rodar e ver falhar**

Run: `python scripts/testar.py`
Expected: FAIL — `argument comando: invalid choice: 'status'`

- [ ] **Step 3: Implementar os três subcomandos**

Acrescentar `import json` aos imports e, antes de `construir_parser`:

```python
REGRAS_DENY = [
    "Read(~/.kbr/secrets.env)",
    "Edit(~/.kbr/secrets.env)",
    "Read(~/.kbr/cache/**)",
    "Edit(~/.kbr/cache/**)",
]


def caminho_settings() -> Path:
    return Path.home() / ".claude" / "settings.json"


def deny_configurado() -> bool:
    caminho = caminho_settings()
    if not caminho.exists():
        return False
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    deny = (dados.get("permissions") or {}).get("deny") or []
    return any(".kbr" in str(regra) for regra in deny)


def _chaves_do_bloco(texto: str, plugin: str) -> list[str]:
    """Chaves entre a marca do plugin e a próxima marca de bloco."""
    marca = f"# --- {plugin} ---"
    dentro = False
    chaves: list[str] = []
    for linha in texto.splitlines():
        despida = linha.strip()
        if despida.startswith("# --- "):
            dentro = despida == marca
            continue
        if dentro and "=" in despida and not despida.startswith("#"):
            chave = despida.partition("=")[0].strip()
            if _CHAVE_VALIDA.match(chave):
                chaves.append(chave)
    return chaves


def cmd_status(args) -> int:
    arquivo = caminho_arquivo()
    if not arquivo.exists():
        print("o arquivo de segredos ainda não existe.")
        print("rode /kbr-core:secrets init para criá-lo.")
        return 1
    texto = arquivo.read_text(encoding="utf-8")
    valores, avisos = analisar(texto)
    chaves = sorted(valores)
    if getattr(args, "plugin", None):
        do_bloco = set(_chaves_do_bloco(texto, args.plugin))
        chaves = [chave for chave in chaves if chave in do_bloco]
    print(f"arquivo de segredos: {arquivo}")
    problemas = 0
    usa_op = False
    if not chaves:
        print("  (nenhuma chave registrada ainda)")
    for chave in chaves:
        valor = valores[chave].strip()
        if not valor:
            print(f"  {chave}: vazia")
            problemas += 1
        elif valor.startswith(PREFIXO_OP):
            usa_op = True
            print(f"  {chave}: preenchida (1Password)")
        else:
            print(f"  {chave}: preenchida")
    for aviso in avisos:
        print(f"  AVISO: {aviso}")
    if usa_op:
        if op_disponivel():
            print("  1Password CLI: encontrado")
        else:
            print("  1Password CLI: NÃO encontrado no PATH")
            problemas += 1
    for aviso in conferir_permissoes(caminho_base()):
        print(f"  AVISO: {aviso}")
    print(f"  proteção no settings do Claude Code: "
          f"{'ativa' if deny_configurado() else 'ausente (rode o init e aceite)'}")
    return 1 if problemas else 0


def cmd_editar(_args) -> int:
    arquivo = caminho_arquivo()
    if not arquivo.exists():
        print("o arquivo de segredos ainda não existe. rode o init primeiro.")
        return 1
    try:
        if os.name == "nt":
            os.startfile(str(arquivo))  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.run(["open", str(arquivo)], check=False)
        else:
            subprocess.run(["xdg-open", str(arquivo)], check=False)
    except OSError as erro:
        print(f"não consegui abrir o editor automaticamente ({erro}).")
        print("abra o arquivo de segredos pelo seu explorador de arquivos.")
        return 1
    print("abri o arquivo de segredos no seu editor padrão.")
    print("cole os valores depois do '=', salve, feche e volte aqui.")
    return 0


def cmd_proteger(_args) -> int:
    caminho = caminho_settings()
    dados: dict = {}
    if caminho.exists():
        try:
            dados = json.loads(caminho.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"não consegui entender o {caminho}: não é um JSON válido.")
            print("não mexi em nada. acrescente estas linhas à mão em permissions.deny:")
            for regra in REGRAS_DENY:
                print(f"  {regra}")
            return 1
    permissoes = dados.setdefault("permissions", {})
    deny = permissoes.setdefault("deny", [])
    novas = [regra for regra in REGRAS_DENY if regra not in deny]
    deny.extend(novas)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"proteção gravada em {caminho}: {len(novas)} regra(s) nova(s), "
          f"{len(REGRAS_DENY) - len(novas)} já existia(m)")
    return 0
```

E registrar os três no parser e no despachante:

```python
    status = sub.add_parser("status", help="diz quais chaves estão preenchidas, sem mostrar valor")
    status.add_argument("--plugin", default=None)

    sub.add_parser("editar", help="abre o arquivo de segredos no editor padrão")
    sub.add_parser("proteger", help="grava as regras de deny no settings do Claude Code")
```

```python
COMANDOS = {"init": cmd_init, "registrar": cmd_registrar, "status": cmd_status,
            "editar": cmd_editar, "proteger": cmd_proteger}
```

- [ ] **Step 4: Sincronizar e rodar os testes**

Run:
```bash
python scripts/sincronizar_shared.py
python scripts/testar.py
```
Expected: PASS — 49 testes OK.

- [ ] **Step 5: Conferir que nenhum subcomando devolve valor**

Run: `python plugins/kbr-core/scripts/kbr_secrets.py --help`
Expected: os cinco subcomandos listados (`init`, `registrar`, `status`, `editar`, `proteger`). **Nenhum** subcomando `obter`, `ler`, `get` ou equivalente.

- [ ] **Step 6: Commit**

```bash
git add shared/kbr_secrets.py plugins/kbr-core/scripts/kbr_secrets.py plugins/kbr-servicedesk/scripts/kbr_secrets.py plugins/kbr-core/tests/test_kbr_secrets.py
git status --short
git commit -m "$(cat <<'MSG'
feat(kbr-core): subcomandos status, editar e proteger

status diz preenchida/vazia/1Password sem nunca mostrar valor e confere
permissões, op no PATH e a regra de deny. editar abre o arquivo no editor
padrão pelo Python, sem o caminho passar por comando. proteger grava as
regras em permissions.deny preservando o resto do settings.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FxSq1YTHKimYYBJmKABcBa
MSG
)"
```

---

### Task 5: Hook `PreToolUse` que protege o arquivo de segredos

**Files:**
- Create: `plugins/kbr-core/hooks/proteger_secrets.py`
- Test: `plugins/kbr-core/tests/test_proteger_secrets.py`

**Interfaces:**
- Consumes: nada (o hook é autocontido; não importa `kbr_secrets` porque roda fora do `scripts/`).
- Produces: `decidir(tool_input: dict, base: Path) -> str | None` — devolve `None` para permitir ou o texto do motivo para negar. `caminho_base() -> Path` (mesma regra do `KBR_HOME`). Constante `MOTIVO: str`. `main() -> int` lê o JSON da entrada padrão e imprime a decisão.

- [ ] **Step 1: Escrever o teste da decisão**

`plugins/kbr-core/tests/test_proteger_secrets.py`:

```python
# -*- coding: utf-8 -*-
"""Testes da decisão do hook que protege ~/.kbr."""
import json
import io
import contextlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))
import proteger_secrets  # noqa: E402

BASE = Path("C:/Users/Fulano/.kbr") if sys.platform == "win32" else Path("/home/fulano/.kbr")


class TesteNega(unittest.TestCase):
    def nega(self, **tool_input):
        return proteger_secrets.decidir(tool_input, BASE)

    def test_read_com_til(self):
        self.assertIsNotNone(self.nega(file_path="~/.kbr/secrets.env"))

    def test_read_com_caminho_absoluto(self):
        self.assertIsNotNone(self.nega(file_path=str(BASE / "secrets.env")))

    def test_read_com_barra_invertida(self):
        self.assertIsNotNone(self.nega(file_path="C:\\Users\\Fulano\\.kbr\\secrets.env"))

    def test_read_com_maiusculas(self):
        self.assertIsNotNone(self.nega(file_path="~/.KBR/SECRETS.ENV"))

    def test_bash_com_cat(self):
        self.assertIsNotNone(self.nega(command="cat ~/.kbr/secrets.env"))

    def test_bash_com_type_do_windows(self):
        self.assertIsNotNone(self.nega(command="type %USERPROFILE%\\.kbr\\secrets.env"))

    def test_bash_com_get_content(self):
        self.assertIsNotNone(self.nega(command="Get-Content $env:USERPROFILE\\.kbr\\secrets.env"))

    def test_bash_com_redirecionamento(self):
        self.assertIsNotNone(self.nega(command="sort < ~/.kbr/secrets.env"))

    def test_bash_com_python_open(self):
        self.assertIsNotNone(
            self.nega(command="python -c \"print(open('~/.kbr/secrets.env').read())\""))

    def test_grep_na_pasta(self):
        self.assertIsNotNone(self.nega(path="~/.kbr", pattern="SDP_"))

    def test_glob_com_estrela(self):
        self.assertIsNotNone(self.nega(pattern="~/.kbr/**"))

    def test_cache_do_token(self):
        self.assertIsNotNone(self.nega(file_path="~/.kbr/cache/sdp_access_token.json"))

    def test_listar_a_pasta(self):
        self.assertIsNotNone(self.nega(command="ls -la ~/.kbr"))

    def test_motivo_e_em_portugues_e_aponta_o_status(self):
        motivo = self.nega(file_path="~/.kbr/secrets.env")
        self.assertIn("segredos", motivo.lower())
        self.assertIn("/kbr-core:secrets status", motivo)


class TestePermite(unittest.TestCase):
    def permite(self, **tool_input):
        return proteger_secrets.decidir(tool_input, BASE)

    def test_config_json(self):
        self.assertIsNone(self.permite(file_path="~/.kbr/config.json"))

    def test_config_json_absoluto(self):
        self.assertIsNone(self.permite(file_path=str(BASE / "config.json")))

    def test_script_do_plugin(self):
        self.assertIsNone(self.permite(
            command="python ${CLAUDE_PLUGIN_ROOT}/scripts/sdp_api.py listar"))

    def test_caminho_do_repo_com_kbr_no_nome(self):
        self.assertIsNone(self.permite(file_path="E:/Projetos/plugins/kbr-core/scripts/x.py"))

    def test_pasta_parecida_nao_dispara(self):
        self.assertIsNone(self.permite(file_path="~/.kbrasil/dados.txt"))

    def test_arquivo_qualquer(self):
        self.assertIsNone(self.permite(file_path="README.md"))

    def test_tool_input_vazio(self):
        self.assertIsNone(self.permite())


class TesteSaida(unittest.TestCase):
    def rodar(self, payload):
        entrada = io.StringIO(json.dumps(payload))
        captura = io.StringIO()
        anterior = sys.stdin
        sys.stdin = entrada
        try:
            with contextlib.redirect_stdout(captura):
                codigo = proteger_secrets.main()
        finally:
            sys.stdin = anterior
        return codigo, captura.getvalue()

    def test_permitir_nao_imprime_nada(self):
        codigo, saida = self.rodar({"tool_name": "Read",
                                    "tool_input": {"file_path": "README.md"}})
        self.assertEqual(codigo, 0)
        self.assertEqual(saida.strip(), "")

    def test_negar_imprime_json_do_hook(self):
        codigo, saida = self.rodar({"tool_name": "Read",
                                    "tool_input": {"file_path": "~/.kbr/secrets.env"}})
        self.assertEqual(codigo, 0)
        dados = json.loads(saida)
        especifico = dados["hookSpecificOutput"]
        self.assertEqual(especifico["hookEventName"], "PreToolUse")
        self.assertEqual(especifico["permissionDecision"], "deny")
        self.assertTrue(especifico["permissionDecisionReason"])

    def test_entrada_invalida_nao_quebra(self):
        entrada = io.StringIO("isso não é json")
        anterior = sys.stdin
        sys.stdin = entrada
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(proteger_secrets.main(), 0)
        finally:
            sys.stdin = anterior


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python scripts/testar.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'proteger_secrets'`

- [ ] **Step 3: Escrever o hook**

`plugins/kbr-core/hooks/proteger_secrets.py`:

```python
# -*- coding: utf-8 -*-
"""Hook PreToolUse do kbr-core: impede o modelo de ler o arquivo de segredos.

Recebe pela entrada padrão o JSON da ferramenta que o Claude Code vai executar e
nega qualquer chamada que mencione algo dentro de `~/.kbr/` — com a única exceção
de `config.json`, que não guarda segredo. Cobre Read, Edit, Write, Grep, Glob e
Bash (aí a inspeção é do texto inteiro do comando, então `cat`, `type`,
`Get-Content`, `sed` e redirecionamentos entram junto).

LIMITE CONHECIDO: isto é uma barreira contra exposição acidental no transcript,
não uma fronteira de segurança. Um script escrito na hora que abra o arquivo por
dentro passa — é exatamente assim que os scripts dos plugins leem os segredos.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

CAMPOS = ("file_path", "notebook_path", "path", "pattern", "command", "file_paths")

# `.kbr` como segmento completo, opcionalmente seguido do que vier depois da barra.
MARCA = re.compile(r"\.kbr(?![a-z0-9_\-])(?:/([a-z0-9_.\-/*]*))?")

MOTIVO = (
    "Esse caminho guarda os segredos pessoais do usuário (tokens de API) e está "
    "protegido pelo plugin kbr-core. Eu não leio esse arquivo: os scripts dos "
    "plugins o leem por dentro, sem que o valor passe pela conversa. Para conferir "
    "o que está preenchido sem expor nada, rode /kbr-core:secrets status. "
    "Para editar, /kbr-core:secrets editar abre o arquivo no editor do usuário."
)


def caminho_base() -> Path:
    override = os.environ.get("KBR_HOME")
    return Path(override) if override else Path.home() / ".kbr"


def normalizar(texto: str, base: Path) -> str:
    """Minúsculas, barras para frente e marcadores de home já expandidos."""
    normalizado = str(texto).replace("\\", "/").lower()
    casa = str(base.parent).replace("\\", "/").lower()
    for marcador in ("$env:userprofile", "%userprofile%", "${home}", "$home", "~"):
        normalizado = normalizado.replace(marcador, casa)
    return normalizado


def _protegido(texto: str, base: Path) -> bool:
    alvo = normalizar(str(base), base)
    if alvo in texto:
        resto = texto.split(alvo, 1)[1].lstrip("/")
        if not resto.startswith("config.json"):
            return True
    for correspondencia in MARCA.finditer(texto):
        resto = correspondencia.group(1) or ""
        if not resto.startswith("config.json"):
            return True
    return False


def decidir(tool_input: dict, base: Path) -> str | None:
    """None = pode seguir. Texto = negar, com esse motivo."""
    for campo in CAMPOS:
        bruto = (tool_input or {}).get(campo)
        if not bruto:
            continue
        valores = bruto if isinstance(bruto, list) else [bruto]
        for valor in valores:
            if _protegido(normalizar(str(valor), base), base):
                return MOTIVO
    return None


def main() -> int:
    try:
        dados = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
        return 0
    if not isinstance(dados, dict):
        return 0
    motivo = decidir(dados.get("tool_input") or {}, caminho_base())
    if motivo is None:
        return 0
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": motivo,
        }
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Rodar os testes**

Run: `python scripts/testar.py`
Expected: PASS — 49 + 24 = 73 testes OK.

- [ ] **Step 5: Conferir o hook de ponta a ponta pela entrada padrão**

Run (Bash):
```bash
echo '{"tool_name":"Read","tool_input":{"file_path":"~/.kbr/secrets.env"}}' | python plugins/kbr-core/hooks/proteger_secrets.py
echo '{"tool_name":"Read","tool_input":{"file_path":"~/.kbr/config.json"}}' | python plugins/kbr-core/hooks/proteger_secrets.py
```
Expected: a primeira imprime o JSON com `"permissionDecision": "deny"`; a segunda não imprime nada. Ambas saem com código 0.

- [ ] **Step 6: Commit**

```bash
git add plugins/kbr-core/hooks/proteger_secrets.py plugins/kbr-core/tests/test_proteger_secrets.py
git status --short
git commit -m "$(cat <<'MSG'
feat(kbr-core): hook PreToolUse que protege ~/.kbr

Nega Read, Edit, Write, Grep, Glob e Bash que mencionem algo dentro de
~/.kbr, exceto config.json. Normaliza til, %USERPROFILE%, $HOME, barras
invertidas e maiúsculas. Motivo em PT-BR apontando o /kbr-core:secrets status.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FxSq1YTHKimYYBJmKABcBa
MSG
)"
```

---

### Task 6: Empacotar o plugin `kbr-core`

**Files:**
- Create: `plugins/kbr-core/.claude-plugin/plugin.json`
- Create: `plugins/kbr-core/hooks/hooks.json`
- Create: `plugins/kbr-core/skills/secrets/SKILL.md`
- Create: `plugins/kbr-core/README.md`

**Interfaces:**
- Consumes: das Tasks 1-5 — `scripts/kbr_secrets.py` com os cinco subcomandos, `hooks/proteger_secrets.py`.
- Produces: plugin `kbr-core` versão `0.1.0` instalável, expondo a skill `/kbr-core:secrets` e registrando o hook. Nada depende dele em tempo de compilação; o `kbr-servicedesk` o declara em `dependencies`.

- [ ] **Step 1: Escrever o `plugin.json`**

```json
{
  "name": "kbr-core",
  "displayName": "KINTO — Núcleo",
  "version": "0.1.0",
  "description": "Segredos por usuário em ~/.kbr/secrets.env, com proteção contra leitura pelo modelo. Base dos demais plugins KINTO.",
  "author": { "name": "KINTO Brasil — TI" },
  "keywords": ["kinto", "secrets", "segredos", "seguranca"]
}
```

- [ ] **Step 2: Escrever o `hooks/hooks.json`**

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Read|Edit|Write|MultiEdit|NotebookEdit|Grep|Glob|Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python \"${CLAUDE_PLUGIN_ROOT}/hooks/proteger_secrets.py\""
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 3: Escrever a skill `secrets`**

`plugins/kbr-core/skills/secrets/SKILL.md`:

```markdown
---
name: secrets
description: Gerencia o arquivo de segredos pessoal em ~/.kbr/secrets.env — cria, confere o que está preenchido, abre para edição e ativa a proteção contra leitura pelo modelo. Use quando o usuário pedir "configurar secrets", "meus segredos", "credenciais", "status dos segredos", quando um plugin KINTO reclamar de credencial ausente, ou antes de qualquer tarefa que precise de token de API dos plugins KINTO.
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
| Ativar a proteção | `proteger` | Confirme que a regra entrou no settings |

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
```

- [ ] **Step 4: Escrever o `README.md` do plugin**

```markdown
# kbr-core

Base dos plugins KINTO: segredos por usuário e a proteção que impede o modelo de lê-los.

## O que ele instala

- **Skill `/kbr-core:secrets`** — cria o arquivo de segredos, diz o que está preenchido, abre
  para edição e ativa a proteção.
- **Hook `PreToolUse`** — nega qualquer tentativa de ler algo dentro de `~/.kbr/`, exceto
  `config.json`. Vale para Read, Edit, Write, Grep, Glob e Bash.

## Onde ficam os arquivos

```
~/.kbr/
├── secrets.env   segredos — protegido
├── config.json   preferências não sensíveis — legível
└── cache/        tokens de curta duração — protegido
```

No Windows, `~` é `%USERPROFILE%`. A pasta fica fora de qualquer repositório: nenhum
`git status` jamais mostra o arquivo de segredos.

## Formato do `secrets.env`

`CHAVE=valor`, uma por linha. Comentário começa com `#`. Aspas em volta do valor são
removidas. Chave repetida: vale a última.

Quem tem o **1Password CLI** pode escrever a referência no lugar do valor:

```dotenv
SDP_CLIENT_ID=op://Cofre/Nome do item/campo
```

O valor é resolvido na hora com `op read` e cacheado pelo tempo do processo. Quando um script
precisa gravar numa chave assim, ele grava no cofre com `op item edit` — a referência nunca
vira valor literal no arquivo. Quem não usa 1Password não precisa de nada disso.

## Ordem de resolução

1. Variável de ambiente de mesmo nome — automação, CI e Claude Code na nuvem.
2. `~/.kbr/secrets.env`.

## Limites da proteção

O hook e a regra `deny` são **barreiras contra exposição acidental no transcript**, não uma
fronteira de segurança:

- Um script escrito na hora que abra o arquivo por dentro passa — é exatamente assim que os
  scripts dos plugins leem os segredos.
- Em repouso, o arquivo tem a mesma postura de `~/.aws/credentials`: protegido por permissão
  do sistema de arquivos, não criptografado.
- Se o Python não estiver no `PATH`, o hook falha e o Claude Code segue sem bloquear. O
  `status` avisa quando isso acontece.

A ameaça que isso trata é segredo vazando para o contexto, para log ou para o git — não um
atacante com acesso à máquina.

## Pré-requisitos

Python 3.10 ou superior no `PATH`. Nada de `pip install`.
```

- [ ] **Step 5: Validar o plugin**

Run: `claude plugin validate plugins/kbr-core`
Expected: `Validation passed` (avisos são aceitáveis; erro não).

- [ ] **Step 6: Commit**

```bash
git add plugins/kbr-core/.claude-plugin/plugin.json plugins/kbr-core/hooks/hooks.json plugins/kbr-core/skills/secrets/SKILL.md plugins/kbr-core/README.md
git status --short
git commit -m "$(cat <<'MSG'
feat(kbr-core): empacotar o plugin — manifesto, hook, skill e README

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FxSq1YTHKimYYBJmKABcBa
MSG
)"
```

---

### Task 7: Marketplace, scripts de validação e CI

**Files:**
- Create: `.claude-plugin/marketplace.json`
- Create: `scripts/validar.py`
- Create: `scripts/criar_tag.py`
- Create: `.github/workflows/validar.yml`
- Create: `README.md`

**Interfaces:**
- Consumes: da Task 6 — o plugin `kbr-core` já válido. O `kbr-servicedesk` ainda não existe: o `marketplace.json` já o declara e `validar.py` **pula** plugin cujo `plugin.json` ainda não existe, avisando.
- Produces: marketplace `kinto-brasil`; `scripts/validar.py` (código 1 se algum plugin existente falhar); `scripts/criar_tag.py <plugin>` (lê a versão do `plugin.json` e cria a tag `<plugin>--v<versão>`, recusando se já existir).

- [ ] **Step 1: Escrever o `marketplace.json`**

```json
{
  "name": "kinto-brasil",
  "description": "Plugins do Claude Code da KINTO Brasil: documentação, ServiceDesk, design systems",
  "owner": { "name": "KINTO Brasil — TI" },
  "plugins": [
    {
      "name": "kbr-core",
      "description": "Segredos por usuário em ~/.kbr/secrets.env e proteção contra leitura pelo modelo",
      "source": "./plugins/kbr-core",
      "category": "productivity"
    },
    {
      "name": "kbr-servicedesk",
      "description": "Gestor de chamados do ServiceDesk Plus por menu, com wizard de configuração",
      "source": "./plugins/kbr-servicedesk",
      "category": "productivity"
    }
  ]
}
```

- [ ] **Step 2: Escrever `scripts/validar.py`**

```python
# -*- coding: utf-8 -*-
"""Roda `claude plugin validate` em cada plugin do marketplace."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CATALOGO = RAIZ / ".claude-plugin" / "marketplace.json"


def main() -> int:
    dados = json.loads(CATALOGO.read_text(encoding="utf-8"))
    falhas: list[str] = []
    for entrada in dados.get("plugins", []):
        origem = entrada.get("source")
        if not isinstance(origem, str) or not origem.startswith("./"):
            print(f"pulando {entrada.get('name')}: fonte não é uma pasta deste repositório")
            continue
        pasta = RAIZ / origem
        if not (pasta / ".claude-plugin" / "plugin.json").is_file():
            print(f"AVISO: {entrada['name']} ainda não existe em {origem} — pulando")
            continue
        print(f"validando {entrada['name']}...")
        try:
            processo = subprocess.run(["claude", "plugin", "validate", str(pasta)],
                                      capture_output=True, text=True)
        except FileNotFoundError:
            print("ERRO: o comando 'claude' não está no PATH")
            return 1
        print((processo.stdout or "").strip() or (processo.stderr or "").strip())
        if processo.returncode != 0:
            falhas.append(entrada["name"])
    if falhas:
        print(f"\nfalharam: {', '.join(falhas)}")
        return 1
    print("\ntodos os plugins existentes passaram na validação")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Escrever `scripts/criar_tag.py`**

```python
# -*- coding: utf-8 -*-
"""Cria a tag de publicação de um plugin: <plugin>--v<versão>.

É esse padrão de tag que o Claude Code lê para detectar que há versão nova de um
plugin num marketplace baseado em git.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plugin")
    parser.add_argument("--push", action="store_true", help="dá push da tag no origin")
    args = parser.parse_args()

    manifesto = RAIZ / "plugins" / args.plugin / ".claude-plugin" / "plugin.json"
    if not manifesto.is_file():
        print(f"plugin não encontrado: {args.plugin}")
        return 1
    versao = json.loads(manifesto.read_text(encoding="utf-8")).get("version")
    if not versao:
        print(f"o plugin.json de {args.plugin} não tem campo 'version'")
        return 1

    tag = f"{args.plugin}--v{versao}"
    existentes = subprocess.run(["git", "tag", "--list", tag], capture_output=True,
                                text=True, cwd=RAIZ).stdout.split()
    if tag in existentes:
        print(f"a tag {tag} já existe. suba a versão no plugin.json antes de publicar.")
        return 1

    subprocess.run(["git", "tag", tag], check=True, cwd=RAIZ)
    print(f"tag criada: {tag}")
    if args.push:
        subprocess.run(["git", "push", "origin", tag], check=True, cwd=RAIZ)
        print(f"tag publicada no origin: {tag}")
    else:
        print(f"para publicar: git push origin {tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Escrever a CI**

`.github/workflows/validar.yml`:

```yaml
name: validar

on:
  push:
    branches: [main]
  pull_request:

jobs:
  validar:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Cópias vendorizadas em sincronia
        run: python scripts/verificar_shared.py

      - name: Testes dos plugins
        run: python scripts/testar.py

      - name: Instalar o Claude Code CLI
        run: npm install -g @anthropic-ai/claude-code

      - name: Validar plugins e marketplace
        run: python scripts/validar.py
```

- [ ] **Step 5: Escrever o `README.md` da raiz**

```markdown
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
```

- [ ] **Step 6: Validar e rodar tudo**

Run:
```bash
python scripts/verificar_shared.py
python scripts/testar.py
python scripts/validar.py
```
Expected: sincronia OK; 73 testes PASS; `kbr-core` validado e `kbr-servicedesk` pulado com aviso.

- [ ] **Step 7: Commit**

```bash
git add .claude-plugin/marketplace.json scripts/validar.py scripts/criar_tag.py .github/workflows/validar.yml README.md
git status --short
git commit -m "$(cat <<'MSG'
feat: marketplace kinto-brasil, scripts de validação e CI

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FxSq1YTHKimYYBJmKABcBa
MSG
)"
```

---

### Task 8: `sdp_api.py` — configuração, erros traduzidos, autenticação e cache

**Files:**
- Create: `plugins/kbr-servicedesk/scripts/sdp_api.py`
- Test: `plugins/kbr-servicedesk/tests/test_sdp_api.py`

**Interfaces:**
- Consumes: da Task 1-2 — `kbr_secrets.obter`, `kbr_secrets.gravar`, `kbr_secrets.caminho_config`, `kbr_secrets.caminho_cache`.
- Produces:
  - `ler_config() -> dict` e `gravar_config(dados: dict) -> None` — leem/gravam a chave `servicedesk` de `~/.kbr/config.json`, com os padrões preenchidos.
  - `PADRAO_CONFIG: dict` com `data_center`, `api_base`, `token_url`, `tecnico_nome`, `tecnico_email`.
  - `class ErroSDP(Exception)` — a mensagem já é o texto em PT-BR para o usuário.
  - `traduzir(origem: str, corpo: dict, http: int = 0) -> str`.
  - `access_token(forcar: bool = False) -> str` — usa e alimenta `~/.kbr/cache/sdp_access_token.json`, renovando só quando faltam menos de 5 minutos.
  - `chamar(metodo: str, caminho: str, input_data: dict | None, token: str) -> tuple[int, dict]`.
  - `_abrir(requisicao)` — ponto único de rede, substituído nos testes.

- [ ] **Step 1: Escrever os testes de config, erros e token**

`plugins/kbr-servicedesk/tests/test_sdp_api.py`:

```python
# -*- coding: utf-8 -*-
"""Testes do acesso à API do ServiceDesk Plus."""
import io
import json
import os
import sys
import tempfile
import time
import unittest
import urllib.error
from pathlib import Path

RAIZ_PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ_PLUGIN / "scripts"))
import kbr_secrets  # noqa: E402
import sdp_api  # noqa: E402


class RespostaFalsa(io.BytesIO):
    def __init__(self, corpo, status=200):
        super().__init__(json.dumps(corpo).encode("utf-8"))
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class RedeFalsa:
    """Substitui sdp_api._abrir. Devolve as respostas na ordem da fila."""

    def __init__(self, *respostas):
        self.fila = list(respostas)
        self.chamadas = []

    def __call__(self, requisicao, timeout=None):
        self.chamadas.append({
            "url": requisicao.full_url,
            "metodo": requisicao.get_method(),
            "corpo": (requisicao.data or b"").decode("utf-8"),
            "cabecalhos": dict(requisicao.header_items()),
        })
        proxima = self.fila.pop(0)
        if isinstance(proxima, Exception):
            raise proxima
        return RespostaFalsa(proxima)


class BaseSDP(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name) / ".kbr"
        (self.base / "cache").mkdir(parents=True)
        self._env = dict(os.environ)
        os.environ["KBR_HOME"] = str(self.base)
        kbr_secrets._cache_op.clear()
        kbr_secrets.caminho_arquivo().write_text(
            "SDP_CLIENT_ID=cid\nSDP_CLIENT_SECRET=csec\nSDP_REFRESH_TOKEN=rtok\n",
            encoding="utf-8")
        sdp_api.gravar_config({"tecnico_nome": "Fulano de Tal",
                               "tecnico_email": "fulano@kintomobility.com.br"})
        self._abrir_original = sdp_api._abrir

    def tearDown(self):
        sdp_api._abrir = self._abrir_original
        os.environ.clear()
        os.environ.update(self._env)
        self.tmp.cleanup()

    def rede(self, *respostas):
        falsa = RedeFalsa(*respostas)
        sdp_api._abrir = falsa
        return falsa


class TesteConfig(BaseSDP):
    def test_preenche_os_padroes(self):
        config = sdp_api.ler_config()
        self.assertEqual(config["data_center"], "us")
        self.assertIn("sdpondemand.manageengine.com", config["api_base"])
        self.assertIn("accounts.zoho.com", config["token_url"])

    def test_preserva_o_que_ja_estava(self):
        self.assertEqual(sdp_api.ler_config()["tecnico_nome"], "Fulano de Tal")

    def test_nao_mexe_em_outras_chaves_do_config(self):
        caminho = kbr_secrets.caminho_config()
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        dados["outro_plugin"] = {"x": 1}
        caminho.write_text(json.dumps(dados), encoding="utf-8")
        sdp_api.gravar_config({"tecnico_nome": "Outro"})
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        self.assertEqual(dados["outro_plugin"], {"x": 1})


class TesteToken(BaseSDP):
    def test_troca_refresh_por_access(self):
        rede = self.rede({"access_token": "acc-1", "expires_in": 3600})
        self.assertEqual(sdp_api.access_token(), "acc-1")
        chamada = rede.chamadas[0]
        self.assertEqual(chamada["metodo"], "POST")
        self.assertIn("accounts.zoho.com", chamada["url"])
        self.assertIn("grant_type=refresh_token", chamada["corpo"])
        self.assertIn("rtok", chamada["corpo"])

    def test_reusa_o_token_em_cache(self):
        rede = self.rede({"access_token": "acc-1", "expires_in": 3600})
        sdp_api.access_token()
        sdp_api.access_token()
        self.assertEqual(len(rede.chamadas), 1)

    def test_renova_quando_esta_perto_de_vencer(self):
        caminho = kbr_secrets.caminho_cache() / "sdp_access_token.json"
        caminho.write_text(json.dumps({"access_token": "velho",
                                       "expira_em": time.time() + 60}), encoding="utf-8")
        self.rede({"access_token": "novo", "expires_in": 3600})
        self.assertEqual(sdp_api.access_token(), "novo")

    def test_cache_nao_guarda_refresh_token(self):
        self.rede({"access_token": "acc-1", "expires_in": 3600})
        sdp_api.access_token()
        bruto = (kbr_secrets.caminho_cache() / "sdp_access_token.json").read_text(
            encoding="utf-8")
        self.assertNotIn("rtok", bruto)

    def test_segredo_ausente_vira_mensagem_do_wizard(self):
        kbr_secrets.caminho_arquivo().write_text("SDP_CLIENT_ID=\n", encoding="utf-8")
        with self.assertRaises(sdp_api.ErroSDP) as caso:
            sdp_api.access_token()
        self.assertIn("configurar", str(caso.exception))


class TesteErros(unittest.TestCase):
    def test_codigo_expirado(self):
        texto = sdp_api.traduzir("zoho", {"error": "invalid_code"})
        self.assertIn("10 minutos", texto)

    def test_cliente_invalido(self):
        texto = sdp_api.traduzir("zoho", {"error": "invalid_client"})
        self.assertIn("Client ID", texto)

    def test_cliente_invalido_menciona_o_console_americano(self):
        texto = sdp_api.traduzir("zoho", {"error": "invalid_client"})
        self.assertIn("api-console.zoho.com", texto)

    def test_escopo_faltando(self):
        texto = sdp_api.traduzir("zoho", {"error": "invalid_scope"})
        self.assertIn("escopo", texto.lower())

    def test_http_401(self):
        texto = sdp_api.traduzir("sdp", {}, http=401)
        self.assertIn("revogado", texto.lower())

    def test_http_403(self):
        texto = sdp_api.traduzir("sdp", {}, http=403)
        self.assertIn("permissão", texto.lower())

    def test_rede(self):
        texto = sdp_api.traduzir("rede", {})
        self.assertIn("conexão", texto.lower())

    def test_erro_desconhecido_nao_quebra(self):
        texto = sdp_api.traduzir("sdp", {"response_status": {"messages": [
            {"message": "algo inesperado"}]}}, http=400)
        self.assertIn("algo inesperado", texto)

    def test_nenhuma_mensagem_vaza_token(self):
        texto = sdp_api.traduzir("zoho", {"error": "invalid_client",
                                          "access_token": "NAO-DEVE-APARECER"})
        self.assertNotIn("NAO-DEVE-APARECER", texto)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python scripts/testar.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdp_api'`

- [ ] **Step 3: Escrever a primeira metade de `sdp_api.py`**

```python
# -*- coding: utf-8 -*-
"""Acesso à API do ServiceDesk Plus Cloud (SDP) v3, com OAuth Zoho.

Os segredos vêm de kbr_secrets (arquivo ~/.kbr/secrets.env ou 1Password) e NUNCA
são impressos. Toda saída é JSON em UTF-8, sem credenciais e sem cabeçalhos HTTP.
Nenhuma operação de escrita acontece sem a flag --confirmar.
"""
from __future__ import annotations

import argparse
import html as _html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kbr_secrets  # noqa: E402

CHAVE_CONFIG = "servicedesk"
ACEITA = "application/vnd.manageengine.sdp.v3+json"
MARGEM_RENOVACAO = 300  # segundos antes do vencimento em que já renovamos

PADRAO_CONFIG = {
    "tecnico_nome": "",
    "tecnico_email": "",
    "data_center": "us",
    "api_base": "https://sdpondemand.manageengine.com/api/v3",
    "token_url": "https://accounts.zoho.com/oauth/v2/token",
}

STATUS_DE_ESPERA = {"on hold", "aguardando aprovacao", "aguardando aprovação", "em observacao",
                    "em observação"}

ESCOPOS = ["SDPOnDemand.requests.READ", "SDPOnDemand.requests.CREATE",
           "SDPOnDemand.requests.UPDATE"]


class ErroSDP(Exception):
    """A mensagem já é o texto em PT-BR pronto para o usuário."""


# --------------------------------------------------------------------------- config

def ler_config() -> dict:
    caminho = kbr_secrets.caminho_config()
    dados: dict = {}
    if caminho.exists():
        try:
            dados = json.loads(caminho.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            dados = {}
    config = dict(PADRAO_CONFIG)
    config.update(dados.get(CHAVE_CONFIG) or {})
    return config


def gravar_config(novos: dict) -> None:
    caminho = kbr_secrets.caminho_config()
    dados: dict = {}
    if caminho.exists():
        try:
            dados = json.loads(caminho.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            dados = {}
    atual = dict(PADRAO_CONFIG)
    atual.update(dados.get(CHAVE_CONFIG) or {})
    atual.update(novos)
    dados[CHAVE_CONFIG] = atual
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")


# --------------------------------------------------------------------------- erros

_ZOHO = {
    "invalid_code": ("O código de autorização expirou ou já foi usado. Ele vale 10 minutos. "
                     "Gere outro no console (passo 5 do wizard) e cole de novo."),
    "invalid_client": ("Client ID ou Client Secret incorretos. Confira se copiou os dois "
                       "inteiros, sem espaços (passo 4 do wizard). Se o cliente foi criado "
                       "no console de outro país, refaça no americano: api-console.zoho.com."),
    "invalid_scope": ("O cliente não tem os escopos necessários. Gere um novo código com a "
                      "lista completa de escopos (passo 5 do wizard)."),
    "invalid_grant": ("O acesso foi revogado no 1Password ou na Zoho. Refaça os passos 5 e 6 "
                      "do wizard para gerar um novo acesso."),
}

_HTTP = {
    401: ("O acesso foi revogado ou o token venceu. Refaça os passos 5 e 6 do wizard "
          "(/kbr-servicedesk:configurar)."),
    403: ("O cliente não tem permissão para esta operação. Gere um novo código com a lista "
          "completa de escopos (passo 5 do wizard)."),
    404: "O ServiceDesk não encontrou esse chamado. Confira o número.",
    429: "O ServiceDesk recusou por excesso de chamadas. Espere um minuto e tente de novo.",
}


def _mensagens_do_sdp(corpo: dict) -> str:
    mensagens = ((corpo.get("response_status") or {}).get("messages")) or []
    textos = [str(item.get("message")) for item in mensagens if item.get("message")]
    return " ".join(textos)


def traduzir(origem: str, corpo: dict, http: int = 0) -> str:
    """Transforma um erro da Zoho ou do SDP em texto acionável em PT-BR."""
    corpo = corpo if isinstance(corpo, dict) else {}
    if origem == "rede":
        return ("Não consegui falar com o ServiceDesk. Confira a conexão e a VPN, se você "
                "usa, e tente de novo.")
    if origem == "zoho":
        codigo = str(corpo.get("error") or "").strip()
        if codigo in _ZOHO:
            return _ZOHO[codigo]
        if codigo:
            return (f"A Zoho recusou a autenticação ({codigo}). Refaça os passos 4 a 6 do "
                    f"wizard (/kbr-servicedesk:configurar).")
        return ("A Zoho não devolveu um token de acesso. Refaça os passos 5 e 6 do wizard "
                "(/kbr-servicedesk:configurar).")
    if http in _HTTP:
        return _HTTP[http]
    detalhe = _mensagens_do_sdp(corpo)
    if detalhe:
        return f"O ServiceDesk recusou a operação (HTTP {http}): {detalhe}"
    return (f"O ServiceDesk respondeu HTTP {http} e não explicou o motivo. Tente de novo; "
            f"se persistir, abra o chamado pelo portal.")


# --------------------------------------------------------------------------- rede

def _abrir(requisicao, timeout=90):
    """Ponto único de rede — os testes substituem esta função."""
    return urllib.request.urlopen(requisicao, timeout=timeout)


def _postar_form(url: str, campos: dict) -> tuple[int, dict]:
    dados = urllib.parse.urlencode(campos).encode("utf-8")
    requisicao = urllib.request.Request(url, data=dados, method="POST")
    try:
        with _abrir(requisicao, timeout=60) as resposta:
            return getattr(resposta, "status", 200), json.loads(resposta.read())
    except urllib.error.HTTPError as erro:
        try:
            return erro.code, json.loads(erro.read())
        except (json.JSONDecodeError, ValueError):
            return erro.code, {}
    except urllib.error.URLError:
        raise ErroSDP(traduzir("rede", {})) from None


def _caminho_cache_token() -> Path:
    return kbr_secrets.caminho_cache() / "sdp_access_token.json"


def _token_em_cache() -> str | None:
    caminho = _caminho_cache_token()
    if not caminho.exists():
        return None
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if float(dados.get("expira_em", 0)) - time.time() < MARGEM_RENOVACAO:
        return None
    return dados.get("access_token") or None


def _guardar_token(token: str, expira_em_segundos: int) -> None:
    caminho = _caminho_cache_token()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps({
        "access_token": token,
        "expira_em": time.time() + max(int(expira_em_segundos or 3600), 60),
    }), encoding="utf-8")


def _segredo(nome: str) -> str:
    try:
        return kbr_secrets.obter(nome)
    except kbr_secrets.ErroSegredo as erro:
        raise ErroSDP(str(erro)) from None


def access_token(forcar: bool = False) -> str:
    if not forcar:
        guardado = _token_em_cache()
        if guardado:
            return guardado
    config = ler_config()
    status, corpo = _postar_form(config["token_url"], {
        "grant_type": "refresh_token",
        "client_id": _segredo("SDP_CLIENT_ID"),
        "client_secret": _segredo("SDP_CLIENT_SECRET"),
        "refresh_token": _segredo("SDP_REFRESH_TOKEN"),
    })
    token = (corpo or {}).get("access_token")
    if status >= 300 or not token:
        raise ErroSDP(traduzir("zoho", corpo or {}))
    _guardar_token(token, (corpo or {}).get("expires_in", 3600))
    return token


def chamar(metodo: str, caminho: str, input_data: dict | None, token: str) -> tuple[int, dict]:
    config = ler_config()
    url = config["api_base"] + caminho
    dados = None
    if metodo == "GET":
        if input_data:
            url += "?" + urllib.parse.urlencode(
                {"input_data": json.dumps(input_data, ensure_ascii=False)})
    else:
        dados = urllib.parse.urlencode(
            {"input_data": json.dumps(input_data or {}, ensure_ascii=False)}).encode("utf-8")
    requisicao = urllib.request.Request(url, data=dados, method=metodo)
    requisicao.add_header("Authorization", f"Zoho-oauthtoken {token}")
    requisicao.add_header("Accept", ACEITA)
    try:
        with _abrir(requisicao) as resposta:
            return getattr(resposta, "status", 200), json.loads(
                resposta.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as erro:
        try:
            return erro.code, json.loads(erro.read().decode("utf-8", "replace"))
        except (json.JSONDecodeError, ValueError):
            return erro.code, {}
    except urllib.error.URLError:
        raise ErroSDP(traduzir("rede", {})) from None
```

- [ ] **Step 4: Rodar os testes**

Run: `python scripts/testar.py`
Expected: PASS — 73 + 21 = 94 testes OK.

- [ ] **Step 5: Commit**

```bash
git add plugins/kbr-servicedesk/scripts/sdp_api.py plugins/kbr-servicedesk/tests/test_sdp_api.py
git status --short
git commit -m "$(cat <<'MSG'
feat(kbr-servicedesk): config, erros traduzidos e OAuth com cache de token

Segredos vêm do kbr_secrets e nunca são impressos. O access token é
guardado em ~/.kbr/cache e renovado só quando faltam menos de 5 minutos;
o refresh token nunca entra no cache. Erros da Zoho e do SDP viram texto
acionável em PT-BR.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FxSq1YTHKimYYBJmKABcBa
MSG
)"
```

---

**Nota para quem executa:** as Tasks 9 a 15 estão no arquivo companheiro
`2026-09-13-fundacao-servicedesk-parte-2.md`, escrito na sequência. Elas cobrem os comandos de
leitura e escrita do `sdp_api.py`, as duas skills do `kbr-servicedesk`, o guia HTML e o
fechamento com as tags de versão.
