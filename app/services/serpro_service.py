from flask import current_app


class SerproNaoConfigurado(Exception):
    pass


def emitir_guia_parcelamento(empresa, competencia):
    """Ponto unico da futura integracao com SERPRO Integra Parcelamento."""
    if not _configurado():
        raise SerproNaoConfigurado(
            "API SERPRO ainda nao configurada. Informe credenciais e certificado para emitir a guia."
        )

    raise NotImplementedError(
        "Contrato SERPRO pendente. Implementar chamada real quando as credenciais forem liberadas."
    )


def _configurado():
    return bool(
        current_app.config.get("SERPRO_CLIENT_ID")
        and current_app.config.get("SERPRO_CLIENT_SECRET")
        and current_app.config.get("SERPRO_CERT_PATH")
    )
