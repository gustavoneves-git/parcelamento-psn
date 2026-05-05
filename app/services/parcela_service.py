from app.database import get_db
from app.services.empresa_service import buscar_empresa
from app.services.periodo_service import competencia_atual
from app.services.psn_disponibilidade_service import (
    buscar_disponibilidade_emitivel,
    marcar_disponibilidade_emitida,
)
from app.services.serpro_service import (
    SerproAviso,
    SerproErro,
    SerproNaoConfigurado,
    emitir_guia_parcelamento,
)


def emitir_parcela_mes_atual(empresa_id):
    return emitir_parcela_competencia(empresa_id, competencia_atual())


def emitir_parcela_competencia(empresa_id, competencia):
    empresa = buscar_empresa(empresa_id)
    if empresa is None:
        return _resultado("Empresa nao encontrada.", "error")

    if not buscar_disponibilidade_emitivel(empresa_id, competencia):
        _salvar_status_sem_pdf(
            empresa_id,
            competencia,
            "AGUARDANDO_API",
            "Consulte o SERPRO antes de emitir. Essa competencia ainda nao esta marcada como disponivel.",
        )
        return _resultado(
            "Consulte o SERPRO antes de emitir. Essa competencia ainda nao esta liberada.",
            "warning",
        )

    try:
        guia = emitir_guia_parcelamento(empresa, competencia)
    except SerproNaoConfigurado as exc:
        _salvar_status_sem_pdf(empresa_id, competencia, "AGUARDANDO_API", str(exc))
        return _resultado(str(exc), "warning")
    except NotImplementedError as exc:
        _salvar_status_sem_pdf(empresa_id, competencia, "AGUARDANDO_API", str(exc))
        return _resultado(str(exc), "warning")
    except SerproAviso as exc:
        _salvar_status_sem_pdf(empresa_id, competencia, "AGUARDANDO_API", str(exc))
        return _resultado(_mensagem_amigavel_serpro(str(exc)), "warning")
    except SerproErro as exc:
        _salvar_status_sem_pdf(empresa_id, competencia, "ERRO_EMISSAO", str(exc))
        return _resultado(str(exc), "error")
    except Exception as exc:
        _salvar_status_sem_pdf(empresa_id, competencia, "ERRO_EMISSAO", str(exc))
        return _resultado("Erro ao emitir parcela pela API SERPRO.", "error")

    _salvar_parcela_emitida(empresa_id, competencia, guia)
    marcar_disponibilidade_emitida(
        empresa_id,
        competencia,
        "Parcela emitida com sucesso.",
    )
    return _resultado(f"Parcela {competencia} emitida com sucesso.", "success")


def buscar_parcela_atual(empresa_id):
    return get_db().execute(
        """
        SELECT *
        FROM parcelas
        WHERE empresa_id = ?
          AND competencia = ?
        """,
        (empresa_id, competencia_atual()),
    ).fetchone()


def buscar_parcela_pronta_onvio(empresa_id):
    return get_db().execute(
        """
        SELECT *
        FROM parcelas
        WHERE empresa_id = ?
          AND status_onvio = 'PRONTO_PARA_SUBIR'
        ORDER BY data_atualizacao DESC, id DESC
        LIMIT 1
        """,
        (empresa_id,),
    ).fetchone()


def _salvar_status_sem_pdf(empresa_id, competencia, status, mensagem):
    get_db().execute(
        """
        INSERT INTO parcelas (
            empresa_id,
            competencia,
            status_emissao,
            status_onvio,
            mensagem
        ) VALUES (?, ?, ?, 'NAO_DISPONIVEL', ?)
        ON CONFLICT(empresa_id, competencia) DO UPDATE SET
            status_emissao = excluded.status_emissao,
            status_onvio = 'NAO_DISPONIVEL',
            mensagem = excluded.mensagem,
            data_atualizacao = CURRENT_TIMESTAMP
        """,
        (empresa_id, competencia, status, mensagem),
    )
    get_db().commit()


def _salvar_parcela_emitida(empresa_id, competencia, guia):
    get_db().execute(
        """
        INSERT INTO parcelas (
            empresa_id,
            competencia,
            valor,
            vencimento,
            caminho_pdf,
            status_emissao,
            status_onvio,
            mensagem,
            data_emissao
        ) VALUES (?, ?, ?, ?, ?, 'EMITIDA', 'PRONTO_PARA_SUBIR', ?, CURRENT_TIMESTAMP)
        ON CONFLICT(empresa_id, competencia) DO UPDATE SET
            valor = excluded.valor,
            vencimento = excluded.vencimento,
            caminho_pdf = excluded.caminho_pdf,
            status_emissao = 'EMITIDA',
            status_onvio = 'PRONTO_PARA_SUBIR',
            mensagem = excluded.mensagem,
            data_emissao = CURRENT_TIMESTAMP,
            data_atualizacao = CURRENT_TIMESTAMP
        """,
        (
            empresa_id,
            competencia,
            guia.get("valor"),
            guia.get("vencimento"),
            guia.get("caminho_pdf"),
            "Parcela desse mes emitida com sucesso.",
        ),
    )
    get_db().commit()


def _resultado(mensagem, categoria):
    return {"mensagem": mensagem, "categoria": categoria}


def _mensagem_amigavel_serpro(mensagem):
    texto = mensagem.lower()
    if "indispon" in texto:
        return "A parcela ainda nao esta disponivel para emissao no SERPRO."
    if "pagamento" in texto or "paga" in texto:
        return "A parcela nao esta disponivel porque pode ja constar como paga."
    if "futuro" in texto:
        return "A competencia informada ainda nao esta liberada para emissao."
    return mensagem
