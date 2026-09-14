# -*- coding: utf-8 -*-
"""Hook PreToolUse do kbr-core: impede o modelo de ler o arquivo de segredos.

Recebe pela entrada padrão o JSON da ferramenta que o Claude Code vai executar e
nega a chamada quando ela endereça algo dentro de `~/.kbr/` — com a única exceção
de `config.json` sozinho (nada depois), que não guarda segredo. Dois marcadores
independentes disparam a negação: o nome do arquivo de segredos (`secrets.env`,
em qualquer campo inspecionado) e a própria pasta protegida.

Quais campos são inspecionados depende de `tool_name`, porque nem todo campo com
esses nomes é um caminho: o `pattern` do Grep é uma regex de busca — procurar por
".kbr" no código-fonte é trabalho legítimo —, mas o `pattern` do Glob é mesmo um
glob de caminho.

- Read, Edit, Write, MultiEdit: `file_path`.
- NotebookEdit: `notebook_path`.
- Glob: `path` e `pattern`.
- Grep: só `path` — nunca `pattern`.
- Bash: `command`.
- Ferramenta desconhecida ou ausente: varre todos os campos candidatos, o padrão
  seguro para uma ferramenta que o hook não conhece.

No campo `command` do Bash, ".kbr" só conta como acesso quando tem forma de
caminho sendo endereçado — início da string, ou logo depois de "/", "~" ou uma
letra de unidade —, e não qualquer menção solta em prosa (mensagem de commit,
`echo`). Nos demais campos (`file_path` e parecidos) o valor inteiro já é um
caminho, então qualquer menção já é um acesso.

Um caso não dá pra separar de forma limpa por regex sem interpretar aspas do
shell: um caminho citado dentro de uma mensagem entre aspas (ex.:
`git commit -m "... ~/.kbr"`) fica com a mesma forma textual — "/" logo antes de
".kbr" — de um caminho de verdade sendo passado a um comando. Sem rastrear
aspas (o que este hook deliberadamente não faz — ver LIMITES abaixo), as duas
situações são indistinguíveis a partir do texto ao redor de ".kbr"; a decisão
tomada aqui foi negar nesse caso (falso positivo numa mensagem de commit é
incômodo; falso negativo é vazamento). Detalhe e exemplos no relatório da
task 5.

LIMITES CONHECIDOS: isto é uma barreira contra exposição acidental no transcript,
não uma fronteira de segurança. Um script escrito na hora que abra o arquivo por
dentro passa — é exatamente assim que os scripts dos plugins leem os segredos.
Um comando codificado em base64 (ou de qualquer forma que não exiba o caminho
como texto) também passa — o hook não decodifica nem interpreta o shell.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# Campos varridos quando a ferramenta é desconhecida (ou ausente) — o padrão
# seguro: como não sabemos a semântica dos campos dessa ferramenta, olhamos
# todos os candidatos plausíveis em vez de arriscar não olhar o campo certo.
CAMPOS_PADRAO = ("file_path", "notebook_path", "path", "pattern", "command", "file_paths")

# Campos que realmente carregam caminho para cada ferramenta conhecida. Grep
# fica de fora do `pattern` (é regex de busca); Glob entra com os dois (o
# `pattern` dele é um glob de caminho).
CAMPOS_POR_FERRAMENTA: dict[str, tuple[str, ...]] = {
    "Read": ("file_path",),
    "Edit": ("file_path",),
    "Write": ("file_path",),
    "MultiEdit": ("file_path",),
    "NotebookEdit": ("notebook_path",),
    "Glob": ("path", "pattern"),
    "Grep": ("path",),
    "Bash": ("command",),
}

# Segundo marcador, independente de ".kbr": o próprio nome do arquivo de
# segredos. Fecha as grafias que escapam do MARCA/padrão-base por causa de
# aspas no meio do nome, variável de shell ou coringa (".k""br", ".$x", ".kb?")
# mas que continuam citando "secrets.env" por extenso.
MARCADOR_SEGREDOS = "secrets.env"

# Depois do marcador, exige fronteira de segmento (nada de alfanumérico/_/- colado
# — senão ".kbr" também "acharia" ".kbrasil") e captura o que vier depois da barra.
SUFIXO_FRONTEIRA = r"(?![a-z0-9_\-])(?:/([a-z0-9_.\-/*]*))?"

# `.kbr` como segmento completo, opcionalmente seguido do que vier depois da barra.
# Usado nos campos onde o valor inteiro já é um caminho (file_path e afins): ali
# qualquer menção é um acesso, não precisa parecer caminho — já é um.
MARCA = re.compile(r"\.kbr" + SUFIXO_FRONTEIRA)

# Só para o campo `command` do Bash: exige que ".kbr" apareça mesmo endereçando
# um caminho — logo no início da string, ou depois de "/", "~" ou uma letra de
# unidade (ex.: "c:") — e não uma menção solta em prosa. Isso é o que distingue
# `cat ~/.kbr/secrets.env` (nega) de `echo "... .kbr"` (permite).
PREFIXO_CAMINHO = r"(?:^|[/~]|[a-z]:)"
MARCA_COMANDO = re.compile(PREFIXO_CAMINHO + r"\.kbr" + SUFIXO_FRONTEIRA)

MOTIVO = (
    "Esse caminho guarda os segredos pessoais do usuário (tokens de API) e está "
    "protegido pelo plugin kbr-core. Eu não leio esse arquivo: os scripts dos "
    "plugins o leem por dentro, sem que o valor passe pela conversa. Para conferir "
    "o que está preenchido sem expor nada, rode /kbr-core:secrets status. "
    "Para editar, /kbr-core:secrets editar abre o arquivo no editor do usuário."
)


def caminho_base() -> Path:
    override = os.environ.get("KBR_HOME")
    return Path(override) if override else Path.home() / ".kbr"


def normalizar(texto: str, base: Path) -> str:
    """Minúsculas, barras para frente e marcadores de home já expandidos."""
    normalizado = str(texto).replace("\\", "/").lower()
    casa = str(base.parent).replace("\\", "/").lower()
    for marcador in ("$env:userprofile", "%userprofile%", "${home}", "$home", "~"):
        normalizado = normalizado.replace(marcador, casa)
    return normalizado


def _protegido(texto: str, base: Path, *, comando: bool = False) -> bool:
    """`texto` já passou por `normalizar`.

    `comando=True` é o modo estrito do campo `command` do Bash: ".kbr" só conta
    quando tem forma de caminho sendo endereçado, não em qualquer lugar do
    texto (ver docstring do módulo). Nos demais campos, o valor inteiro já é um
    caminho, então a checagem ampla (MARCA, sem exigir prefixo) é a certa.
    """
    if MARCADOR_SEGREDOS in texto:
        return True
    alvo = normalizar(str(base), base)
    # Mesma fronteira do MARCA: cobre um KBR_HOME customizado cujo nome não seja
    # literalmente ".kbr" — sem ela, "alvo in texto" bastava para negar por engano
    # uma pasta que só começa igual (".kbrasil" contém ".kbr" como substring).
    padrao_base = re.compile(re.escape(alvo) + SUFIXO_FRONTEIRA)
    correspondencia_base = padrao_base.search(texto)
    if correspondencia_base:
        resto = correspondencia_base.group(1) or ""
        # Exceção exata: só "config.json" e nada depois. Com startswith(),
        # "config.json.bak" e "config.json/../secrets.env" também "começavam"
        # com "config.json" e passavam como se fossem o arquivo permitido.
        if resto != "config.json":
            return True
    marca = MARCA_COMANDO if comando else MARCA
    for correspondencia in marca.finditer(texto):
        resto = correspondencia.group(1) or ""
        if resto != "config.json":
            return True
    return False


def decidir(tool_name: str, tool_input: dict, base: Path) -> str | None:
    """None = pode seguir. Texto = negar, com esse motivo.

    Os campos inspecionados dependem de `tool_name` — ver CAMPOS_POR_FERRAMENTA
    e a docstring do módulo.
    """
    # tool_input vem de JSON: pode chegar como string, lista, número etc. em vez de
    # objeto (campo com tipo inesperado). "x or {}" só cobre None/vazio — um valor
    # truthy não-dict (ex.: "algo") chegaria inteiro ao .get() e estouraria
    # AttributeError. Isso não pode escapar de main().
    if not isinstance(tool_input, dict):
        return None
    # tool_name também vem de JSON e pode chegar com tipo inesperado (lista,
    # dict...). Um tipo não-hashável quebraria o .get() do dicionário de campos
    # por ferramenta (TypeError: unhashable type) — o isinstance evita isso e
    # cai no mesmo padrão seguro de ferramenta desconhecida.
    if isinstance(tool_name, str):
        campos = CAMPOS_POR_FERRAMENTA.get(tool_name, CAMPOS_PADRAO)
    else:
        campos = CAMPOS_PADRAO
    for campo in campos:
        bruto = tool_input.get(campo)
        if not bruto:
            continue
        valores = bruto if isinstance(bruto, list) else [bruto]
        comando = tool_name == "Bash" and campo == "command"
        for valor in valores:
            texto = normalizar(str(valor), base)
            if _protegido(texto, base, comando=comando):
                return MOTIVO
    return None


def main() -> int:
    # Mesma repetição deliberada do KBR_HOME: o hook é autocontido e não importa
    # kbr_secrets, mas sofre do mesmo problema no Windows — sem isto, o console
    # grava o JSON com o codepage local (ex.: cp1252) em vez de UTF-8, e o motivo
    # em PT-BR sai com acentuação errada para quem lê a saída do hook.
    if hasattr(sys.stdout, "reconfigure"):
        # stdout fechado (ou num estado que rejeita reconfigure) levantaria
        # aqui — o hook nunca pode perturbar a sessão do usuário por causa
        # disso, então a falha é engolida e a saída simplesmente sai sem o
        # encoding ideal, em vez de derrubar o hook inteiro.
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    try:
        dados = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
        return 0
    if not isinstance(dados, dict):
        return 0
    try:
        base = caminho_base()
    except RuntimeError:
        # Path.home() não conseguiu resolver o diretório do usuário. Sem uma
        # base para comparar, não há o que proteger — permite e sai em
        # silêncio, como qualquer outra entrada que não dá pra avaliar.
        return 0
    motivo = decidir(dados.get("tool_name"), dados.get("tool_input") or {}, base)
    if motivo is None:
        return 0
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": motivo,
        }
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
