#!/usr/bin/env python3
"""
Monta um conjunto de documentos com a identidade do projeto.

Lê o `.docs-brand.yml` da raiz, copia os arquivos da skill para a pasta de destino,
COPIA OS LOGOS DO PROJETO por cima dos placeholders e escreve `assets/brand.css` com
os tokens de marca. Os HTML saem com `{{PROJETO}}` e companhia já substituídos.

Regra dos logos: primeiro os do projeto, sempre. O placeholder da skill só aparece
quando o YAML não aponta para nada que exista — e, nesse caso, o aviso sai no relatório
em vez de passar despercebido.

Uso:
    python aplicar_marca.py <pasta-de-destino> [--raiz .] [--paginas 01-visao,02-arquitetura]
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent

# O bloco de instruções no topo do modelo — ele orienta quem COPIA o template e
# não tem o que fazer no documento entregue.
COMENTARIO_DO_MODELO = r'<!--\s*=+\s*\n.*?MODELO DE DOCUMENTO.*?-->\s*\n'


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


def raiz_do_projeto(inicio: Path) -> Path:
    try:
        r = subprocess.run(['git', 'rev-parse', '--show-toplevel'],
                           cwd=inicio, capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and r.stdout.strip():
            return Path(r.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return inicio.resolve()


# ---------------------------------------------------------------- CSS marca --
def css_da_marca(marca: dict) -> str:
    """
    Só os tokens que mudam de projeto para projeto. Vem DEPOIS do docs.css no HTML,
    então sobrescreve sem precisar editar o design system — atualizar a skill não
    apaga a marca de ninguém.
    """
    def rgb(hexa: str) -> str:
        return ','.join(str(int(hexa[i:i + 2], 16)) for i in (1, 3, 5))

    c = marca.get('claro', {}) or {}
    e = marca.get('escuro', {}) or {}
    cb = c.get('brand', '#00708D')
    eb = e.get('brand', '#4AB5D0')
    return f'''/* Marca do projeto — gerado de .docs-brand.yml. Não editar à mão:
   mexa no YAML e rode a skill de novo. Carregar DEPOIS de docs.css. */
:root, :root[data-theme="light"] {{
  --brand:       {cb};
  --brand-rgb:   {rgb(cb)};
  --brand-hover: {c.get('hover', cb)};
  --brand-tint:  {c.get('tint', '#EBF4F6')};
}}
:root[data-theme="dark"] {{
  --brand:       {eb};
  --brand-rgb:   {rgb(eb)};
  --brand-hover: {e.get('hover', eb)};
  --brand-tint:  {e.get('tint', '#1A3A44')};
}}

/* A folha impressa é sempre clara — inclusive quando o leitor está no tema
   escuro na hora do Ctrl+P. O docs.css já força os tokens de superfície, mas
   este arquivo é carregado DEPOIS dele: sem repetir a marca aqui, o azul
   luminoso do tema escuro sairia sobre papel branco, com contraste de nada. */
@media print {{
  :root, :root[data-theme="light"], :root[data-theme="dark"] {{
    --brand:       {cb};
    --brand-rgb:   {rgb(cb)};
    --brand-hover: {c.get('hover', cb)};
    --brand-tint:  {c.get('tint', '#EBF4F6')};
  }}
}}
'''


# -------------------------------------------------------------------- logos --
def instalar_avatar(cfg: dict, raiz: Path, destino: Path) -> tuple[str, list[str]]:
    """
    Copia a foto do autor, quando houver. Devolve o HTML do avatar e o relatório.

    Sem foto — ou com um caminho que não existe — voltam as iniciais, que é o
    estado normal e não um defeito: nem todo documento tem retrato do autor.
    """
    autoria = cfg.get('autoria', {}) or {}
    rel = (autoria.get('avatar') or '').strip()
    nome = autoria.get('autor', '')
    iniciaisHtml = f'<div class="avatar">{iniciais(nome)}</div>'

    if not rel:
        return iniciaisHtml, []
    origem = (raiz / rel).resolve()
    if not origem.exists():
        return iniciaisHtml, [f'avatar: "{rel}" não existe — usando as iniciais']

    alvo = destino / 'assets' / f'avatar{origem.suffix.lower()}'
    shutil.copy2(origem, alvo)
    notas = [f'avatar: {rel} → assets/{alvo.name}']
    if alvo.stat().st_size > 300_000:
        notas.append(f'   ⚠ {alvo.name} tem {alvo.stat().st_size // 1024} KB — '
                     f'a foto aparece em 48px; vale reduzir')
    alt = f'{nome}, autor do documento' if nome else 'Autor do documento'
    return (f'<img class="avatar" src="assets/{alvo.name}" alt="{alt}" '
            f'width="48" height="48" loading="lazy">'), notas


def instalar_logos(cfg: dict, raiz: Path, destino: Path) -> list[str]:
    """Copia os logos do projeto sobre os placeholders. Devolve o relatório."""
    notas = []
    for chave, alvo_base in (('claro', 'logo-claro'), ('escuro', 'logo-escuro')):
        rel = (cfg.get('logo') or {}).get(chave) or ''
        if not rel:
            notas.append(f'logo {chave}: NÃO definido no YAML — usando o placeholder da skill')
            continue
        origem = (raiz / rel).resolve()
        if not origem.exists():
            notas.append(f'logo {chave}: "{rel}" não existe — usando o placeholder da skill')
            continue
        # mantém a extensão do arquivo do projeto: png, svg, webp…
        alvo = destino / 'assets' / f'{alvo_base}{origem.suffix.lower()}'
        shutil.copy2(origem, alvo)
        # documentação carrega o logo em toda página; um PNG de 2 MB pesa em cada uma
        if alvo.stat().st_size > 500_000:
            notas.append(f'   ⚠ {alvo.name} tem {alvo.stat().st_size // 1024} KB — '
                         f'vale gerar uma versão reduzida para a documentação')
        # o HTML aponta para o placeholder .svg; se o logo real tem outra extensão,
        # o placeholder sai de cena para não ficar arquivo morto na pasta
        placeholder = destino / 'assets' / f'{alvo_base}.svg'
        if placeholder.exists() and placeholder != alvo:
            placeholder.unlink()
        notas.append(f'logo {chave}: {rel} → assets/{alvo.name}')
    return notas


# --------------------------------------------------------------- montagem ---
def iniciais(nome: str) -> str:
    """As iniciais do autor para o avatar do rodapé — 'Fábio Patria' vira 'FP'."""
    partes = [p for p in (nome or '').split() if len(p) > 2]
    return ''.join(p[0].upper() for p in partes[:2]) or '··'


def substituir(texto: str, cfg: dict, destino_assets: dict[str, str], avatar: str = '') -> str:
    proj = cfg.get('projeto', {}) or {}
    textos = cfg.get('textos', {}) or {}
    autoria = cfg.get('autoria', {}) or {}
    contato = cfg.get('contato', {}) or {}
    hoje = date.today()
    trocas = {
        '{{PROJETO}}': proj.get('nome', 'Projeto'),
        '{{SUBTITULO}}': proj.get('subtitulo', ''),
        '{{AREA}}': proj.get('area', ''),
        '{{CLASSIFICACAO}}': proj.get('classificacao', 'Interno'),
        '{{CABECALHO}}': textos.get('cabecalho', ''),
        '{{RODAPE}}': (textos.get('rodape', '') or '')
            .replace('{ano}', str(hoje.year))
            .replace('{data}', hoje.strftime('%d/%m/%Y')),
        '{{AUTOR}}': autoria.get('autor', ''),
        '{{REVISOR}}': autoria.get('revisor', ''),
        '{{CARGO}}': autoria.get('cargo', ''),
        '{{INICIAIS}}': iniciais(autoria.get('autor', '')),
        '{{AVATAR}}': avatar or f'<div class="avatar">{iniciais(autoria.get("autor", ""))}</div>',
        '{{EMAIL}}': contato.get('email', ''),
        '{{SITE}}': contato.get('site', ''),
        '{{DATA}}': hoje.strftime('%d/%m/%Y'),
        'assets/logo-claro.svg': destino_assets['claro'],
        'assets/logo-escuro.svg': destino_assets['escuro'],
    }
    for de, para in trocas.items():
        texto = texto.replace(de, para)

    # O comentário-instrução do modelo é para quem COPIA o template, não para quem
    # lê o documento pronto: sai na geração.
    texto = re.sub(COMENTARIO_DO_MODELO, '', texto, flags=re.S)

    # o design system carrega o CSS da skill; a marca entra logo depois
    texto = texto.replace(
        '<link rel="stylesheet" href="assets/docs.css">',
        '<link rel="stylesheet" href="assets/docs.css">\n'
        '<link rel="stylesheet" href="assets/brand.css">')

    if not (cfg.get('tipografia', {}) or {}).get('fontes_externas', True):
        # documento que roda offline ou vai por e-mail não pode depender do Google
        linhas = [l for l in texto.split('\n')
                  if 'fonts.googleapis.com' not in l and 'fonts.gstatic.com' not in l]
        texto = '\n'.join(linhas)
    return texto


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
    destino = Path(args[0]).resolve()

    opc = {a.split('=')[0]: a.split('=', 1)[1] if '=' in a else ''
           for a in sys.argv[1:] if a.startswith('--')}
    raiz = raiz_do_projeto(Path(opc.get('--raiz', '.')))

    yml = raiz / '.docs-brand.yml'
    if not yml.exists():
        print(f'Não achei {yml}.\nInvoque a skill /kbr-docs:report-creator — ela descobre os '
              f'logos e a marca deste projeto na primeira vez.', file=sys.stderr)
        return 1
    cfg = carregar_yaml(yml)

    destino.mkdir(parents=True, exist_ok=True)
    (destino / 'assets').mkdir(exist_ok=True)

    for arq in (SKILL / 'assets').iterdir():
        shutil.copy2(arq, destino / 'assets' / arq.name)

    notas = instalar_logos(cfg, raiz, destino)
    avatarHtml, notasAvatar = instalar_avatar(cfg, raiz, destino)
    notas += notasAvatar

    # para onde os <img> devem apontar depois da cópia
    def caminho_logo(base: str) -> str:
        for ext in ('.svg', '.png', '.webp', '.jpg', '.jpeg'):
            if (destino / 'assets' / f'{base}{ext}').exists():
                return f'assets/{base}{ext}'
        return f'assets/{base}.svg'

    destino_assets = {'claro': caminho_logo('logo-claro'), 'escuro': caminho_logo('logo-escuro')}

    (destino / 'assets' / 'brand.css').write_text(
        css_da_marca(cfg.get('marca', {}) or {}), encoding='utf-8', newline='\n')

    paginas = [p for p in (opc.get('--paginas', '') or '').split(',') if p]
    escritos = []
    for modelo in (SKILL / 'templates').iterdir():
        texto = substituir(modelo.read_text(encoding='utf-8'), cfg, destino_assets, avatarHtml)
        if modelo.name == 'documento-modelo.html' and paginas:
            for p in paginas:
                alvo = destino / f'{p}.html'
                if alvo.exists():
                    continue          # nunca sobrescreve documento já escrito
                alvo.write_text(texto, encoding='utf-8', newline='\n')
                escritos.append(alvo.name)
            continue
        alvo = destino / modelo.name
        if alvo.exists():
            continue
        alvo.write_text(texto, encoding='utf-8', newline='\n')
        escritos.append(alvo.name)

    print(f'projeto : {(cfg.get("projeto") or {}).get("nome")}')
    print(f'raiz    : {raiz}')
    print(f'destino : {destino}')
    for n in notas:
        print(f'   {n}')
    print(f'escritos: {", ".join(escritos) if escritos else "(nenhum — já existiam)"}')
    print('assets  : docs.css, docs.js, brand.css + logos')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
