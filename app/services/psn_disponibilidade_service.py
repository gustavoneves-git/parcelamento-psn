import json
import re

from app.database import get_db
from app.services.empresa_service import buscar_empresa
from app.services.periodo_service import competencia_atual
from app.services.serpro_log_service import registrar_serpro_log
from app.services.serpro_service import (
    SerproErro,
    SerproNaoConfigurado,
    consultar_parcelas_disponiveis_psn,
)


def consultar_e_salvar_disponibilidades(empresa_id):
    empresa = buscar_empresa(empresa_id)
    if empresa is None:
        return _resultado("Empresa nao encontrada.", "error")

    try:
        resposta = consultar_parcelas_disponiveis_psn(empresa)
    except SerproNaoConfigurado as exc:
        _registrar_indisponibilidade_tecnica(empresa_id, str(exc))
        return _resultado(str(exc), "warning")
    except SerproErro as exc:
        _registrar_indisponibilidade_tecnica(empresa_id, str(exc))
        return _resultado("Nao foi possivel consultar parcelas no SERPRO agora.", "error")
    except Exception as exc:
        _registrar_indisponibilidade_tecnica(empresa_id, str(exc))
        return _resultado("Erro tecnico ao consultar parcelas no SERPRO.", "error")

    parcelas = extrair_parcelas_disponiveis(resposta)
    mensagem = mensagem_serpro(resposta) or "Consulta realizada com sucesso."
    _limpar_disponibilidades_ativas(empresa_id)

    if not parcelas:
        _salvar_disponibilidade(
            empresa_id=empresa_id,
            competencia=competencia_atual(),
            parcela_aaaamm=_competencia_para_aaaamm(competencia_atual()),
            status="INDISPONIVEL",
            mensagem=mensagem,
            resposta_resumo=_resumo_resposta(resposta),
        )
        registrar_serpro_log(
            acao="disponibilidade_psn",
            empresa_id=empresa_id,
            competencia=competencia_atual(),
            status="INFO",
            mensagem="Consulta PSN sem parcelas disponiveis.",
            detalhe_tecnico=mensagem,
        )
        return _resultado("Nenhuma parcela disponivel para emissao no momento.", "warning")

    for parcela in parcelas:
        _salvar_disponibilidade(
            empresa_id=empresa_id,
            competencia=parcela["competencia"],
            parcela_aaaamm=parcela["parcela_aaaamm"],
            status="DISPONIVEL",
            mensagem=parcela.get("mensagem") or "Parcela disponivel para emissao.",
            resposta_resumo=_resumo_resposta(resposta),
        )

    registrar_serpro_log(
        acao="disponibilidade_psn",
        empresa_id=empresa_id,
        status="SUCESSO",
        mensagem=f"{len(parcelas)} parcela(s) disponivel(is) para emissao.",
        detalhe_tecnico=", ".join(p["parcela_aaaamm"] for p in parcelas),
    )
    return _resultado(f"{len(parcelas)} parcela(s) disponivel(is) para emissao.", "success")


def listar_disponibilidades_por_empresa():
    rows = get_db().execute(
        """
        SELECT *
        FROM psn_disponibilidades
        WHERE id IN (
            SELECT MAX(id)
            FROM psn_disponibilidades
            GROUP BY empresa_id, parcela_aaaamm
        )
        ORDER BY data_consulta DESC, parcela_aaaamm DESC
        """
    ).fetchall()
    por_empresa = {}
    for row in rows:
        por_empresa.setdefault(row["empresa_id"], []).append(row)
    return por_empresa


def buscar_disponibilidade_emitivel(empresa_id, competencia):
    return get_db().execute(
        """
        SELECT *
        FROM psn_disponibilidades
        WHERE empresa_id = ?
          AND competencia = ?
          AND status_disponibilidade = 'DISPONIVEL'
        ORDER BY data_consulta DESC, id DESC
        LIMIT 1
        """,
        (empresa_id, competencia),
    ).fetchone()


def marcar_disponibilidade_emitida(empresa_id, competencia, mensagem):
    get_db().execute(
        """
        UPDATE psn_disponibilidades
        SET status_disponibilidade = 'INDISPONIVEL',
            mensagem = ?,
            data_consulta = CURRENT_TIMESTAMP
        WHERE empresa_id = ?
          AND competencia = ?
        """,
        (mensagem, empresa_id, competencia),
    )
    get_db().commit()


