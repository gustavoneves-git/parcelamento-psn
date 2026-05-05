import json
import traceback
import uuid

from flask import current_app, request

from app.database import get_db
from app.services.email_service import enviar_email_erro_interno


def registrar_erro_interno(exc, contexto=None):
    codigo = f"PSN-{uuid.uuid4().hex[:10].upper()}"
    contexto = contexto or {}
    erro = {
        "codigo_ocorrencia": codigo,
        "sistema": "parcelamento-psn",
        "versao_sistema": current_app.config.get("VERSION", ""),
        "empresa_id": contexto.get("empresa_id"),
        "usuario": contexto.get("usuario") or "local",
        "tela": contexto.get("tela") or _endpoint_seguro(),
        "acao": contexto.get("acao") or _acao_segura(),
        "rota": _rota_segura(),
        "metodo_http": _metodo_seguro(),
        "competencia": contexto.get("competencia") or _valor_request("competencia"),
        "tipo_erro": type(exc).__name__,
        "mensagem_erro": str(exc),
        "detalhe_tecnico": contexto.get("detalhe_tecnico") or "",
        "stack_trace": traceback.format_exc(),
        "contexto_json": _contexto_json(contexto),
    }

    get_db().execute(
        """
        INSERT INTO erros_internos (
            codigo_ocorrencia,
            sistema,
            versao_sistema,
            empresa_id,
            usuario,
            tela,
            acao,
            rota,
            metodo_http,
            competencia,
            tipo_erro,
            mensagem_erro,
            detalhe_tecnico,
            stack_trace,
            contexto_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            erro["codigo_ocorrencia"],
            erro["sistema"],
            erro["versao_sistema"],
            erro["empresa_id"],
            erro["usuario"],
            erro["tela"],
            erro["acao"],
            erro["rota"],
            erro["metodo_http"],
            erro["competencia"],
            erro["tipo_erro"],
            erro["mensagem_erro"],
            erro["detalhe_tecnico"],
            erro["stack_trace"],
            erro["contexto_json"],
        ),
    )
    get_db().commit()

    try:
        email_enviado, email_erro = enviar_email_erro_interno(erro)
    except Exception as email_exc:
        email_enviado = False
        email_erro = f"{type(email_exc).__name__}: {email_exc}"

    get_db().execute(
        """
        UPDATE erros_internos
        SET email_enviado = ?,
            email_erro = ?
        WHERE codigo_ocorrencia = ?
        """,
        (1 if email_enviado else 0, email_erro, erro["codigo_ocorrencia"]),
    )
    get_db().commit()

    return erro["codigo_ocorrencia"]


def _rota_segura():
    try:
        return request.path
    except RuntimeError:
        return ""


def _metodo_seguro():
    try:
        return request.method
    except RuntimeError:
        return ""


def _endpoint_seguro():
    try:
        return request.endpoint or ""
    except RuntimeError:
        return ""


def _acao_segura():
    try:
        return f"{request.method} {request.path}"
    except RuntimeError:
        return ""


def _valor_request(nome):
    try:
        return request.form.get(nome) or request.args.get(nome) or ""
    except RuntimeError:
        return ""


def _contexto_json(contexto):
    try:
        return json.dumps(contexto, ensure_ascii=False, default=str)[:4000]
    except TypeError:
        return "{}"
