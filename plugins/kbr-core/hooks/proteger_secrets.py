# -*- coding: utf-8 -*-
"""Hook PreToolUse do kbr-core: impede o modelo de ler o arquivo de segredos.

Recebe pela entrada padrão o JSON da ferramenta que o Claude Code vai executar e
nega qualquer chamada que mencione algo dentro de `~/.kbr/` — com a única exceção
de `config.json`, que não guarda segredo. Cobre Read, Edit, Write, Grep, Glob e
Bash (aí a inspeção é do texto inteiro do comando, então `cat`, `type`,
`Get-Content`, `sed` e redirecionamentos entram junto).

LIMITE CONHECIDO: isto é uma barreira contra exposição acidental no transcript,
não uma fronteira de segurança. Um script escrito na hora que abra o arquivo por
dentro passa — é exatamente assim que os scripts dos plugins leem os segredos.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

CAMPOS = ("file_path", "notebook_path", "path", "pattern", "command", "file_paths")

# Depois do marcador, exige fronteira de segmento (nada de alfanumérico/_/- colado
# — senão ".kbr" também "acharia" ".kbrasil") e captura o que vier depois da barra.
SUFIXO_FRONTEIRA = r"(?![a-z0-9_\-])(?:/([a-z0-9_.\-/*]*))?"

# `.kbr` como segmento completo, opcionalmente seguido do que vier depois da barra.
MARCA = re.compile(r"\.kbr" + SUFIXO_FRONTEIRA)

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


def _protegido(texto: str, base: Path) -> bool:
    alvo = normalizar(str(base), base)
    # Mesma fronteira do MARCA: cobre um KBR_HOME customizado cujo nome não seja
    # literalmente ".kbr" — sem ela, "alvo in texto" bastava para negar por engano
    # uma pasta que só começa igual (".kbrasil" contém ".kbr" como substring).
    padrao_base = re.compile(re.escape(alvo) + SUFIXO_FRONTEIRA)
    correspondencia_base = padrao_base.search(texto)
    if correspondencia_base:
        resto = correspondencia_base.group(1) or ""
        if not resto.startswith("config.json"):
            return True
    for correspondencia in MARCA.finditer(texto):
        resto = correspondencia.group(1) or ""
        if not resto.startswith("config.json"):
            return True
    return False


def decidir(tool_input: dict, base: Path) -> str | None:
    """None = pode seguir. Texto = negar, com esse motivo."""
    # tool_input vem de JSON: pode chegar como string, lista, número etc. em vez de
    # objeto (campo com tipo inesperado). "x or {}" só cobre None/vazio — um valor
    # truthy não-dict (ex.: "algo") chegaria inteiro ao .get() e estouraria
    # AttributeError. Isso não pode escapar de main().
    if not isinstance(tool_input, dict):
        return None
    for campo in CAMPOS:
        bruto = tool_input.get(campo)
        if not bruto:
            continue
        valores = bruto if isinstance(bruto, list) else [bruto]
        for valor in valores:
            if _protegido(normalizar(str(valor), base), base):
                return MOTIVO
    return None


def main() -> int:
    # Mesma repetição deliberada do KBR_HOME: o hook é autocontido e não importa
    # kbr_secrets, mas sofre do mesmo problema no Windows — sem isto, o console
    # grava o JSON com o codepage local (ex.: cp1252) em vez de UTF-8, e o motivo
    # em PT-BR sai com acentuação errada para quem lê a saída do hook.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        dados = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
        return 0
    if not isinstance(dados, dict):
        return 0
    motivo = decidir(dados.get("tool_input") or {}, caminho_base())
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
