import json
import logging
import threading
import time
from pathlib import Path

from flask import current_app

from app.database import get_db
from app.services.empresa_service import buscar_empresa
from app.services.onvio_log_service import registrar_onvio_log
from app.services.onvio_service import subir_parcela_onvio
from app.services.parcela_service import buscar_parcela_pronta_onvio

_worker_lock = threading.Lock()
_worker_thread = None
_wake_event = threading.Event()


def enfileirar_envio_onvio(empresa_id):
    empresa = buscar_empresa(empresa_id)
    parcela = buscar_parcela_pronta_onvio(empresa_id)

    if empresa is None:
        return _resultado("Empresa nao encontrada.", "error")
    if parcela is None or parcela["status_onvio"] != "PRONTO_PARA_SUBIR":
        return _resultado("Nao existe guia emitida pronta para subir ao Onvio.", "warning")
    if not parcela["caminho_pdf"]:
        return _resultado("A parcela nao possui PDF salvo.", "error")
    if not Path(parcela["caminho_pdf"]).exists():
        return _resultado("PDF da guia nao encontrado no disco.", "error")

    fila_ativa = _buscar_fila_ativa(parcela["id"])
    if fila_ativa:
        if fila_ativa["status"] == "PROCESSANDO":
            return _resultado("Envio ao Onvio ja esta em andamento para essa guia.", "warning")
        return _resultado("Guia ja esta na fila de envio ao Onvio.", "warning")

    get_db().execute(
        """
        INSERT INTO onvio_fila (empresa_id, parcela_id, status, mensagem)
        VALUES (?, ?, 'AGUARDANDO', ?)
        """,
        (empresa_id, parcela["id"], "Aguardando processamento do envio ao Onvio."),
    )
    get_db().commit()

    registrar_onvio_log(
        acao="onvio_fila:enfileirar",
        empresa_id=empresa_id,
        parcela_id=parcela["id"],
        status="INFO",
        mensagem="Guia adicionada a fila de envio Onvio.",
        detalhe_tecnico=json.dumps(
            {
                "modo": current_app.config["ONVIO_UPLOAD_MODE"],
                "competencia": parcela["competencia"],
                "arquivo_pdf": Path(parcela["caminho_pdf"]).name,
            },
            ensure_ascii=True,
        ),
    )
    _notificar_worker()
    return _resultado("Guia adicionada a fila de envio ao Onvio.", "success")


def iniciar_worker_onvio(app):
    if not app.config.get("ONVIO_QUEUE_ENABLED", True):
        return

    global _worker_thread
    with _worker_lock:
        if _worker_thread and _worker_thread.is_alive():
            return
        _wake_event.clear()
        with app.app_context():
            _recolocar_itens_interrompidos()
        _worker_thread = threading.Thread(
            target=_worker_loop,
            args=(app,),
            name="onvio-fila-worker",
            daemon=True,
        )
        _worker_thread.start()



def _recolocar_itens_interrompidos():
    get_db().execute(
        """
        UPDATE onvio_fila
        SET status = 'AGUARDANDO',
            mensagem = 'Envio recolocado na fila apos reinicio do sistema.',
            data_atualizacao = CURRENT_TIMESTAMP
        WHERE status = 'PROCESSANDO'
        """
    )
    get_db().commit()

def _worker_loop(app):
    intervalo = max(5, int(app.config.get("ONVIO_QUEUE_POLL_SECONDS", 15)))
    while True:
        try:
            with app.app_context():
                processou = processar_proximo_item()
        except Exception:
            logging.getLogger("onvio").exception("Falha inesperada no worker da fila Onvio.")
            processou = False

        espera = 1 if processou else intervalo
        _wake_event.wait(espera)
        _wake_event.clear()


def _notificar_worker():
    _wake_event.set()


def processar_proximo_item():
    item = _reservar_proximo_item()
    if item is None:
        return False

    fila_id = item["id"]
    empresa_id = item["empresa_id"]
    parcela_id = item["parcela_id"]

    try:
        resultado = subir_parcela_onvio(empresa_id)
    except Exception as exc:
        _marcar_item_erro(fila_id, f"{type(exc).__name__}: {exc}")
        registrar_onvio_log(
            acao="onvio_fila:erro_inesperado",
            empresa_id=empresa_id,
            parcela_id=parcela_id,
            status="ERRO",
            mensagem="Falha inesperada ao processar fila Onvio.",
            detalhe_tecnico=f"{type(exc).__name__}: {exc}",
        )
        return True

    if resultado["categoria"] == "success":
        _marcar_item_sucesso(fila_id, resultado["mensagem"])
    else:
        _marcar_item_erro(fila_id, resultado["mensagem"])

    pausa = max(0, int(current_app.config.get("ONVIO_QUEUE_INTERVAL_SECONDS", 60)))
    if pausa:
        time.sleep(pausa)
    return True


def _reservar_proximo_item():
    db = get_db()
    item = db.execute(
        """
        SELECT *
        FROM onvio_fila
        WHERE status = 'AGUARDANDO'
        ORDER BY data_criacao, id
        LIMIT 1
        """
    ).fetchone()
    if item is None:
        return None

    db.execute(
        """
        UPDATE onvio_fila
        SET status = 'PROCESSANDO',
            tentativas = tentativas + 1,
            mensagem = 'Processando envio ao Onvio.',
            data_inicio = COALESCE(data_inicio, CURRENT_TIMESTAMP),
            data_atualizacao = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (item["id"],),
    )
    db.commit()
    return item


def _buscar_fila_ativa(parcela_id):
    return get_db().execute(
        """
        SELECT *
        FROM onvio_fila
        WHERE parcela_id = ?
          AND status IN ('AGUARDANDO', 'PROCESSANDO')
        ORDER BY id DESC
        LIMIT 1
        """,
        (parcela_id,),
    ).fetchone()


def _marcar_item_sucesso(fila_id, mensagem):
    get_db().execute(
        """
        UPDATE onvio_fila
        SET status = 'SUCESSO',
            mensagem = ?,
            data_fim = CURRENT_TIMESTAMP,
            data_atualizacao = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (mensagem, fila_id),
    )
    get_db().commit()


def _marcar_item_erro(fila_id, mensagem):
    get_db().execute(
        """
        UPDATE onvio_fila
        SET status = 'ERRO',
            mensagem = ?,
            data_fim = CURRENT_TIMESTAMP,
            data_atualizacao = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (mensagem, fila_id),
    )
    get_db().commit()


def _resultado(mensagem, categoria):
    return {"mensagem": mensagem, "categoria": categoria}
