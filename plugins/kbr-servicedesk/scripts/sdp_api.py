# -*- coding: utf-8 -*-
"""Acesso à API do ServiceDesk Plus Cloud (SDP) v3, com OAuth Zoho.

Os segredos vêm de kbr_secrets (arquivo ~/.kbr/secrets.env ou 1Password) e NUNCA
são impressos. Toda saída é JSON em UTF-8, sem credenciais e sem cabeçalhos HTTP.
Nenhuma operação de escrita acontece sem a flag --confirmar.
"""
from __future__ import annotations

import argparse
import html as _html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kbr_secrets  # noqa: E402

CHAVE_CONFIG = "servicedesk"
ACEITA = "application/vnd.manageengine.sdp.v3+json"
MARGEM_RENOVACAO = 300  # segundos antes do vencimento em que já renovamos

PADRAO_CONFIG = {
    "tecnico_nome": "",
    "tecnico_email": "",
    "data_center": "us",
    "api_base": "https://sdpondemand.manageengine.com/api/v3",
    "token_url": "https://accounts.zoho.com/oauth/v2/token",
}

STATUS_DE_ESPERA = {"on hold", "aguardando aprovacao", "aguardando aprovação", "em observacao",
                    "em observação"}

ESCOPOS = ["SDPOnDemand.requests.READ", "SDPOnDemand.requests.CREATE",
           "SDPOnDemand.requests.UPDATE"]


class ErroSDP(Exception):
    """A mensagem já é o texto em PT-BR pronto para o usuário."""


# --------------------------------------------------------------------------- config

