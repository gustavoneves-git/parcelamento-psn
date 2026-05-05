from app.database import get_db


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
