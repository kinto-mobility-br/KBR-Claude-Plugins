#!/usr/bin/env python3
"""
Resolve o config efetivo de marca do `kbr-docs` — por enquanto, só o parser de
YAML (movido de `aplicar_marca.py`). A cascata de três níveis entra na Task 2.
"""
from __future__ import annotations

from pathlib import Path


# --------------------------------------------------------------------- YAML --
def _dividir_comentario(linha: str) -> str:
    """Corta um comentário à direita (# fora de aspas). # dentro de "..." não conta."""
    dentro_de_aspas = False
    for i, ch in enumerate(linha):
        if ch == '"':
            dentro_de_aspas = not dentro_de_aspas
        elif ch == '#' and not dentro_de_aspas:
            return linha[:i]
    return linha


def _valor_escalar(bruto: str):
    """None quando a linha só abre um mapeamento aninhado (ex.: "marca:", sem valor)."""
    bruto = bruto.strip()
    if not bruto:
        return None
    if bruto.startswith('"') and bruto.endswith('"') and len(bruto) >= 2:
        return bruto[1:-1].replace('\\"', '"')
    minusculo = bruto.casefold()
    if minusculo in ('true', 'yes', 'on'):
        return True
    if minusculo in ('false', 'no', 'off'):
        return False
    return bruto


def carregar_yaml_simples(texto: str) -> dict:
    """
    Lê o subconjunto de YAML que `.docs-brand.yml` usa: mapeamentos aninhados até 3
    níveis, indentação de 2 espaços, valores entre aspas duplas ou booleano (`true`/
    `yes`/`on` e `false`/`no`/`off`, sem diferenciar maiúsculas), comentários com `#`
    (linha inteira ou à direita do valor, fora de aspas).

    Deliberadamente NÃO é um parser de YAML geral — feito para não exigir PyYAML (e
    portanto nenhum `pip install`) de quem usa o plugin. Não suporta lista, âncora,
    bloco multilinha, aspas simples nem chave com dois-pontos dentro do próprio nome.
    """
    raiz: dict = {}
    pilha: list[tuple[int, dict]] = [(-1, raiz)]
    for linha_bruta in texto.splitlines():
        sem_comentario = _dividir_comentario(linha_bruta)
        if not sem_comentario.strip():
            continue
        indent = len(sem_comentario) - len(sem_comentario.lstrip(' '))
        chave, _, resto = sem_comentario.strip().partition(':')
        chave = chave.strip()
        if not chave:
            continue
        while indent <= pilha[-1][0]:
            pilha.pop()
        atual = pilha[-1][1]
        valor = _valor_escalar(resto)
        if valor is None:
            novo: dict = {}
            atual[chave] = novo
            pilha.append((indent, novo))
        else:
            atual[chave] = valor
    return raiz


def carregar_yaml(caminho: Path) -> dict:
    return carregar_yaml_simples(caminho.read_text(encoding='utf-8-sig'))
