from datetime import datetime

from app.database import get_db
from app.services.periodo_service import ano_atual


MESES = (
    ("01", "jan"),
    ("02", "fev"),
    ("03", "mar"),
    ("04", "abr"),
    ("05", "mai"),
    ("06", "jun"),
    ("07", "jul"),
    ("08", "ago"),
    ("09", "set"),
    ("10", "out"),
    ("11", "nov"),
    ("12", "dez"),
)


def montar_historico_mensal(ano=None):
    ano = str(ano or ano_atual())
    meses = [{"competencia": f"{numero}/{ano}", "rotulo": f"{nome}/{ano[-2:]}"} for numero, nome in MESES]

    empresas = get_db().execute(
        "SELECT id, cnpj, nome_empresa, status_empresa FROM empresas ORDER BY nome_empresa"
    ).fetchall()
    parcelas = get_db().execute(
        """
        SELECT *
        FROM parcelas
        WHERE competencia LIKE ?
        ORDER BY data_atualizacao DESC, id DESC
        """,
        (f"%/{ano}",),
    ).fetchall()

    por_empresa_mes = {}
    for parcela in parcelas:
        por_empresa_mes.setdefault((parcela["empresa_id"], parcela["competencia"]), parcela)

    linhas = []
    for empresa in empresas:
        celulas = []
        for mes in meses:
            parcela = por_empresa_mes.get((empresa["id"], mes["competencia"]))
            celulas.append(_celula(mes["competencia"], parcela))
        linhas.append({"empresa": empresa, "celulas": celulas})

    return {
        "ano": ano,
        "anos": listar_anos(),
        "meses": meses,
        "linhas": linhas,
    }


def listar_anos():
    anos = {str(datetime.now().year)}
    for row in get_db().execute("SELECT competencia FROM parcelas").fetchall():
        if row["competencia"] and "/" in row["competencia"]:
            anos.add(row["competencia"].split("/")[-1])
    return sorted(anos, reverse=True)


def _celula(competencia, parcela):
    if parcela is None:
        return {"competencia": competencia, "classe": "empty", "texto": "-", "detalhe": ""}

    if parcela["status_onvio"] == "ENVIADO":
        classe = "sent"
        texto = _formatar_valor(parcela["valor"]) or "Onvio"
    elif parcela["status_onvio"] == "PRONTO_PARA_SUBIR":
        classe = "ready"
        texto = _formatar_valor(parcela["valor"]) or "Emitida"
    elif parcela["status_emissao"] == "AGUARDANDO_API":
        classe = "waiting"
        texto = "API"
    elif parcela["status_emissao"] == "ERRO_EMISSAO":
        classe = "error"
        texto = "Erro"
    else:
        classe = "pending"
        texto = "Pendente"

    return {
        "competencia": competencia,
        "classe": classe,
        "texto": texto,
        "detalhe": parcela["mensagem"] or "",
    }


def _formatar_valor(valor):
    if valor is None:
        return ""
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return ""
    texto = f"{numero:,.2f}"
    return "R$ " + texto.replace(",", "X").replace(".", ",").replace("X", ".")
