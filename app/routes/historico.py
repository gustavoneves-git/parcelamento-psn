from flask import Blueprint, render_template, request

from app.services.historico_service import montar_historico_mensal


historico_bp = Blueprint("historico", __name__, url_prefix="/historico")


@historico_bp.route("/mensal")
def mensal():
    ano = request.args.get("ano")
    return render_template("historico_mensal.html", historico=montar_historico_mensal(ano))
