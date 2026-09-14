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
