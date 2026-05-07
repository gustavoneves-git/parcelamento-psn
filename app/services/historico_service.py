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


def montar_historico_mensal(ano=None, status_empresa="ATIVA"):
    ano = str(ano or ano_atual())
    status_empresa = (status_empresa or "ATIVA").upper()
    if status_empresa not in ("ATIVA", "INATIVA", "TODAS"):
        status_empresa = "ATIVA"
    meses = [{"competencia": f"{numero}/{ano}", "rotulo": f"{nome}/{ano[-2:]}"} for numero, nome in MESES]

    if status_empresa == "TODAS":
        empresas = get_db().execute(
            "SELECT id, cnpj, nome_empresa, status_empresa FROM empresas ORDER BY nome_empresa"
        ).fetchall()
    else:
        empresas = get_db().execute(
            """
            SELECT id, cnpj, nome_empresa, status_empresa
            FROM empresas
            WHERE status_empresa = ?
            ORDER BY nome_empresa
            """,
            (status_empresa,),
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
        "filtro_status": status_empresa,
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

    valor_formatado = _formatar_valor(parcela["valor"])
    if parcela["status_onvio"] == "ENVIADO":
        classe = "sent"
        texto = valor_formatado or "Onvio"
    elif parcela["status_onvio"] == "PRONTO_PARA_SUBIR":
        classe = "ready"
        texto = valor_formatado or "Emitida"
    elif valor_formatado:
        classe = "history"
        texto = valor_formatado
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
