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
