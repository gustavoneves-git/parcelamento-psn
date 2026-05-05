import base64
import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from requests_pkcs12 import post as pkcs12_post
from flask import current_app

from app.services.serpro_log_service import registrar_serpro_log


PARCSN_SISTEMA = "PARCSN"
PARCSN_VERSAO = "1.0"
SERVICO_CONSULTAR_PARCELAMENTO = "OBTERPARC164"
SERVICO_PARCELAS_DISPONIVEIS = "PARCELASPARAGERAR162"
SERVICO_EMITIR_DAS = "GERARDAS161"

_TOKEN_CACHE = {"access_token": "", "jwt_token": "", "expires_at": 0}


class SerproNaoConfigurado(Exception):
    pass


class SerproErro(Exception):
    pass


class SerproAviso(Exception):
    pass


def consultar_parcelamento_psn(empresa, numero_parcelamento):
    return _cliente().chamar_servico(
        empresa=empresa,
        competencia=None,
        id_servico=SERVICO_CONSULTAR_PARCELAMENTO,
        dados={"numeroParcelamento": numero_parcelamento},
        acao="consultar_parcelamento_psn",
    )


def consultar_parcelas_disponiveis_psn(empresa):
    return _cliente().chamar_servico(
        empresa=empresa,
        competencia=None,
        id_servico=SERVICO_PARCELAS_DISPONIVEIS,
        dados="",
        acao="consultar_parcelas_disponiveis_psn",
    )


def emitir_das_psn(empresa, parcela_aaaamm):
    return _cliente().chamar_servico(
        empresa=empresa,
        competencia=_competencia_de_aaaamm(parcela_aaaamm),
        id_servico=SERVICO_EMITIR_DAS,
        dados={"parcelaParaEmitir": parcela_aaaamm},
        acao="emitir_das_psn",
    )


def emitir_guia_parcelamento(empresa, competencia):
    """Emite a guia PSN do mes informado usando PARCSN/GERARDAS161."""
    parcela_aaaamm = _competencia_para_aaaamm(competencia)
    resposta = emitir_das_psn(empresa, parcela_aaaamm)
    mensagem_serpro = _mensagem_serpro(resposta)
    if mensagem_serpro and not _extrair_pdf_base64(resposta):
        raise SerproAviso(mensagem_serpro)

    caminho_pdf = _salvar_pdf_emitido(empresa, competencia, resposta)

    return {
        "valor": _buscar_primeiro_valor(resposta, ("valor", "valorDAS", "valorTotal")),
        "vencimento": _buscar_primeiro_valor(resposta, ("vencimento", "dataVencimento")),
        "caminho_pdf": str(caminho_pdf),
        "resposta": resposta,
    }


