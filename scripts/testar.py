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
