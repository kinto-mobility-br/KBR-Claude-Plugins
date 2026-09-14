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


def _rodar_git(comando: list[str]) -> subprocess.CompletedProcess[str]:
    """Roda um comando git no repositório, capturando a saída sem levantar em erro.

    `check=True` sem tratamento estoura um `CalledProcessError` com traceback em
    inglês — errado para o passo em que um mantenedor publica uma versão. Aqui o
    chamador decide o que fazer com `returncode` e mostra o próprio stderr do git.
    """
    return subprocess.run(comando, cwd=RAIZ, capture_output=True, text=True)


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

    resultado = _rodar_git(["git", "tag", tag])
    if resultado.returncode != 0:
        erro = (resultado.stderr or resultado.stdout or "").strip()
        print(f"ERRO: não consegui criar a tag {tag} — {erro}")
        return 1
    print(f"tag criada: {tag}")

    if args.push:
        resultado = _rodar_git(["git", "push", "origin", tag])
        if resultado.returncode != 0:
            erro = (resultado.stderr or resultado.stdout or "").strip()
            print(f"ERRO: não consegui publicar a tag {tag} no origin — {erro}")
            return 1
        print(f"tag publicada no origin: {tag}")
    else:
        print(f"para publicar: git push origin {tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