class SerproClient:
    def __init__(self):
        self.token_url = current_app.config["SERPRO_TOKEN_URL"]
        self.api_url = current_app.config["SERPRO_API_URL"]
        self.consumer_key = current_app.config["SERPRO_CONSUMER_KEY"]
        self.consumer_secret = current_app.config["SERPRO_CONSUMER_SECRET"]
        self.cert_path = current_app.config["SERPRO_CERT_PATH"]
        self.timeout = current_app.config["SERPRO_TIMEOUT_SECONDS"]
        self.jwt_header_name = current_app.config["SERPRO_JWT_HEADER_NAME"]
        self.auth_role_type = current_app.config["SERPRO_AUTH_ROLE_TYPE"]
        self.contratante_cnpj = current_app.config["SERPRO_CONTRATANTE_CNPJ"]
        self.autor_pedido_cpf = current_app.config["SERPRO_AUTOR_PEDIDO_CPF"]
        self.use_mtls = current_app.config["SERPRO_USE_MTLS"]

        self._validar_config()

    def autenticar(self):
        if (
            _TOKEN_CACHE["access_token"]
            and _TOKEN_CACHE["jwt_token"]
            and _TOKEN_CACHE["expires_at"] > time.time() + 60
        ):
            return _TOKEN_CACHE["access_token"], _TOKEN_CACHE["jwt_token"]

        registrar_serpro_log(
            acao="autenticar_serpro",
            mensagem="Solicitando token SERPRO.",
            status="INFO",
        )
        response = self._post_autenticacao()

        if response.status_code >= 400:
            registrar_serpro_log(
                acao="autenticar_serpro",
                mensagem="Falha ao autenticar no SERPRO.",
                status="ERRO",
                http_status=response.status_code,
                detalhe_tecnico=_resumo_resposta(response),
            )
            raise SerproErro("Falha ao autenticar no SERPRO.")

        payload = response.json()
        access_token = payload.get("access_token")
        jwt_token = payload.get("jwt_token")
        if not access_token:
            raise SerproErro("Resposta de autenticacao SERPRO nao trouxe access_token.")
        if not jwt_token:
            raise SerproErro("Resposta de autenticacao SERPRO nao trouxe jwt_token.")

        expires_in = int(payload.get("expires_in") or 300)
        _TOKEN_CACHE["access_token"] = access_token
        _TOKEN_CACHE["jwt_token"] = jwt_token
        _TOKEN_CACHE["expires_at"] = time.time() + expires_in

        registrar_serpro_log(
            acao="autenticar_serpro",
            mensagem="Token SERPRO obtido com sucesso.",
            status="SUCESSO",
            http_status=response.status_code,
        )
        return access_token, jwt_token

    def chamar_servico(self, empresa, competencia, id_servico, dados, acao):
        access_token, jwt_token = self.autenticar()
        payload = self._montar_payload(empresa, id_servico, dados)
        url = self._url_servico(id_servico)
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}",
            self.jwt_header_name: jwt_token,
        }

        registrar_serpro_log(
            acao=acao,
            empresa_id=empresa["id"],
            competencia=competencia,
            mensagem=f"Chamando servico PARCSN/{id_servico}.",
            status="INFO",
            detalhe_tecnico=_payload_sem_segredos(payload),
        )
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=self.timeout,
            cert=self._requests_cert(),
        )

        detalhe = _resumo_resposta(response)
        if response.status_code >= 400:
            registrar_serpro_log(
                acao=acao,
                empresa_id=empresa["id"],
                competencia=competencia,
                mensagem=f"Erro HTTP no servico PARCSN/{id_servico}.",
                status="ERRO",
                http_status=response.status_code,
                detalhe_tecnico=detalhe,
            )
            raise SerproErro(f"Erro HTTP {response.status_code} ao chamar SERPRO.")

        registrar_serpro_log(
            acao=acao,
            empresa_id=empresa["id"],
            competencia=competencia,
            mensagem=f"Servico PARCSN/{id_servico} executado com sucesso.",
            status="SUCESSO",
            http_status=response.status_code,
            detalhe_tecnico=detalhe,
        )
        if "application/pdf" in response.headers.get("content-type", ""):
            return {"pdf": base64.b64encode(response.content).decode("ascii")}
        return response.json()

    def _montar_payload(self, empresa, id_servico, dados):
        pedido_dados = {
            "idSistema": PARCSN_SISTEMA,
            "idServico": id_servico,
            "versaoSistema": PARCSN_VERSAO,
        }
        if dados == "":
            pedido_dados["dados"] = ""
        elif dados is not None:
            pedido_dados["dados"] = json.dumps(dados, ensure_ascii=False)

        payload = {
            "contratante": {
                "numero": _somente_digitos(self.contratante_cnpj or empresa["cnpj"]),
                "tipo": 2,
            },
            "autorPedidoDados": {
                "numero": _somente_digitos(self.autor_pedido_cpf or self.contratante_cnpj or empresa["cnpj"]),
                "tipo": _tipo_documento(self.autor_pedido_cpf or self.contratante_cnpj or empresa["cnpj"]),
            },
            "contribuinte": {
                "numero": _somente_digitos(empresa["cnpj"]),
                "tipo": 2,
            },
            "pedidoDados": pedido_dados,
        }

        return payload

    def _url_servico(self, id_servico):
        rota = "Emitir" if id_servico == SERVICO_EMITIR_DAS else "Consultar"
        base = self.api_url.rstrip("/") + "/"
        return urljoin(base, rota)

    def _requests_cert(self):
        if not self.use_mtls:
            return None
        if self.cert_path.lower().endswith((".pfx", ".p12")):
            raise SerproNaoConfigurado(
                "mTLS com requests exige certificado PEM. Mantenha SERPRO_USE_MTLS=0 "
                "ou converta o certificado conforme a documentacao SERPRO."
            )
        return self.cert_path

    def _post_autenticacao(self):
        kwargs = {
            "url": self.token_url,
            "auth": (self.consumer_key, self.consumer_secret),
            "data": {"grant_type": "client_credentials"},
            "headers": {"Role-Type": self.auth_role_type},
            "timeout": self.timeout,
        }

        if self.cert_path.lower().endswith((".pfx", ".p12")):
            return pkcs12_post(
                **kwargs,
                pkcs12_filename=self.cert_path,
                pkcs12_password=current_app.config["SERPRO_CERT_PASSWORD"],
            )

        return requests.post(**kwargs, cert=self._requests_cert())

    def _validar_config(self):
        faltando = []
        for nome, valor in (
            ("SERPRO_CONSUMER_KEY", self.consumer_key),
            ("SERPRO_CONSUMER_SECRET", self.consumer_secret),
            ("SERPRO_TOKEN_URL", self.token_url),
            ("SERPRO_API_URL", self.api_url),
        ):
            if not valor:
                faltando.append(nome)

        if faltando:
            raise SerproNaoConfigurado(
                "API SERPRO ainda nao configurada. Preencha no .env: "
                + ", ".join(faltando)
            )

        if self.cert_path and not Path(self.cert_path).exists():
            raise SerproNaoConfigurado("Certificado SERPRO nao encontrado no caminho configurado.")


