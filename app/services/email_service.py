import smtplib
from email.message import EmailMessage

from flask import current_app


def enviar_email_erro_interno(erro):
    if not current_app.config["ERROR_EMAIL_ENABLED"]:
        return False, "Envio de e-mail desativado."

    if not current_app.config["SMTP_HOST"]:
        return False, "SMTP_HOST nao configurado."

    mensagem = EmailMessage()
    mensagem["Subject"] = (
        f"[PSN] Erro interno {erro['codigo_ocorrencia']} - {erro['tipo_erro']}"
    )
    mensagem["From"] = current_app.config["SMTP_FROM"]
    mensagem["To"] = current_app.config["ERROR_EMAIL_TO"]
    mensagem.set_content(_corpo_email(erro))

    with smtplib.SMTP(
        current_app.config["SMTP_HOST"],
        current_app.config["SMTP_PORT"],
        timeout=20,
    ) as smtp:
        if current_app.config["SMTP_USE_TLS"]:
            smtp.starttls()
        if current_app.config["SMTP_USER"]:
            smtp.login(
                current_app.config["SMTP_USER"],
                current_app.config["SMTP_PASSWORD"],
            )
        smtp.send_message(mensagem)

    return True, ""


def _corpo_email(erro):
    partes = [
        "Erro interno no sistema PSN.",
        "",
        f"Codigo da ocorrencia: {erro['codigo_ocorrencia']}",
        f"Sistema: {erro['sistema']}",
        f"Versao: {erro.get('versao_sistema') or '-'}",
        f"Empresa ID: {erro.get('empresa_id') or '-'}",
        f"Usuario: {erro.get('usuario') or '-'}",
        f"Tela: {erro.get('tela') or '-'}",
        f"Acao: {erro.get('acao') or '-'}",
        f"Rota: {erro.get('rota') or '-'}",
        f"Metodo: {erro.get('metodo_http') or '-'}",
        f"Competencia: {erro.get('competencia') or '-'}",
        f"Tipo do erro: {erro['tipo_erro']}",
        f"Mensagem: {erro.get('mensagem_erro') or '-'}",
        "",
        "Detalhe tecnico:",
        erro.get("detalhe_tecnico") or "-",
        "",
        "Contexto:",
        erro.get("contexto_json") or "-",
        "",
        "Stack trace:",
        erro.get("stack_trace") or "-",
    ]
    return "\n".join(partes)
