import re

from app.database import get_db
def limpar_cnpj(cnpj):
    return re.sub(r"\D", "", cnpj or "")


def validar_cnpj_basico(cnpj):
    cnpj_limpo = limpar_cnpj(cnpj)
    return len(cnpj_limpo) == 14 and len(set(cnpj_limpo)) > 1


def validar_empresa(dados, empresa_id=None):
    erros = []
    cnpj = limpar_cnpj(dados.get("cnpj"))
    nome_empresa = (dados.get("nome_empresa") or "").strip()

    if not validar_cnpj_basico(cnpj):
        erros.append("Informe um CNPJ valido com 14 digitos.")
    if not nome_empresa:
        erros.append("Nome da empresa obrigatorio.")

    existente = buscar_empresa_por_cnpj(cnpj) if cnpj else None
    if existente and existente["id"] != empresa_id:
        erros.append("Ja existe empresa cadastrada com esse CNPJ.")

    return erros


def listar_empresas_com_parcela_atual(status_empresa="ATIVA"):
    filtro_status = ""
    parametros = []
    if status_empresa in ("ATIVA", "INATIVA"):
        filtro_status = "WHERE empresas.status_empresa = ?"
        parametros.append(status_empresa)

    return get_db().execute(
        f"""
        SELECT
            empresas.*,
            parcelas.id AS parcela_id,
            parcelas.competencia,
            parcelas.valor,
            parcelas.vencimento,
            parcelas.caminho_pdf,
            parcelas.status_emissao,
            parcelas.status_onvio,
            parcelas.mensagem,
            parcelas.data_emissao,
            parcelas.data_envio_onvio
        FROM empresas
        LEFT JOIN parcelas
            ON parcelas.empresa_id = empresas.id
           AND parcelas.id = (
                SELECT id
                FROM parcelas AS ultima_parcela
                WHERE ultima_parcela.empresa_id = empresas.id
                ORDER BY ultima_parcela.data_atualizacao DESC, ultima_parcela.id DESC
                LIMIT 1
           )
        {filtro_status}
        ORDER BY empresas.nome_empresa
        """,
        parametros,
    ).fetchall()


def buscar_empresa(empresa_id):
    return get_db().execute("SELECT * FROM empresas WHERE id = ?", (empresa_id,)).fetchone()


def buscar_empresa_por_cnpj(cnpj):
    return get_db().execute(
        "SELECT * FROM empresas WHERE cnpj = ?",
        (limpar_cnpj(cnpj),),
    ).fetchone()


def criar_empresa(dados):
    erros = validar_empresa(dados)
    if erros:
        return None, erros

    cursor = get_db().execute(
        """
        INSERT INTO empresas (
            cnpj,
            nome_empresa,
            nome_onvio,
            pasta_onvio,
            status_empresa,
            observacao
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        _empresa_params(dados),
    )
    get_db().commit()
    return cursor.lastrowid, []


def atualizar_empresa(empresa_id, dados):
    erros = validar_empresa(dados, empresa_id=empresa_id)
    if erros:
        return erros

    get_db().execute(
        """
        UPDATE empresas
        SET cnpj = ?,
            nome_empresa = ?,
            nome_onvio = ?,
            pasta_onvio = ?,
            status_empresa = ?,
            observacao = ?,
            data_atualizacao = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (*_empresa_params(dados), empresa_id),
    )
    get_db().commit()
    return []


def _empresa_params(dados):
    status = dados.get("status_empresa") or "ATIVA"
    if status not in ("ATIVA", "INATIVA"):
        status = "ATIVA"

    return (
        limpar_cnpj(dados.get("cnpj")),
        (dados.get("nome_empresa") or "").strip(),
        (dados.get("nome_onvio") or "").strip(),
        (dados.get("pasta_onvio") or "").strip(),
        status,
        (dados.get("observacao") or "").strip(),
    )