def _cliente():
    return SerproClient()


def _competencia_para_aaaamm(competencia):
    mes, ano = competencia.split("/")
    return f"{ano}{mes.zfill(2)}"


def _competencia_de_aaaamm(parcela_aaaamm):
    return f"{parcela_aaaamm[4:6]}/{parcela_aaaamm[:4]}"


def _salvar_pdf_emitido(empresa, competencia, resposta):
    conteudo_pdf = _extrair_pdf_base64(resposta)
    if not conteudo_pdf:
        raise SerproErro("Resposta SERPRO nao trouxe PDF/base64 reconhecido para o DAS.")

    pasta = current_app.config["PARCELAS_PATH"] / empresa["cnpj"] / competencia.replace("/", "-")
    pasta.mkdir(parents=True, exist_ok=True)
    nome = _nome_pdf(empresa, competencia, resposta)
    caminho = pasta / nome
    caminho.write_bytes(base64.b64decode(_limpar_prefixo_base64(conteudo_pdf)))
    return caminho


def _extrair_pdf_base64(valor):
    if isinstance(valor, dict):
        for chave in ("pdf", "arquivo", "documento", "das", "conteudo", "base64"):
            if isinstance(valor.get(chave), str) and _parece_base64_pdf(valor[chave]):
                return valor[chave]
        for item in valor.values():
            encontrado = _extrair_pdf_base64(item)
            if encontrado:
                return encontrado
    if isinstance(valor, list):
        for item in valor:
            encontrado = _extrair_pdf_base64(item)
            if encontrado:
                return encontrado
    if isinstance(valor, str):
        texto = valor.strip()
        if _parece_base64_pdf(texto):
            return texto
        if texto.startswith("{") or texto.startswith("["):
            try:
                return _extrair_pdf_base64(json.loads(texto))
            except json.JSONDecodeError:
                return ""
    return ""


def _parece_base64_pdf(texto):
    amostra = _limpar_prefixo_base64(texto)
    if amostra.startswith("data:application/pdf;base64,"):
        return True
    try:
        inicio = base64.b64decode(amostra[:120] + "===")
    except Exception:
        return False
    return inicio.startswith(b"%PDF")


def _limpar_prefixo_base64(texto):
    return texto.strip().replace("data:application/pdf;base64,", "", 1)


def _nome_pdf(empresa, competencia, resposta):
    competencia_aaaamm = _competencia_para_aaaamm(competencia)
    nome = (
        f"{empresa['nome_empresa']} - {empresa['cnpj']} - "
        f"parcelamento_simples_nacional - competencia_{competencia_aaaamm}.pdf"
    )
    return re.sub(r'[<>:"/\\|?*]', "", nome).strip().lower()


def _buscar_primeiro_valor(valor, chaves):
    if isinstance(valor, dict):
        for chave in chaves:
            if valor.get(chave) not in (None, ""):
                return valor[chave]
        for item in valor.values():
            encontrado = _buscar_primeiro_valor(item, chaves)
            if encontrado not in (None, ""):
                return encontrado
    if isinstance(valor, list):
        for item in valor:
            encontrado = _buscar_primeiro_valor(item, chaves)
            if encontrado not in (None, ""):
                return encontrado
    return None


def _mensagem_serpro(resposta):
    mensagens = resposta.get("mensagens") if isinstance(resposta, dict) else None
    if not mensagens:
        return ""
    textos = []
    for mensagem in mensagens:
        codigo = mensagem.get("codigo", "") if isinstance(mensagem, dict) else ""
        texto = mensagem.get("texto", "") if isinstance(mensagem, dict) else str(mensagem)
        textos.append(f"{codigo} {texto}".strip())
    return " ".join(textos)


def _somente_digitos(valor):
    return re.sub(r"\D", "", valor or "")


def _tipo_documento(valor):
    return 1 if len(_somente_digitos(valor)) == 11 else 2


def _payload_sem_segredos(payload):
    return str(payload)[:2000]


def _resumo_resposta(response):
    content_type = response.headers.get("content-type", "")
    if "application/pdf" in content_type:
        return f"PDF recebido: {len(response.content)} bytes."
    return response.text[:2000]