def ler_config() -> dict:
    caminho = kbr_secrets.caminho_config()
    dados: dict = {}
    if caminho.exists():
        try:
            dados = json.loads(caminho.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            dados = {}
    config = dict(PADRAO_CONFIG)
    config.update(dados.get(CHAVE_CONFIG) or {})
    return config


def gravar_config(novos: dict) -> None:
    caminho = kbr_secrets.caminho_config()
    dados: dict = {}
    if caminho.exists():
        try:
            dados = json.loads(caminho.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            dados = {}
    atual = dict(PADRAO_CONFIG)
    atual.update(dados.get(CHAVE_CONFIG) or {})
    atual.update(novos)
    dados[CHAVE_CONFIG] = atual
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")


# --------------------------------------------------------------------------- erros

_ZOHO = {
    "invalid_code": ("O código de autorização expirou ou já foi usado. Ele vale 10 minutos. "
                     "Gere outro no console (passo 5 do wizard) e cole de novo."),
    "invalid_client": ("Client ID ou Client Secret incorretos. Confira se copiou os dois "
                       "inteiros, sem espaços (passo 4 do wizard). Se o cliente foi criado "
                       "no console de outro país, refaça no americano: api-console.zoho.com."),
    "invalid_scope": ("O cliente não tem os escopos necessários. Gere um novo código com a "
                      "lista completa de escopos (passo 5 do wizard)."),
    "invalid_grant": ("O acesso foi revogado no 1Password ou na Zoho. Refaça os passos 5 e 6 "
                      "do wizard para gerar um novo acesso."),
}

_HTTP = {
    401: ("O acesso foi revogado ou o token venceu. Refaça os passos 5 e 6 do wizard "
          "(/kbr-servicedesk:configurar)."),
    403: ("O cliente não tem permissão para esta operação. Gere um novo código com a lista "
          "completa de escopos (passo 5 do wizard)."),
    404: "O ServiceDesk não encontrou esse chamado. Confira o número.",
    429: "O ServiceDesk recusou por excesso de chamadas. Espere um minuto e tente de novo.",
}


def _mensagens_do_sdp(corpo: dict) -> str:
    """Extrai as mensagens de erro do corpo de resposta do SDP.

    O corpo vem de um `json.loads` sobre a resposta HTTP — o formato de
    `response_status` e `messages` não é garantido, então cada nível é
    validado antes de ser indexado; qualquer formato fora do esperado
    simplesmente não contribui com detalhe nenhum, em vez de quebrar.
    """
    response_status = corpo.get("response_status")
    if not isinstance(response_status, dict):
        return ""
    mensagens = response_status.get("messages")
    if not isinstance(mensagens, list):
        return ""
    textos = [str(item.get("message")) for item in mensagens
             if isinstance(item, dict) and item.get("message")]
    return " ".join(textos)


def traduzir(origem: str, corpo: dict, http: int = 0) -> str:
    """Transforma um erro da Zoho ou do SDP em texto acionável em PT-BR."""
    corpo = corpo if isinstance(corpo, dict) else {}
    if origem == "rede":
        return ("Não consegui falar com o ServiceDesk. Confira a conexão e a VPN, se você "
                "usa, e tente de novo.")
    if origem == "zoho":
        erro_bruto = corpo.get("error")
        codigo = erro_bruto.strip() if isinstance(erro_bruto, str) else ""
        if codigo in _ZOHO:
            return _ZOHO[codigo]
        if codigo:
            return (f"A Zoho recusou a autenticação ({codigo}). Refaça os passos 4 a 6 do "
                    f"wizard (/kbr-servicedesk:configurar).")
        return ("A Zoho não devolveu um token de acesso. Refaça os passos 5 e 6 do wizard "
                "(/kbr-servicedesk:configurar).")
    if http in _HTTP:
        return _HTTP[http]
    detalhe = _mensagens_do_sdp(corpo)
    if detalhe:
        return f"O ServiceDesk recusou a operação (HTTP {http}): {detalhe}"
    return (f"O ServiceDesk respondeu HTTP {http} e não explicou o motivo. Tente de novo; "
            f"se persistir, abra o chamado pelo portal.")


# --------------------------------------------------------------------------- rede

def _abrir(requisicao, timeout=90):
    """Ponto único de rede — os testes substituem esta função."""
    return urllib.request.urlopen(requisicao, timeout=timeout)


def _postar_form(url: str, campos: dict) -> tuple[int, dict]:
    dados = urllib.parse.urlencode(campos).encode("utf-8")
    requisicao = urllib.request.Request(url, data=dados, method="POST")
    try:
        with _abrir(requisicao, timeout=60) as resposta:
            return getattr(resposta, "status", 200), json.loads(resposta.read())
    except urllib.error.HTTPError as erro:
        try:
            return erro.code, json.loads(erro.read())
        except (json.JSONDecodeError, ValueError):
            return erro.code, {}
    except urllib.error.URLError:
        raise ErroSDP(traduzir("rede", {})) from None


def _caminho_cache_token() -> Path:
    return kbr_secrets.caminho_cache() / "sdp_access_token.json"


def _token_em_cache() -> str | None:
    caminho = _caminho_cache_token()
    if not caminho.exists():
        return None
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if float(dados.get("expira_em", 0)) - time.time() < MARGEM_RENOVACAO:
        return None
    return dados.get("access_token") or None


def _guardar_token(token: str, expira_em_segundos: int) -> None:
    caminho = _caminho_cache_token()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps({
        "access_token": token,
        "expira_em": time.time() + max(int(expira_em_segundos or 3600), 60),
    }), encoding="utf-8")


def _segredo(nome: str) -> str:
    try:
        return kbr_secrets.obter(nome)
    except kbr_secrets.ErroSegredo as erro:
        raise ErroSDP(str(erro)) from None


def access_token(forcar: bool = False) -> str:
    if not forcar:
        guardado = _token_em_cache()
        if guardado:
            return guardado
    config = ler_config()
    status, corpo = _postar_form(config["token_url"], {
        "grant_type": "refresh_token",
        "client_id": _segredo("SDP_CLIENT_ID"),
        "client_secret": _segredo("SDP_CLIENT_SECRET"),
        "refresh_token": _segredo("SDP_REFRESH_TOKEN"),
    })
    token = (corpo or {}).get("access_token")
    if status >= 300 or not token:
        raise ErroSDP(traduzir("zoho", corpo or {}))
    _guardar_token(token, (corpo or {}).get("expires_in", 3600))
    return token


def chamar(metodo: str, caminho: str, input_data: dict | None, token: str) -> tuple[int, dict]:
    config = ler_config()
    url = config["api_base"] + caminho
    dados = None
    if metodo == "GET":
        if input_data:
            url += "?" + urllib.parse.urlencode(
                {"input_data": json.dumps(input_data, ensure_ascii=False)})
    else:
        dados = urllib.parse.urlencode(
            {"input_data": json.dumps(input_data or {}, ensure_ascii=False)}).encode("utf-8")
    requisicao = urllib.request.Request(url, data=dados, method=metodo)
    requisicao.add_header("Authorization", f"Zoho-oauthtoken {token}")
    requisicao.add_header("Accept", ACEITA)
    try:
        with _abrir(requisicao) as resposta:
            return getattr(resposta, "status", 200), json.loads(
                resposta.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as erro:
        try:
            return erro.code, json.loads(erro.read().decode("utf-8", "replace"))
        except (json.JSONDecodeError, ValueError):
            return erro.code, {}
    except urllib.error.URLError:
        raise ErroSDP(traduzir("rede", {})) from None
