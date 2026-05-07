from flask import Blueprint, render_template, request

from app.services.historico_service import montar_historico_mensal


historico_bp = Blueprint("historico", __name__, url_prefix="/historico")


@historico_bp.route("/mensal")
def mensal():
    ano = request.args.get("ano")
    filtro_status = request.args.get("status", "ATIVA").upper()
    if filtro_status not in ("ATIVA", "INATIVA", "TODAS"):
        filtro_status = "ATIVA"
    return render_template(
        "historico_mensal.html",
        historico=montar_historico_mensal(ano, filtro_status),
    )
