import logging

from app.database import get_db
from app.logging_config import safe_json


def registrar_serpro_log(
    acao,
    mensagem,
    status="INFO",
    empresa_id=None,
    competencia=None,
    http_status=None,
    detalhe_tecnico="",
):
    get_db().execute(
        """
        INSERT INTO serpro_logs (
            empresa_id,
            competencia,
            acao,
            status,
            http_status,
            mensagem,
            detalhe_tecnico
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            empresa_id,
            competencia,
            acao,
            status,
            http_status,
            mensagem,
            detalhe_tecnico,
        ),
    )
    get_db().commit()
    _registrar_arquivo_serpro(
        acao=acao,
        mensagem=mensagem,
        status=status,
        empresa_id=empresa_id,
        competencia=competencia,
        http_status=http_status,
        detalhe_tecnico=detalhe_tecnico,
    )


def _registrar_arquivo_serpro(
    acao,
    mensagem,
    status,
    empresa_id,
    competencia,
    http_status,
    detalhe_tecnico,
):
    try:
        level = logging.ERROR if status == "ERRO" else logging.INFO
        logging.getLogger("serpro").log(
            level,
            "acao=%s status=%s empresa_id=%s competencia=%s http_status=%s "
            "mensagem=%s detalhe=%s",
            acao,
            status,
            empresa_id,
            competencia,
            http_status,
            mensagem,
            safe_json(detalhe_tecnico),
        )
    except Exception:
        pass
