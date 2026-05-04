from app.database import get_db
from app.services.empresa_service import buscar_empresa
from app.services.periodo_service import competencia_atual
from app.services.serpro_service import (
    SerproErro,
    SerproNaoConfigurado,
    emitir_guia_parcelamento,
)


def emitir_parcela_mes_atual(empresa_id):
    empresa = buscar_empresa(empresa_id)
    if empresa is None:
        return _resultado("Empresa nao encontrada.", "error")

    competencia = competencia_atual()
    try:
        guia = emitir_guia_parcelamento(empresa, competencia)
    except SerproNaoConfigurado as exc:
        _salvar_status_sem_pdf(empresa_id, competencia, "AGUARDANDO_API", str(exc))
        return _resultado(str(exc), "warning")
    except NotImplementedError as exc:
        _salvar_status_sem_pdf(empresa_id, competencia, "AGUARDANDO_API", str(exc))
        return _resultado(str(exc), "warning")
    except SerproErro as exc:
        _salvar_status_sem_pdf(empresa_id, competencia, "ERRO_EMISSAO", str(exc))
        return _resultado(str(exc), "error")
    except Exception as exc:
        _salvar_status_sem_pdf(empresa_id, competencia, "ERRO_EMISSAO", str(exc))
        return _resultado("Erro ao emitir parcela pela API SERPRO.", "error")

    _salvar_parcela_emitida(empresa_id, competencia, guia)
    return _resultado("Parcela desse mes emitida com sucesso.", "success")


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
