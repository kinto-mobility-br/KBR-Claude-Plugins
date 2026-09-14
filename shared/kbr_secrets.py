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
import shutil
import subprocess
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


def _rodar_op(argumentos: list[str]):
    """Chama o 1Password CLI. Isolado numa função para os testes substituírem."""
    return subprocess.run(["op", *argumentos], capture_output=True, text=True)


def op_disponivel() -> bool:
    return shutil.which("op") is not None


def _partes_op(referencia: str, nome: str) -> tuple[str, str, str]:
    partes = referencia[len(PREFIXO_OP):].split("/")
    if len(partes) != 3 or not all(parte.strip() for parte in partes):
        raise SegredoInacessivel(
            nome, "referência mal formada (esperado op://cofre/item/campo)")
    return partes[0].strip(), partes[1].strip(), partes[2].strip()


def _motivo_da_falha(processo) -> str:
    linhas = (processo.stderr or "").strip().splitlines()
    return linhas[0] if linhas else f"o comando op saiu com código {processo.returncode}"


def _executar_op(argumentos: list[str], nome: str):
    """Chama o 1Password CLI e traduz as duas falhas possíveis. Devolve o processo."""
    try:
        processo = _rodar_op(argumentos)
    except FileNotFoundError:
        raise SegredoInacessivel(
            nome, "o comando 'op' não está instalado ou não está no PATH") from None
    if processo.returncode != 0:
        raise SegredoInacessivel(nome, _motivo_da_falha(processo))
    return processo


def _resolver_op(referencia: str, nome: str) -> str:
    if referencia in _cache_op:
        return _cache_op[referencia]
    _partes_op(referencia, nome)  # valida o formato antes de chamar o op
    processo = _executar_op(["read", referencia], nome)
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
    _executar_op(["item", "edit", item, "--vault", cofre, f"{campo}={valor}"], nome)


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
