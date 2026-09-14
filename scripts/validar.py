# -*- coding: utf-8 -*-
"""Roda `claude plugin validate` em cada plugin do marketplace."""
from __future__ import annotations

import json
import shutil
import subprocess
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


def main() -> int:
    dados = json.loads(CATALOGO.read_text(encoding="utf-8"))
    executavel = caminho_do_claude()
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
        if not executavel:
            print("ERRO: o comando 'claude' não está no PATH")
            return 1
        try:
            processo = subprocess.run([executavel, "plugin", "validate", str(pasta)],
                                      capture_output=True, text=True)
        except OSError as erro:
            print(f"ERRO: não consegui rodar o Claude Code CLI ({erro})")
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