def extrair_parcelas_disponiveis(resposta):
    dados = _normalizar_dados(resposta.get("dados") if isinstance(resposta, dict) else resposta)
    encontrados = []
    for item in _iterar_objetos(dados):
        parcela_aaaamm = _extrair_aaaamm(item)
        if not parcela_aaaamm:
            continue
        encontrados.append(
            {
                "parcela_aaaamm": parcela_aaaamm,
                "competencia": _aaaamm_para_competencia(parcela_aaaamm),
                "mensagem": _extrair_mensagem_item(item),
            }
        )

    unicos = {}
    for item in encontrados:
        unicos[item["parcela_aaaamm"]] = item
    return list(unicos.values())


def mensagem_serpro(resposta):
    mensagens = resposta.get("mensagens") if isinstance(resposta, dict) else None
    if not mensagens:
        return ""
    textos = []
    for mensagem in mensagens:
        if isinstance(mensagem, dict):
            textos.append(mensagem.get("texto") or mensagem.get("codigo") or "")
        else:
            textos.append(str(mensagem))
    return " ".join(texto for texto in textos if texto)


def _normalizar_dados(dados):
    if not isinstance(dados, str):
        return dados
    texto = dados.strip()
    if not texto:
        return []
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        return texto


def _iterar_objetos(valor):
    if isinstance(valor, dict):
        yield valor
        for item in valor.values():
            yield from _iterar_objetos(item)
    elif isinstance(valor, list):
        for item in valor:
            yield from _iterar_objetos(item)
    elif isinstance(valor, str):
        yield valor


def _extrair_aaaamm(item):
    if isinstance(item, str):
        return _primeiro_aaaamm(item)
    if not isinstance(item, dict):
        return ""

    chaves_preferidas = (
        "parcelaParaEmitir",
        "competencia",
        "periodoApuracao",
        "pa",
        "mesAno",
        "parcela",
    )
    for chave in chaves_preferidas:
        if chave in item:
            encontrado = _primeiro_aaaamm(str(item[chave]))
            if encontrado:
                return encontrado
    return _primeiro_aaaamm(json.dumps(item, ensure_ascii=False))


def _primeiro_aaaamm(texto):
    for candidato in re.findall(r"\b(20\d{2}(0[1-9]|1[0-2]))\b", texto):
        return candidato[0]
    match = re.search(r"\b(0[1-9]|1[0-2])[/.-](20\d{2})\b", texto)
    if match:
        return f"{match.group(2)}{match.group(1)}"
    return ""


def _extrair_mensagem_item(item):
    if not isinstance(item, dict):
        return ""
    for chave in ("mensagem", "descricao", "situacao", "status"):
        if item.get(chave):
            return str(item[chave])
    return ""


def _salvar_disponibilidade(
    empresa_id,
    competencia,
    parcela_aaaamm,
    status,
    mensagem,
    resposta_resumo,
):
    get_db().execute(
        """
        INSERT INTO psn_disponibilidades (
            empresa_id,
            competencia,
            parcela_aaaamm,
            status_disponibilidade,
            mensagem,
            resposta_resumo
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(empresa_id, parcela_aaaamm) DO UPDATE SET
            competencia = excluded.competencia,
            status_disponibilidade = excluded.status_disponibilidade,
            mensagem = excluded.mensagem,
            resposta_resumo = excluded.resposta_resumo,
            data_consulta = CURRENT_TIMESTAMP
        """,
        (empresa_id, competencia, parcela_aaaamm, status, mensagem, resposta_resumo),
    )
    get_db().commit()


def _limpar_disponibilidades_ativas(empresa_id):
    get_db().execute(
        """
        UPDATE psn_disponibilidades
        SET status_disponibilidade = 'INDISPONIVEL',
            mensagem = 'Disponibilidade atualizada em nova consulta.',
            data_consulta = CURRENT_TIMESTAMP
        WHERE empresa_id = ?
          AND status_disponibilidade = 'DISPONIVEL'
        """,
        (empresa_id,),
    )
    get_db().commit()


def _registrar_indisponibilidade_tecnica(empresa_id, mensagem):
    _salvar_disponibilidade(
        empresa_id=empresa_id,
        competencia=competencia_atual(),
        parcela_aaaamm=_competencia_para_aaaamm(competencia_atual()),
        status="ERRO_CONSULTA",
        mensagem=mensagem,
        resposta_resumo=mensagem,
    )


def _resumo_resposta(resposta):
    return json.dumps(resposta, ensure_ascii=False)[:2000]


def _competencia_para_aaaamm(competencia):
    mes, ano = competencia.split("/")
    return f"{ano}{mes.zfill(2)}"


def _aaaamm_para_competencia(parcela_aaaamm):
    return f"{parcela_aaaamm[4:6]}/{parcela_aaaamm[:4]}"


def _resultado(mensagem, categoria):
    return {"mensagem": mensagem, "categoria": categoria}
