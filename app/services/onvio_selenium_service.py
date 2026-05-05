from datetime import datetime
from pathlib import Path

from flask import current_app
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from app.services.onvio_log_service import registrar_onvio_log


class OnvioConfiguracaoErro(Exception):
    pass


class OnvioAutomacaoErro(Exception):
    pass


def subir_pdf_onvio_selenium(empresa, parcela, caminho_pdf):
    _validar_configuracao()
    caminho_pdf = Path(caminho_pdf).resolve()
    if not caminho_pdf.exists():
        raise OnvioAutomacaoErro("PDF nao encontrado para upload no Onvio.")

    driver = None
    try:
        registrar_onvio_log(
            acao="onvio_selenium",
            empresa_id=empresa["id"],
            parcela_id=parcela["id"],
            mensagem="Iniciando automacao Selenium do Onvio.",
        )
        driver = _criar_driver()
        wait = WebDriverWait(driver, current_app.config["ONVIO_WAIT_SECONDS"])

        _abrir_documentos_cliente(driver, wait)
        _autenticar_se_necessario(driver, wait)
        _abrir_documentos_cliente(driver, wait)
        _pesquisar_e_abrir_cliente(driver, wait, empresa)
        _abrir_pasta_fiscal_parcelamentos(driver, wait)
        _fazer_upload(driver, wait, caminho_pdf)
        _gerenciar_vencimento(driver, wait, caminho_pdf.name)

        registrar_onvio_log(
            acao="onvio_selenium",
            empresa_id=empresa["id"],
            parcela_id=parcela["id"],
            status="SUCESSO",
            mensagem="Documento enviado ao Onvio com sucesso.",
            detalhe_tecnico=caminho_pdf.name,
        )
        return "Guia de parcelamento subida com sucesso para Onvio."
    except (OnvioConfiguracaoErro, OnvioAutomacaoErro):
        raise
    except Exception as exc:
        registrar_onvio_log(
            acao="onvio_selenium",
            empresa_id=empresa["id"],
            parcela_id=parcela["id"],
            status="ERRO",
            mensagem="Falha na automacao do Onvio.",
            detalhe_tecnico=f"{type(exc).__name__}: {exc}",
        )
        raise OnvioAutomacaoErro(
            "Nao foi possivel concluir o upload no Onvio. Verifique login, cliente e pasta."
        ) from exc
    finally:
        if driver and current_app.config["ONVIO_HEADLESS"]:
            driver.quit()


def _validar_configuracao():
    faltando = []
    if not current_app.config["ONVIO_EMAIL"]:
        faltando.append("ONVIO_EMAIL")
    if not current_app.config["ONVIO_PASSWORD"]:
        faltando.append("ONVIO_PASSWORD")
    if faltando:
        raise OnvioConfiguracaoErro(
            "Credenciais Onvio nao configuradas no .env: " + ", ".join(faltando)
        )


def _criar_driver():
    browser = current_app.config["ONVIO_BROWSER"].lower()
    if browser not in ("edge", "chrome"):
        raise OnvioConfiguracaoErro("ONVIO_BROWSER deve ser edge ou chrome.")

    user_data_dir = Path(current_app.config["ONVIO_USER_DATA_DIR"])
    user_data_dir.mkdir(parents=True, exist_ok=True)

    if browser == "chrome":
        options = webdriver.ChromeOptions()
        options.add_argument(f"--user-data-dir={user_data_dir}")
        if current_app.config["ONVIO_HEADLESS"]:
            options.add_argument("--headless=new")
        return webdriver.Chrome(options=options)

    options = webdriver.EdgeOptions()
    options.add_argument(f"--user-data-dir={user_data_dir}")
    if current_app.config["ONVIO_HEADLESS"]:
        options.add_argument("--headless=new")
    return webdriver.Edge(options=options)


def _abrir_documentos_cliente(driver, wait):
    driver.get(current_app.config["ONVIO_URL"])
    wait.until(lambda d: d.execute_script("return document.readyState") == "complete")


def _autenticar_se_necessario(driver, wait):
    if not _esta_em_login(driver):
        return

    registrar_onvio_log(
        acao="onvio_login",
        mensagem="Sessao Onvio nao autenticada. Executando login simples.",
    )
    email = _primeiro_presente(
        driver,
        (
            "input[type='email']",
            "input[name*='email' i]",
            "input[id*='email' i]",
            "input[type='text']",
        ),
    )
    senha = _primeiro_presente(
        driver,
        (
            "input[type='password']",
            "input[name*='password' i]",
            "input[id*='password' i]",
            "input[name*='senha' i]",
            "input[id*='senha' i]",
        ),
    )
    if not email or not senha:
        raise OnvioAutomacaoErro("Tela de login Onvio detectada, mas campos nao foram encontrados.")

    email.clear()
    email.send_keys(current_app.config["ONVIO_EMAIL"])
    senha.clear()
    senha.send_keys(current_app.config["ONVIO_PASSWORD"])
    _clicar_primeiro_texto(driver, ("Entrar", "Login", "Sign in", "Acessar"))
    wait.until(lambda d: not _esta_em_login(d))


