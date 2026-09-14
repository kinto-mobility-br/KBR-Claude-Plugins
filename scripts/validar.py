# -*- coding: utf-8 -*-
"""Roda `claude plugin validate --strict` em cada plugin do marketplace e no
marketplace em si."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CATALOGO = RAIZ / ".claude-plugin" / "marketplace.json"


def caminho_do_claude() -> str | None:
    """Resolve o executável do Claude Code.

    No Windows o comando instalado pelo npm é `claude.CMD`, e o `subprocess.run`
    não consulta o PATHEXT: chamar só "claude" levanta FileNotFoundError mesmo com
    o CLI instalado e funcionando. O `shutil.which` resolve a extensão certa.
    """
    return shutil.which("claude")


def validar(executavel: str, pasta: Path, rotulo: str) -> bool:
    """Roda `claude plugin validate --strict` numa pasta e devolve se passou.

    O `--strict` trata avisos como erro — é a própria recomendação do CLI para CI.
    A codificação é fixada em UTF-8 porque o console do Windows costuma estar em
    cp1252, e o CLI sempre emite UTF-8; sem isso os símbolos ✔/✘ viram mojibake.
    """
    print(f"\n=== validando {rotulo} ===")
    try:
        processo = subprocess.run(
            [executavel, "plugin", "validate", "--strict", str(pasta)],
            capture_output=True, encoding="utf-8", errors="replace",
        )
    except OSError as erro:
        print(f"ERRO: não consegui rodar o Claude Code CLI ({erro})")
        return False
    print((processo.stdout or "").strip() or (processo.stderr or "").strip())
    return processo.returncode == 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        # console do Windows costuma estar em cp1252; sem isso, o ✔/✘ do CLI
        # (decodificado em UTF-8 acima) não tem como sair no print().
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    dados = json.loads(CATALOGO.read_text(encoding="utf-8"))
    executavel = caminho_do_claude()
    if not executavel:
        print("ERRO: o comando 'claude' não está no PATH")
        return 1

    falhas: list[str] = []

    if not validar(executavel, RAIZ, "marketplace (kinto-brasil)"):
        falhas.append("marketplace")

    for entrada in dados.get("plugins", []):
        origem = entrada.get("source")
        if not isinstance(origem, str) or not origem.startswith("./"):
            print(f"pulando {entrada.get('name')}: fonte não é uma pasta deste repositório")
            continue
        pasta = RAIZ / origem
        if not (pasta / ".claude-plugin" / "plugin.json").is_file():
            print(f"AVISO: {entrada['name']} ainda não existe em {origem} — pulando")
            continue
        if not validar(executavel, pasta, f"plugin {entrada['name']}"):
            falhas.append(entrada["name"])

    if falhas:
        print(f"\nfalharam: {', '.join(falhas)}")
        return 1
    print("\nmarketplace e todos os plugins existentes passaram na validação")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
