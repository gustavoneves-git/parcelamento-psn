import shutil
from pathlib import Path

from flask import current_app

from app.database import get_db
from app.services.empresa_service import buscar_empresa
from app.services.onvio_log_service import registrar_onvio_log
from app.services.onvio_selenium_service import (
    OnvioAutomacaoErro,
    OnvioConfiguracaoErro,
    subir_pdf_onvio_selenium,
)
from app.services.parcela_service import buscar_parcela_pronta_onvio


def subir_parcela_onvio(empresa_id):
    empresa = buscar_empresa(empresa_id)
    parcela = buscar_parcela_pronta_onvio(empresa_id)

    if empresa is None:
        return _resultado("Empresa nao encontrada.", "error")
    if parcela is None or parcela["status_onvio"] != "PRONTO_PARA_SUBIR":
        return _resultado("Nao existe guia emitida pronta para subir ao Onvio.", "warning")
    if not parcela["caminho_pdf"]:
        return _resultado("A parcela nao possui PDF salvo.", "error")

    origem = Path(parcela["caminho_pdf"])
    if not origem.exists():
        return _resultado("PDF da guia nao encontrado no disco.", "error")

    modo = current_app.config["ONVIO_UPLOAD_MODE"].lower()
    if modo == "selenium":
        try:
            mensagem = subir_pdf_onvio_selenium(empresa, parcela, origem)
        except OnvioConfiguracaoErro as exc:
            registrar_onvio_log(
                acao="onvio_configuracao",
                empresa_id=empresa_id,
                parcela_id=parcela["id"],
                status="ERRO",
                mensagem=str(exc),
            )
            return _resultado(str(exc), "warning")
        except OnvioAutomacaoErro as exc:
            return _resultado(str(exc), "error")
        _marcar_parcela_enviada(parcela["id"], mensagem)
        return _resultado(mensagem, "success")

    if modo != "pasta":
        return _resultado("ONVIO_UPLOAD_MODE invalido. Use pasta ou selenium.", "error")

    destino_dir = _destino_onvio(empresa)
    destino_dir.mkdir(parents=True, exist_ok=True)
    destino = destino_dir / origem.name
    shutil.copy2(origem, destino)
    registrar_onvio_log(
        acao="onvio_pasta",
        empresa_id=empresa_id,
        parcela_id=parcela["id"],
        status="SUCESSO",
        mensagem="PDF copiado para pasta Onvio.",
        detalhe_tecnico=str(destino),
    )

    mensagem = "Guia de parcelamento subida com sucesso para Onvio."
    _marcar_parcela_enviada(parcela["id"], mensagem)
    return _resultado(mensagem, "success")


def _marcar_parcela_enviada(parcela_id, mensagem):
    get_db().execute(
        """
        UPDATE parcelas
        SET status_onvio = 'ENVIADO',
            mensagem = ?,
            data_envio_onvio = CURRENT_TIMESTAMP,
            data_atualizacao = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (mensagem, parcela_id),
    )
    get_db().commit()


def _destino_onvio(empresa):
    if empresa["pasta_onvio"]:
        return Path(empresa["pasta_onvio"])
    return Path(current_app.config["ONVIO_SAIDA_PADRAO"]) / empresa["cnpj"]


def _resultado(mensagem, categoria):
    return {"mensagem": mensagem, "categoria": categoria}
