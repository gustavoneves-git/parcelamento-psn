from app.database import get_db


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
