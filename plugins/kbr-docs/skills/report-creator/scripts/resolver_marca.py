#!/usr/bin/env python3
"""
Resolve o config efetivo de marca do `kbr-docs`: mescla, campo a campo, o nível de
projeto (canônico ou legado) com o nível de usuário — o projeto sempre vence quando
não-vazio; nada é gravado.

Uso:
    python resolver_marca.py <pasta-dentro-do-projeto>

Mostra os dois locais do nível de projeto (canônico e legado) e o do usuário, cada
um com se existe ou não, e o efetivo já mesclado — com os campos de arquivo (logo,
avatar) já resolvidos pra absoluto. Não recebe `--raiz=`; o argumento pode ser
qualquer pasta dentro do projeto, a raiz do git é descoberta automaticamente (mesmo
comportamento de `aplicar_marca.py` e `descobrir.py`).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


# ------------------------------------------------------------------------ raiz --
def raiz_do_projeto(inicio: Path) -> Path:
    try:
        r = subprocess.run(['git', 'rev-parse', '--show-toplevel'],
                           cwd=inicio, capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and r.stdout.strip():
            return Path(r.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return inicio.resolve()


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


NOME_ARQUIVO = 'docs-brand.yml'
CAMPOS_DE_ARQUIVO = (('logo', 'claro'), ('logo', 'escuro'), ('autoria', 'avatar'))


# ------------------------------------------------------------------ caminhos --
def caminho_projeto(raiz: Path) -> Path:
    """<raiz>/.claude/plugins-data/kbr-docs/docs-brand.yml — o canônico."""
    return raiz / '.claude' / 'plugins-data' / 'kbr-docs' / NOME_ARQUIVO


def caminho_projeto_legado(raiz: Path) -> Path:
    """<raiz>/.docs-brand.yml — retrocompatibilidade com o formato de hoje."""
    return raiz / '.docs-brand.yml'


def caminho_projeto_efetivo(raiz: Path) -> Path:
    """Canônico, se existir; senão o legado (existente ou não) — é o que resolver() lê."""
    canonico = caminho_projeto(raiz)
    return canonico if canonico.exists() else caminho_projeto_legado(raiz)


def pasta_usuario() -> Path:
    """
    ~/.claude/plugins-data/kbr-docs/ — ou $CLAUDE_USER_HOME/.claude/plugins-data/
    kbr-docs/, quando a variável de ambiente CLAUDE_USER_HOME estiver definida
    (só os testes usam isso, pra nunca tocar no ~/.claude de verdade).
    """
    override = os.environ.get('CLAUDE_USER_HOME')
    base = Path(override) if override else Path.home()
    return base / '.claude' / 'plugins-data' / 'kbr-docs'


def caminho_usuario() -> Path:
    return pasta_usuario() / NOME_ARQUIVO


def nenhum_nivel_configurado(raiz: Path) -> bool:
    """True quando nem projeto (canônico ou legado) nem usuário têm arquivo."""
    return not (
        caminho_projeto(raiz).exists()
        or caminho_projeto_legado(raiz).exists()
        or caminho_usuario().exists()
    )


# ------------------------------------------------------------------- mescla --
def _absolutizar_campos_de_arquivo(cfg: dict, base: Path) -> None:
    """Muda `cfg` no lugar: cada campo de arquivo não-vazio vira caminho absoluto
    contra `base`. O comportamento é assimétrico por design:
    - Para PROJETO: `base` é a raiz do projeto (caminhos relativos à raiz, compatível com
      `descobrir.py`).
    - Para USUÁRIO: `base` é a pasta de config (~/.claude/plugins-data/kbr-docs/), caminhos
      relativos aos arquivos do usuário, seguindo a convenção de pasta estruturada."""
    for secao, campo in CAMPOS_DE_ARQUIVO:
        bloco = cfg.get(secao)
        if not isinstance(bloco, dict):
            continue
        valor = (bloco.get(campo) or '').strip()
        if valor:
            bloco[campo] = str((base / valor).resolve())


def _mesclar(preferido: dict, alternativo: dict) -> dict:
    """
    Campo a campo, recursivo: valor não-vazio de `preferido` sempre vence; string
    vazia ou chave ausente cai pro mesmo campo em `alternativo`. Booleano nunca é
    tratado como vazio (mesmo `False`). Nenhum dos dois argumentos é alterado.
    """
    resultado: dict = {}
    for chave in dict.fromkeys([*preferido.keys(), *alternativo.keys()]):
        v_pref = preferido.get(chave)
        v_alt = alternativo.get(chave)
        if isinstance(v_pref, dict) or isinstance(v_alt, dict):
            resultado[chave] = _mesclar(
                v_pref if isinstance(v_pref, dict) else {},
                v_alt if isinstance(v_alt, dict) else {})
        elif v_pref is None:
            resultado[chave] = v_alt
        elif isinstance(v_pref, str) and not v_pref.strip():
            resultado[chave] = v_alt if v_alt is not None else v_pref
        else:
            resultado[chave] = v_pref
    return resultado


def resolver(raiz: Path) -> tuple[dict, list[str]]:
    """
    Config efetivo (projeto -> usuário), com os campos de arquivo (logo.claro,
    logo.escuro, autoria.avatar) já absolutos. `notas` lista, no formato
    "secao.campo: nível de usuário (<caminho>)", cada campo de ARQUIVO que NÃO
    veio do projeto — pra aplicar_marca.py citar no relatório da geração.
    """
    notas: list[str] = []

    caminho_proj = caminho_projeto_efetivo(raiz)
    cfg_projeto = carregar_yaml(caminho_proj) if caminho_proj.exists() else {}
    if cfg_projeto:
        _absolutizar_campos_de_arquivo(cfg_projeto, raiz)

    caminho_usr = caminho_usuario()
    cfg_usuario = carregar_yaml(caminho_usr) if caminho_usr.exists() else {}
    if cfg_usuario:
        _absolutizar_campos_de_arquivo(cfg_usuario, caminho_usr.parent)

    efetivo = _mesclar(cfg_projeto, cfg_usuario)

    for secao, campo in CAMPOS_DE_ARQUIVO:
        veio_do_projeto = bool(((cfg_projeto.get(secao) or {}).get(campo) or '').strip())
        veio_do_usuario = bool(((cfg_usuario.get(secao) or {}).get(campo) or '').strip())
        if not veio_do_projeto and veio_do_usuario:
            notas.append(f'{secao}.{campo}: nível de usuário ({caminho_usr})')

    return efetivo, notas


def main() -> int:
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding='utf-8')
        except (AttributeError, OSError):
            pass
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 2
    raiz = raiz_do_projeto(Path(args[0]))
    efetivo, notas = resolver(raiz)

    canonico = caminho_projeto(raiz)
    legado = caminho_projeto_legado(raiz)
    caminho_usr = caminho_usuario()

    print(f'raiz do projeto      : {raiz}')
    print(f'projeto canônico     : {canonico} ({"existe" if canonico.exists() else "não existe"})')
    print(f'projeto legado (raiz): {legado} ({"existe" if legado.exists() else "não existe"})')
    print(f'usuário              : {caminho_usr} ({"existe" if caminho_usr.exists() else "não existe"})')
    print()
    if not efetivo:
        print('(nada configurado em nenhum nível — só o placeholder da skill)')
        return 0
    for secao, dados in efetivo.items():
        print(f'{secao}:')
        if isinstance(dados, dict):
            for chave, valor in dados.items():
                if isinstance(valor, dict):
                    print(f'  {chave}:')
                    for chave2, valor2 in valor.items():
                        print(f'    {chave2}: {valor2!r}')
                else:
                    print(f'  {chave}: {valor!r}')
        else:
            print(f'  {dados!r}')
    if notas:
        print('\ncampos que vieram do nível de usuário:')
        for nota in notas:
            print(f'  {nota}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
