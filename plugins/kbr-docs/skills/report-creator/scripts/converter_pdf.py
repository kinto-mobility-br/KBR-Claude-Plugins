#!/usr/bin/env python3
"""
Converte um arquivo HTML local em PDF, chamando (via subprocess) um navegador
Chromium já instalado na máquina em modo headless — sem Playwright, sem
nenhuma dependência Python nova.

Uso:
    python converter_pdf.py <entrada.html> [saida.pdf]

Sem `saida.pdf`, usa o mesmo nome de `entrada.html` com a extensão trocada
pra `.pdf`, na mesma pasta. O `@media print` do CSS da própria página entra
em ação sozinho — é o mesmo comportamento de apertar Ctrl+P no navegador.

Navegador: acha Edge/Chrome nos caminhos padrão do Windows ou no PATH. Numa
máquina sem nenhum dos dois nos lugares de sempre, aponte pro executável com
a variável de ambiente KBR_DOCS_BROWSER.

Códigos de saída: 0 = PDF gerado; 1 = erro (entrada, navegador ou conversão —
mensagem em stderr explica qual); 2 = uso incorreto (sem argumento).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

CAMINHOS_PADRAO_WINDOWS = (
    r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
    r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
    r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files\Google\Chrome\Application\chrome.exe',
)

NOMES_NO_PATH = ('msedge', 'chrome', 'chromium')


class ErroNavegadorNaoEncontrado(Exception):
    pass


class ErroConversao(Exception):
    pass


def achar_navegador() -> Path:
    """
    Acha um navegador Chromium instalado, nesta ordem: variável de ambiente
    KBR_DOCS_BROWSER, caminhos padrão do Windows (Edge, depois Chrome), e por
    fim o PATH. Levanta ErroNavegadorNaoEncontrado (mensagem em PT-BR) se não
    achar nada.

    KBR_DOCS_BROWSER, quando definida, é AUTORITATIVA — não cai pros outros
    métodos se o caminho nela não existir; isso é erro de configuração, não
    "tenta o resto".
    """
    override = os.environ.get('KBR_DOCS_BROWSER')
    if override:
        caminho = Path(override)
        if caminho.exists():
            return caminho
        raise ErroNavegadorNaoEncontrado(
            f'KBR_DOCS_BROWSER aponta para um caminho que não existe: {override}')

    for bruto in CAMINHOS_PADRAO_WINDOWS:
        caminho = Path(bruto)
        if caminho.exists():
            return caminho

    for nome in NOMES_NO_PATH:
        achado = shutil.which(nome)
        if achado:
            return Path(achado)

    tentativas = '\n'.join(f'  - {c}' for c in CAMINHOS_PADRAO_WINDOWS)
    tentativas += '\n' + '\n'.join(f'  - shutil.which("{n}")' for n in NOMES_NO_PATH)
    raise ErroNavegadorNaoEncontrado(
        f'Não achei nenhum navegador Chromium instalado. Tentei:\n{tentativas}\n\n'
        f'Defina KBR_DOCS_BROWSER com o caminho do executável, se tiver um instalado '
        f'em lugar não padrão.')


def converter(entrada: Path, saida: Path, navegador: Path) -> None:
    """
    Roda `navegador` em modo headless pra gerar `saida` a partir de `entrada`.
    Levanta ErroConversao (mensagem em PT-BR) se a entrada não existir, se
    `saida` for o mesmo arquivo que `entrada`, se o processo falhar, ou se
    não produzir o arquivo esperado.
    """
    entrada = entrada.resolve()
    saida = saida.resolve()

    if not entrada.exists():
        raise ErroConversao(f'Entrada não existe: {entrada}.')

    if saida == entrada:
        raise ErroConversao(f'A saída não pode ser o mesmo arquivo da entrada: {saida}.')

    if saida.exists():
        try:
            saida.unlink()
        except OSError as erro:
            raise ErroConversao(f'Não consegui apagar o PDF antigo em {saida}: {erro}') from erro

    comando = [
        str(navegador),
        '--headless',
        '--disable-gpu',
        f'--print-to-pdf={saida}',
        '--no-pdf-header-footer',
        entrada.as_uri(),
    ]
    try:
        resultado = subprocess.run(
            comando, capture_output=True, encoding='utf-8', errors='replace', timeout=60)
    except (OSError, subprocess.SubprocessError) as erro:
        raise ErroConversao(f'Não consegui rodar {navegador}: {erro}') from erro

    if resultado.returncode != 0:
        raise ErroConversao(
            f'{navegador.name} terminou com código {resultado.returncode}.\n'
            f'{resultado.stderr.strip()}')

    if not saida.exists():
        raise ErroConversao(
            f'{navegador.name} terminou sem erro, mas {saida} não foi criado.\n'
            f'{resultado.stderr.strip()}')


def main() -> int:
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding='utf-8')
        except (AttributeError, OSError):
            pass

    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not args:
        print(__doc__)
        return 2

    entrada = Path(args[0]).resolve()
    if not entrada.exists():
        print(f'Não achei {entrada}.', file=sys.stderr)
        return 1

    saida = Path(args[1]).resolve() if len(args) > 1 else entrada.with_suffix('.pdf')

    try:
        navegador = achar_navegador()
    except ErroNavegadorNaoEncontrado as erro:
        print(str(erro), file=sys.stderr)
        return 1

    try:
        converter(entrada, saida, navegador)
    except ErroConversao as erro:
        print(str(erro), file=sys.stderr)
        return 1

    print(f'gerado: {saida}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
