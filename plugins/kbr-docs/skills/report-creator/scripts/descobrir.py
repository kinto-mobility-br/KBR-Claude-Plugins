#!/usr/bin/env python3
"""
Descobre a identidade visual de um projeto e escreve `.docs-brand.yml`.

O que ele procura, nesta ordem:
  1. logos JÁ EXISTENTES no projeto — nunca baixa nem inventa;
  2. o nome do projeto, no que o repositório declarar (git, package.json, .csproj, CLAUDE.md);
  3. a cor de marca, amostrada do próprio logo.

O que não encontra vira comentário no YAML, para a pessoa preencher. Nada é chutado em
silêncio: um valor que não veio do projeto entra marcado como sugestão.

Uso:
    python descobrir.py [raiz] [--escrever]

Sem `--escrever` ele só mostra o que encontrou (é o padrão: olhar antes de gravar).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

# Pastas que nunca são do projeto — logo de dependência não é a marca de ninguém.
IGNORAR = {
    '.git', 'node_modules', '.ds-sync', '.design-sync', 'dist', 'build', 'out',
    'obj', 'bin', '.venv', 'venv', '__pycache__', '.next', '.nuxt', 'vendor',
    'coverage', '.cache', 'target', 'Pods', '.idea', '.vs', 'temp', 'tmp',
}
EXTENSOES = {'.svg', '.png', '.webp', '.jpg', '.jpeg'}
PADRAO_NOME = re.compile(r'logo|marca|brand|símbolo|simbolo|wordmark', re.I)

# Pistas no nome do arquivo sobre o fundo a que o logo se destina.
PARA_FUNDO_ESCURO = re.compile(r'branco|white|light[-_]?on|dark[-_]?bg|escuro|invert|neg', re.I)
PARA_FUNDO_CLARO = re.compile(r'preto|black|blue|azul|color|colorido|dark[-_]?on|light[-_]?bg|claro|pos', re.I)


# --------------------------------------------------------------------- raiz --
def raiz_do_projeto(inicio: Path) -> Path:
    """A raiz do repositório, ou o diretório dado se não houver git."""
    try:
        saida = subprocess.run(
            ['git', 'rev-parse', '--show-toplevel'],
            cwd=inicio, capture_output=True, text=True, timeout=10,
        )
        if saida.returncode == 0 and saida.stdout.strip():
            return Path(saida.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return inicio.resolve()


def caminhar(raiz: Path):
    """Percorre o projeto pulando o que é dependência, artefato ou lixo."""
    for pasta, subpastas, arquivos in os.walk(raiz):
        subpastas[:] = [s for s in subpastas if s not in IGNORAR and not s.startswith('.git')]
        for a in arquivos:
            yield Path(pasta) / a


# -------------------------------------------------------------------- logos --
def pixels(im):
    """Os pixels da imagem — `getdata` sai no Pillow 14, `get_flattened_data` entrou."""
    obter = getattr(im, 'get_flattened_data', None) or im.getdata
    return obter()


def luminancia_media(caminho: Path) -> float | None:
    """Luminância média dos pixels OPACOS (0 a 1). None quando não dá para ler."""
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(caminho) as im:
            im = im.convert('RGBA')
            im.thumbnail((64, 64))
            soma = n = 0
            for r, g, b, a in pixels(im):
                if a < 32:          # transparente não conta: é fundo, não marca
                    continue
                soma += 0.2126 * r + 0.7152 * g + 0.0722 * b
                n += 1
            return (soma / n / 255) if n else None
    except Exception:
        return None


def cor_dominante(caminho: Path) -> str | None:
    """A cor mais frequente entre os pixels opacos e coloridos — a cor da marca."""
    if caminho.suffix.lower() == '.svg':
        return cor_de_svg(caminho)
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(caminho) as im:
            im = im.convert('RGBA')
            im.thumbnail((96, 96))
            conta: dict[tuple[int, int, int], int] = {}
            for r, g, b, a in pixels(im):
                if a < 128:
                    continue
                # descarta quase-branco e quase-preto: são fundo e contorno
                mx, mn = max(r, g, b), min(r, g, b)
                if mx > 240 and mn > 240:
                    continue
                if mx < 26:
                    continue
                chave = (r // 24 * 24, g // 24 * 24, b // 24 * 24)
                conta[chave] = conta.get(chave, 0) + 1
            if not conta:
                return None
            r, g, b = max(conta, key=conta.get)
            return f'#{r:02X}{g:02X}{b:02X}'
    except Exception:
        return None


def cor_de_svg(caminho: Path) -> str | None:
    """No SVG a cor está escrita: pega o hex mais repetido que não seja neutro."""
    try:
        texto = caminho.read_text(encoding='utf-8', errors='ignore')
    except OSError:
        return None
    conta: dict[str, int] = {}
    for hexa in re.findall(r'#([0-9a-fA-F]{6})\b', texto):
        r, g, b = (int(hexa[i:i + 2], 16) for i in (0, 2, 4))
        if max(r, g, b) > 240 and min(r, g, b) > 240:
            continue
        if max(r, g, b) < 26:
            continue
        chave = '#' + hexa.upper()
        conta[chave] = conta.get(chave, 0) + 1
    return max(conta, key=conta.get) if conta else None


def achar_logos(raiz: Path) -> list[dict]:
    """Todo candidato a logo dentro do projeto, com o que se pôde medir dele."""
    achados = []
    for caminho in caminhar(raiz):
        if caminho.suffix.lower() not in EXTENSOES:
            continue
        relativo = caminho.relative_to(raiz).as_posix()
        if not PADRAO_NOME.search(caminho.name) and not PADRAO_NOME.search(relativo):
            continue
        lum = luminancia_media(caminho)
        achados.append({
            'caminho': relativo,
            'nome': caminho.name,
            'bytes': caminho.stat().st_size,
            'luminancia': lum,
            'cor': cor_dominante(caminho),
        })
    # o mais raso primeiro: `assets/logo.svg` é mais provável que `docs/x/y/z/logo.svg`
    achados.sort(key=lambda a: (a['caminho'].count('/'), a['caminho']))
    return achados


def escolher_par(logos: list[dict]) -> tuple[dict | None, dict | None]:
    """
    Separa qual logo serve a fundo claro e qual serve a fundo escuro.

    O nome do arquivo é a evidência mais forte (quem nomeou sabia o que fazia); a
    luminância é o desempate — logo para fundo escuro é claro, e vice-versa.
    """
    if not logos:
        return None, None

    para_escuro = [l for l in logos if PARA_FUNDO_ESCURO.search(l['nome'])]
    para_claro = [l for l in logos if PARA_FUNDO_CLARO.search(l['nome']) and l not in para_escuro]

    if not para_escuro or not para_claro:
        com_lum = [l for l in logos if l['luminancia'] is not None]
        if len(com_lum) >= 2:
            com_lum.sort(key=lambda l: l['luminancia'])
            para_claro = para_claro or [com_lum[0]]     # mais escuro → sobre papel
            para_escuro = para_escuro or [com_lum[-1]]  # mais claro → sobre fundo escuro

    claro = para_claro[0] if para_claro else (logos[0] if logos else None)
    escuro = para_escuro[0] if para_escuro else claro
    return claro, escuro


# -------------------------------------------------------------------- nome ---
def nome_do_projeto(raiz: Path) -> tuple[str, str]:
    """(nome, de onde veio) — o projeto costuma se declarar em algum arquivo."""
    pkg = raiz / 'package.json'
    if pkg.exists():
        try:
            dados = json.loads(pkg.read_text(encoding='utf-8'))
            if dados.get('name'):
                return str(dados['name']), 'package.json'
        except (OSError, ValueError):
            pass
    for csproj in list(raiz.glob('*/*.csproj'))[:3]:
        return csproj.stem, csproj.name
    claude = raiz / 'CLAUDE.md'
    if claude.exists():
        for linha in claude.read_text(encoding='utf-8', errors='ignore').splitlines():
            m = re.match(r'^#\s+(.+)', linha.strip())
            if m and m.group(1).strip().upper() != 'CLAUDE.MD':
                return m.group(1).strip(), 'CLAUDE.md'
    return raiz.name, 'nome da pasta'


# -------------------------------------------------------------------- YAML ---
def escurecer(hexa: str, fator: float = .82) -> str:
    r, g, b = (int(hexa[i:i + 2], 16) for i in (1, 3, 5))
    return '#%02X%02X%02X' % (int(r * fator), int(g * fator), int(b * fator))


def clarear(hexa: str, fator: float = .90) -> str:
    r, g, b = (int(hexa[i:i + 2], 16) for i in (1, 3, 5))
    mist = lambda c: int(c + (255 - c) * fator)
    return '#%02X%02X%02X' % (mist(r), mist(g), mist(b))


def realcar(hexa: str, fator: float = .35) -> str:
    """Versão luminosa da marca, para o tema escuro."""
    r, g, b = (int(hexa[i:i + 2], 16) for i in (1, 3, 5))
    mist = lambda c: int(c + (255 - c) * fator)
    return '#%02X%02X%02X' % (mist(r), mist(g), mist(b))


def rgb_de(hexa: str) -> str:
    return ','.join(str(int(hexa[i:i + 2], 16)) for i in (1, 3, 5))


def montar_yaml(raiz: Path, nome: str, origem_nome: str,
                claro: dict | None, escuro: dict | None) -> str:
    marca = (claro or {}).get('cor') or (escuro or {}).get('cor')
    veio_do_logo = marca is not None
    marca = marca or '#00708D'

    def comentario(achou: bool, ondeue: str = '') -> str:
        return f'   # {ondeue}' if achou else '   # SUGESTÃO — confira'

    lc = claro['caminho'] if claro else ''
    le = escuro['caminho'] if escuro else ''

    return f'''# ============================================================================
# IDENTIDADE DO PROJETO PARA A DOCUMENTAÇÃO HTML
# ----------------------------------------------------------------------------
# Lido pela skill `report-creator` a cada documento gerado. Gerado por ela mesma,
# na descoberta de marca, em {raiz.name} — daqui para a frente, editável à mão.
#
# Duas regras que valem para o arquivo inteiro:
#   · caminho é sempre relativo à RAIZ do projeto (onde este arquivo está);
#   · campo vazio tem comportamento definido — está dito em cada um. Nenhum
#     deles quebra a geração.
#
# Depois de editar, gere de novo:
#   invoque a skill /kbr-docs:report-creator
# ============================================================================

projeto:
  # Nome que aparece no cabeçalho, no <title> e na assinatura do rodapé.
  nome: "{nome}"{comentario(True, 'de ' + origem_nome)}
  # Segunda linha do cabeçalho, sob o nome. Vazio = só o nome.
  subtitulo: ""
  # Área responsável — entra na assinatura do rodapé, ao lado do cargo.
  area: ""                       # ex.: Produto, Engenharia, Dados
  # Vai para a ficha do Front Matter. Use o vocabulário da sua empresa.
  classificacao: "Interno"       # Público · Interno · Restrito · Confidencial

logo:
  # O logo do PROJETO, sempre. Os placeholders da skill (que se anunciam como
  # placeholder) só entram quando o caminho está vazio ou não existe — e o
  # aviso sai no relatório da geração, nunca em silêncio.
  # Aceita .svg, .png, .webp e .jpg; a extensão é preservada na cópia.
  claro: "{lc}"{comentario(bool(lc), 'encontrado no projeto')}   # usado no tema CLARO (logo escuro, sobre papel)
  escuro: "{le}"{comentario(bool(le), 'encontrado no projeto')}   # usado no tema ESCURO (logo claro, sobre fundo escuro)
  # Texto alternativo das duas imagens — o que um leitor de tela anuncia.
  alt: "{nome}"

marca:
  # A cor da marca, em hex. Vira `assets/brand.css`, carregado DEPOIS do
  # design system: é o único lugar onde a cor do projeto é definida, e mexer
  # aqui repinta tudo (links, selos, gráficos, o círculo do avatar).
  claro:                           # sobre papel — precisa de contraste ≥ 4,5:1 com o branco
    brand: "{marca}"{comentario(veio_do_logo, 'amostrada do logo')}
    hover: "{escurecer(marca)}"   # links e botões sob o cursor
    tint:  "{clarear(marca)}"   # fundo de callout, selo e realce
  escuro:                          # sobre fundo escuro — some se for escura demais
    brand: "{realcar(marca)}"
    hover: "{realcar(marca, .55)}"
    tint:  "{escurecer(marca, .35)}"

textos:
  # Linha fixa no alto de toda página. Vazio = o cabeçalho mostra só projeto e
  # subtítulo.
  cabecalho: ""
  # Última linha do rodapé, em todas as páginas. Aceita {{ano}} e {{data}},
  # trocados na hora da geração — evita documento com ano congelado.
  rodape: "{nome} · uso interno"

autoria:
  # Nome que assina o documento, no rodapé e na ficha do Front Matter.
  autor: ""
  # Aparece sob o nome, junto com a área: "Cargo · Projeto".
  cargo: ""
  # Foto do autor no selo do rodapé: 48px, redonda, recortada no centro.
  # Vazio = o selo mostra as iniciais do nome (duas letras).
  avatar: ""
  # Quem aprova. Entra na ficha do Front Matter; vazio vira "—".
  revisor: ""

contato:
  # Bloco de contato à direita da assinatura. Vazio = a linha some.
  email: ""
  site: ""

tipografia:
  # true  → Inter e JetBrains Mono, do Google Fonts (precisa de internet).
  # false → system-ui e a monoespaçada do sistema. Use em documento que vá por
  #         e-mail ou rode offline: a página continua correta, muda a fonte.
  fontes_externas: true

saida:
  # Onde os conjuntos de documentos são criados por padrão. Serve de sugestão
  # a quem gera; o comando aceita qualquer caminho.
  pasta: "docs"
'''


# --------------------------------------------------------------------- main --
def main() -> int:
    # o console do Windows nasce em cp1252 e engole os acentos do relatório
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding='utf-8')
        except (AttributeError, OSError):
            pass
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    escrever = '--escrever' in sys.argv
    raiz = raiz_do_projeto(Path(args[0] if args else '.'))

    nome, origem = nome_do_projeto(raiz)
    logos = achar_logos(raiz)
    claro, escuro = escolher_par(logos)

    print(f'raiz do projeto : {raiz}')
    print(f'nome            : {nome}   (de {origem})')
    print(f'logos achados   : {len(logos)}')
    for l in logos[:8]:
        lum = f"{l['luminancia']:.2f}" if l['luminancia'] is not None else ' -- '
        print(f"   {l['caminho']:<52} lum {lum}  cor {l['cor'] or '--'}")
    if len(logos) > 8:
        print(f'   ... e mais {len(logos) - 8}')
    print(f"logo (claro)    : {claro['caminho'] if claro else '(nenhum — usará o placeholder)'}")
    print(f"logo (escuro)   : {escuro['caminho'] if escuro else '(nenhum — usará o placeholder)'}")

    yml = montar_yaml(raiz, nome, origem, claro, escuro)
    destino = raiz / '.docs-brand.yml'

    if not escrever:
        print(f'\n--- {destino} (prévia; use --escrever para gravar) ---\n')
        print(yml)
        return 0

    if destino.exists():
        print(f'\n{destino} já existe — não vou sobrescrever. Apague ou edite à mão.')
        return 1
    destino.write_text(yml, encoding='utf-8', newline='\n')
    print(f'\nescrito: {destino}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
