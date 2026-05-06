import re
import time
from datetime import datetime, timedelta, timezone

import requests
from flask import current_app


class OutlookGraphNaoConfigurado(Exception):
    pass


class OutlookGraphErro(Exception):
    pass


_TOKEN_CACHE = {"access_token": "", "expires_at": 0}


def buscar_codigo_onvio():
    cliente = OutlookGraphClient()
    deadline = time.time() + current_app.config["MICROSOFT_GRAPH_POLL_SECONDS"]
    ultimo_erro = None

    while time.time() <= deadline:
        try:
            codigo = cliente.buscar_codigo_recente()
            if codigo:
                return codigo
        except OutlookGraphErro as exc:
            ultimo_erro = exc
        time.sleep(5)

    if ultimo_erro:
        raise ultimo_erro
    raise OutlookGraphErro("Codigo Onvio nao encontrado nos e-mails recentes.")


class OutlookGraphClient:
    def __init__(self):
        self.tenant_id = current_app.config["MICROSOFT_GRAPH_TENANT_ID"]
        self.client_id = current_app.config["MICROSOFT_GRAPH_CLIENT_ID"]
        self.client_secret = current_app.config["MICROSOFT_GRAPH_CLIENT_SECRET"]
        self.user_email = current_app.config["MICROSOFT_GRAPH_USER_EMAIL"]
        self.lookback_minutes = current_app.config["MICROSOFT_GRAPH_LOOKBACK_MINUTES"]
        self._validar_config()

    def buscar_codigo_recente(self):
        token = self._token()
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        desde = (datetime.now(timezone.utc) - timedelta(minutes=self.lookback_minutes)).isoformat()
        params = {
            "$top": "15",
            "$orderby": "receivedDateTime desc",
            "$select": "subject,bodyPreview,from,receivedDateTime,body",
            "$filter": f"receivedDateTime ge {desde.replace('+00:00', 'Z')}",
        }
        url = f"https://graph.microsoft.com/v1.0/users/{self.user_email}/messages"
        response = requests.get(url, headers=headers, params=params, timeout=30)
        if response.status_code >= 400:
            raise OutlookGraphErro(f"Microsoft Graph retornou HTTP {response.status_code}.")

        for mensagem in response.json().get("value", []):
            if not _parece_email_onvio(mensagem):
                continue
            codigo = _extrair_codigo(mensagem)
            if codigo:
                return codigo
        return ""

    def _token(self):
        if _TOKEN_CACHE["access_token"] and _TOKEN_CACHE["expires_at"] > time.time() + 60:
            return _TOKEN_CACHE["access_token"]

        url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        response = requests.post(
            url,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": "https://graph.microsoft.com/.default",
                "grant_type": "client_credentials",
            },
            timeout=30,
        )
        if response.status_code >= 400:
            raise OutlookGraphErro(f"Falha ao autenticar no Microsoft Graph: HTTP {response.status_code}.")

        payload = response.json()
        access_token = payload.get("access_token")
        if not access_token:
            raise OutlookGraphErro("Microsoft Graph nao retornou access_token.")
        _TOKEN_CACHE["access_token"] = access_token
        _TOKEN_CACHE["expires_at"] = time.time() + int(payload.get("expires_in") or 300)
        return access_token

    def _validar_config(self):
        faltando = []
        for nome, valor in (
            ("MICROSOFT_GRAPH_TENANT_ID", self.tenant_id),
            ("MICROSOFT_GRAPH_CLIENT_ID", self.client_id),
            ("MICROSOFT_GRAPH_CLIENT_SECRET", self.client_secret),
            ("MICROSOFT_GRAPH_USER_EMAIL", self.user_email),
        ):
            if not valor:
                faltando.append(nome)
        if faltando:
            raise OutlookGraphNaoConfigurado(
                "Microsoft Graph nao configurado. Preencha no .env: " + ", ".join(faltando)
            )


def _parece_email_onvio(mensagem):
    remetente = (
        mensagem.get("from", {})
        .get("emailAddress", {})
        .get("address", "")
        .lower()
    )
    texto = " ".join(
        str(valor or "")
        for valor in (
            mensagem.get("subject"),
            mensagem.get("bodyPreview"),
            mensagem.get("body", {}).get("content"),
            remetente,
        )
    ).lower()
    termos = ("onvio", "thomson", "reuters", "codigo", "código", "verification", "verificacao", "verificação")
    return any(termo in texto for termo in termos)


def _extrair_codigo(mensagem):
    texto = " ".join(
        str(valor or "")
        for valor in (
            mensagem.get("subject"),
            mensagem.get("bodyPreview"),
            mensagem.get("body", {}).get("content"),
        )
    )
    candidatos = re.findall(r"(?<!\d)(\d{6,8})(?!\d)", texto)
    return candidatos[0] if candidatos else ""
