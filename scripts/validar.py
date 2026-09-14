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