def _esta_em_login(driver):
    url = driver.current_url.lower()
    if "login" in url or "signin" in url or "auth" in url:
        return True
    return bool(driver.find_elements(By.CSS_SELECTOR, "input[type='password']"))


def _pesquisar_e_abrir_cliente(driver, wait, empresa):
    termo = empresa["nome_onvio"] or empresa["cnpj"] or empresa["nome_empresa"]
    campo_busca = _primeiro_presente(
        driver,
        (
            "input[placeholder*='Pesquisar' i]",
            "input[placeholder*='Cliente' i]",
            "input[aria-label*='Pesquisar' i]",
            "input[type='search']",
            "input[type='text']",
        ),
    )
    if not campo_busca:
        raise OnvioAutomacaoErro("Campo de pesquisa de cliente nao encontrado no Onvio.")

    campo_busca.clear()
    campo_busca.send_keys(termo)
    campo_busca.send_keys(Keys.ENTER)
    _clicar_texto_aproximado(driver, wait, (empresa["nome_onvio"], empresa["nome_empresa"], empresa["cnpj"]))


def _abrir_pasta_fiscal_parcelamentos(driver, wait):
    _clicar_texto_aproximado(driver, wait, ("Fiscal",))
    _clicar_texto_aproximado(driver, wait, ("Parcelamentos",))


def _fazer_upload(driver, wait, caminho_pdf):
    _clicar_primeiro_texto(driver, ("Upload", "Enviar", "Carregar"))
    file_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='file']")))
    file_input.send_keys(str(caminho_pdf))
    wait.until(lambda d: caminho_pdf.name.lower() in d.page_source.lower())


def _gerenciar_vencimento(driver, wait, nome_arquivo):
    _clicar_texto_aproximado(driver, wait, (nome_arquivo,))
    _clicar_primeiro_texto(driver, ("Gerenciar", "Manage"))

    hoje = datetime.now().strftime("%d/%m/%Y")
    campo_data = _primeiro_presente(
        driver,
        (
            "input[type='date']",
            "input[placeholder*='vencimento' i]",
            "input[aria-label*='vencimento' i]",
            "input[name*='vencimento' i]",
            "input[id*='vencimento' i]",
        ),
    )
    if not campo_data:
        raise OnvioAutomacaoErro("Campo de data de vencimento nao encontrado no Onvio.")

    campo_data.clear()
    if campo_data.get_attribute("type") == "date":
        campo_data.send_keys(datetime.now().strftime("%Y-%m-%d"))
    else:
        campo_data.send_keys(hoje)

    _clicar_primeiro_texto(driver, ("Salvar", "Aplicar", "Concluir", "OK"))


def _primeiro_presente(driver, seletores):
    for seletor in seletores:
        elementos = driver.find_elements(By.CSS_SELECTOR, seletor)
        for elemento in elementos:
            if elemento.is_displayed() and elemento.is_enabled():
                return elemento
    return None


def _clicar_texto_aproximado(driver, wait, textos):
    textos = [texto for texto in textos if texto]
    ultimo_erro = None
    for texto in textos:
        try:
            xpath = (
                "//*[self::a or self::button or @role='button' or self::span or self::div]"
                f"[contains(normalize-space(.), { _xpath_literal(texto) })]"
            )
            elemento = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elemento)
            elemento.click()
            return
        except Exception as exc:
            ultimo_erro = exc
    raise OnvioAutomacaoErro(f"Elemento nao encontrado no Onvio: {', '.join(textos)}") from ultimo_erro


def _clicar_primeiro_texto(driver, textos):
    for texto in textos:
        xpath = (
            "//*[self::button or self::a or @role='button']"
            f"[contains(normalize-space(.), { _xpath_literal(texto) })]"
        )
        elementos = driver.find_elements(By.XPATH, xpath)
        for elemento in elementos:
            if elemento.is_displayed() and elemento.is_enabled():
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elemento)
                elemento.click()
                return
    raise OnvioAutomacaoErro(f"Botao nao encontrado no Onvio: {', '.join(textos)}")


def _xpath_literal(texto):
    if "'" not in texto:
        return f"'{texto}'"
    if '"' not in texto:
        return f'"{texto}"'
    partes = texto.split("'")
    return "concat(" + ", \"'\", ".join(f"'{parte}'" for parte in partes) + ")"
