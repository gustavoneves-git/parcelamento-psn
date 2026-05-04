import shutil
from pathlib import Path

from flask import current_app

from app.database import get_db
from app.services.empresa_service import buscar_empresa
from app.services.parcela_service import buscar_parcela_atual


def subir_parcela_onvio(empresa_id):
    empresa = buscar_empresa(empresa_id)
    parcela = buscar_parcela_atual(empresa_id)

    if empresa is None:
        return _resultado("Empresa nao encontrada.", "error")
    if parcela is None or parcela["status_onvio"] != "PRONTO_PARA_SUBIR":
        return _resultado("Nao existe guia emitida pronta para subir ao Onvio.", "warning")
    if not parcela["caminho_pdf"]:
        return _resultado("A parcela nao possui PDF salvo.", "error")

    origem = Path(parcela["caminho_pdf"])
    if not origem.exists():
        return _resultado("PDF da guia nao encontrado no disco.", "error")

    destino_dir = _destino_onvio(empresa)
    destino_dir.mkdir(parents=True, exist_ok=True)
    destino = destino_dir / origem.name
    shutil.copy2(origem, destino)

    get_db().execute(
        """
        UPDATE parcelas
        SET status_onvio = 'ENVIADO',
            mensagem = 'Guia de parcelamento subida com sucesso para Onvio.',
            data_envio_onvio = CURRENT_TIMESTAMP,
            data_atualizacao = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (parcela["id"],),
    )
    get_db().commit()

    return _resultado("Guia de parcelamento subida com sucesso para Onvio.", "success")


def _destino_onvio(empresa):
    if empresa["pasta_onvio"]:
        return Path(empresa["pasta_onvio"])
    return Path(current_app.config["ONVIO_SAIDA_PADRAO"]) / empresa["cnpj"]


def _resultado(mensagem, categoria):
    return {"mensagem": mensagem, "categoria": categoria}
