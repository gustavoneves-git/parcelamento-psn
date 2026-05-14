import logging

from app.database import get_db
from app.logging_config import safe_json


def registrar_onvio_log(
    acao,
    mensagem,
    status="INFO",
    empresa_id=None,
    parcela_id=None,
    detalhe_tecnico="",
):
    get_db().execute(
        """
        INSERT INTO onvio_logs (
            empresa_id,
            parcela_id,
            acao,
            status,
            mensagem,
            detalhe_tecnico
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            empresa_id,
            parcela_id,
            acao,
            status,
            mensagem,
            detalhe_tecnico,
        ),
    )
    get_db().commit()
    _registrar_arquivo_onvio(
        acao=acao,
        mensagem=mensagem,
        status=status,
        empresa_id=empresa_id,
        parcela_id=parcela_id,
        detalhe_tecnico=detalhe_tecnico,
    )


def _registrar_arquivo_onvio(
    acao,
    mensagem,
    status,
    empresa_id,
    parcela_id,
    detalhe_tecnico,
):
    try:
        level = logging.ERROR if status == "ERRO" else logging.INFO
        logging.getLogger("onvio").log(
            level,
            "acao=%s status=%s empresa_id=%s parcela_id=%s mensagem=%s detalhe=%s",
            acao,
            status,
            empresa_id,
            parcela_id,
            mensagem,
            safe_json(detalhe_tecnico),
        )
    except Exception:
        pass
