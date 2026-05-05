import json
import os
import sys
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
    contexto = _contexto_automacao(empresa, parcela, caminho_pdf)
    try:
        _registrar_etapa(
            contexto,
            etapa="iniciar",
            status="INFO",
            mensagem="Iniciando automacao Selenium do Onvio.",
        )
        driver = _executar_etapa(
            contexto,
            "criar_navegador",
            "Navegador Selenium iniciado.",
            _criar_driver,
        )
        wait = WebDriverWait(driver, current_app.config["ONVIO_WAIT_SECONDS"])

        _executar_etapa(
            contexto,
            "abrir_documentos_cliente",
            "Tela de documentos do cliente carregada.",
            _abrir_documentos_cliente,
            driver,
            wait,
            driver=driver,
        )
        _executar_etapa(
            contexto,
            "verificar_sessao_login",
            "Sessao Onvio verificada.",
            _autenticar_se_necessario,
            driver,
            wait,
            contexto,
            driver=driver,
        )
        _executar_etapa(
            contexto,
            "retomar_documentos_cliente",
            "Tela de documentos do cliente pronta apos verificacao de login.",
            _abrir_documentos_cliente,
            driver,
            wait,
            driver=driver,
        )
        _executar_etapa(
            contexto,
            "pesquisar_cliente",
            "Cliente localizado e aberto no Onvio.",
            _pesquisar_e_abrir_cliente,
            driver,
            wait,
            empresa,
            driver=driver,
        )
        _executar_etapa(
            contexto,
            "abrir_fiscal_parcelamentos",
            "Pasta Fiscal/Parcelamentos aberta.",
            _abrir_pasta_fiscal_parcelamentos,
            driver,
            wait,
            driver=driver,
        )
        _executar_etapa(
            contexto,
            "upload",
            "PDF enviado para o Onvio.",
            _fazer_upload,
            driver,
            wait,
            caminho_pdf,
            driver=driver,
        )
        _executar_etapa(
            contexto,
            "gerenciar_vencimento",
            "Vencimento preenchido e alteracao concluida.",
            _gerenciar_vencimento,
            driver,
            wait,
            caminho_pdf.name,
            driver=driver,
        )

        _registrar_etapa(
            contexto,
            etapa="concluir",
            status="SUCESSO",
            mensagem="Documento enviado ao Onvio com sucesso.",
            driver=driver,
        )
        return "Guia de parcelamento subida com sucesso para Onvio."
    except (OnvioConfiguracaoErro, OnvioAutomacaoErro):
        raise
    except Exception as exc:
        _registrar_etapa(
            contexto,
            etapa="erro_inesperado",
            status="ERRO",
            mensagem="Falha na automacao do Onvio.",
            driver=driver,
            detalhe=f"{type(exc).__name__}: {exc}",
        )
        raise OnvioAutomacaoErro(
            "Nao foi possivel concluir o upload no Onvio. Verifique login, cliente e pasta."
        ) from exc
    finally:
        if driver and current_app.config["ONVIO_HEADLESS"]:
            driver.quit()


def _contexto_automacao(empresa, parcela, caminho_pdf):
    return {
        "empresa_id": empresa["id"],
        "parcela_id": parcela["id"],
        "empresa_nome": empresa["nome_empresa"],
        "empresa_cnpj": empresa["cnpj"],
        "arquivo_pdf": caminho_pdf.name,
        "caminho_pdf": str(caminho_pdf),
        "modo": "selenium",
    }


def _executar_etapa(contexto, etapa, mensagem_sucesso, funcao, *args, driver=None):
    _registrar_etapa(
        contexto,
        etapa=etapa,
        status="INFO",
        mensagem=f"Iniciando etapa: {etapa}.",
        driver=driver,
    )
    try:
        resultado = funcao(*args)
    except OnvioAutomacaoErro as exc:
        _registrar_etapa(
            contexto,
            etapa=etapa,
            status="ERRO",
            mensagem=str(exc),
            driver=driver,
            detalhe=f"{type(exc).__name__}: {exc}",
        )
        raise
    except (TimeoutException, WebDriverException) as exc:
        mensagem = (
            "Falha de calibracao da automacao Onvio. "
            "A tela pode ter mudado, carregado fora do tempo esperado ou o seletor nao foi encontrado."
        )
        _registrar_etapa(
            contexto,
            etapa=etapa,
            status="ERRO",
            mensagem=mensagem,
            driver=driver,
            detalhe=f"{type(exc).__name__}: {exc}",
        )
        raise OnvioAutomacaoErro(mensagem) from exc
    except Exception as exc:
        mensagem = "Falha inesperada durante a automacao Onvio."
        _registrar_etapa(
            contexto,
            etapa=etapa,
            status="ERRO",
            mensagem=mensagem,
            driver=driver,
            detalhe=f"{type(exc).__name__}: {exc}",
        )
        raise

    _registrar_etapa(
        contexto,
        etapa=etapa,
        status="SUCESSO",
        mensagem=mensagem_sucesso,
        driver=driver,
    )
    return resultado


def _registrar_etapa(contexto, etapa, status, mensagem, driver=None, detalhe=""):
    detalhe_tecnico = {
        "modo": contexto["modo"],
        "etapa": etapa,
        "empresa_nome": contexto["empresa_nome"],
        "empresa_cnpj": contexto["empresa_cnpj"],
        "arquivo_pdf": contexto["arquivo_pdf"],
        "caminho_pdf": contexto["caminho_pdf"],
        "url_atual": _url_atual(driver),
        "detalhe": detalhe,
    }
    registrar_onvio_log(
        acao=f"onvio_selenium:{etapa}",
        empresa_id=contexto["empresa_id"],
        parcela_id=contexto["parcela_id"],
        status=status,
        mensagem=mensagem,
        detalhe_tecnico=json.dumps(detalhe_tecnico, ensure_ascii=True),
    )


def _url_atual(driver):
    if not driver:
        return ""
    try:
        return driver.current_url
    except WebDriverException:
        return ""


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

    user_data_dir = _resolver_user_data_dir(browser)
    user_data_dir.mkdir(parents=True, exist_ok=True)

    if browser == "chrome":
        options = webdriver.ChromeOptions()
        _aplicar_opcoes_navegador(options, user_data_dir)
        if current_app.config["ONVIO_HEADLESS"]:
            options.add_argument("--headless=new")
        return webdriver.Chrome(options=options)

    options = webdriver.EdgeOptions()
    _aplicar_opcoes_navegador(options, user_data_dir)
    if current_app.config["ONVIO_HEADLESS"]:
        options.add_argument("--headless=new")
    return webdriver.Edge(options=options)


def _resolver_user_data_dir(browser):
    configurado = Path(current_app.config["ONVIO_USER_DATA_DIR"])
    if sys.platform != "win32":
        return configurado

    texto = str(configurado)
    if texto.startswith("\\\\wsl.localhost\\") or texto.startswith("\\\\wsl$\\"):
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            return Path(local_appdata) / "PSN Parcelamento" / f"onvio_{browser}_profile"

    return configurado


def _aplicar_opcoes_navegador(options, user_data_dir):
    options.add_argument(f"--user-data-dir={user_data_dir}")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])


def _abrir_documentos_cliente(driver, wait):
    driver.get(current_app.config["ONVIO_URL"])
    wait.until(lambda d: d.execute_script("return document.readyState") == "complete")


def _autenticar_se_necessario(driver, wait, contexto):
    if not _esta_em_login(driver):
        _registrar_etapa(
            contexto,
            etapa="sessao_ativa",
            status="INFO",
            mensagem="Sessao Onvio ja estava autenticada.",
            driver=driver,
        )
        return

    _registrar_etapa(
        contexto,
        etapa="login",
        status="INFO",
        mensagem="Sessao Onvio nao autenticada. Executando login simples.",
        driver=driver,
    )
    _abrir_formulario_login_se_necessario(driver, wait)
    email = _primeiro_presente(
        driver,
        (
            "input[name='username']",
            "input#username",
            "input[type='email']",
            "input[name='uid']",
            "input[name*='email' i]",
            "input[id*='email' i]",
            "input[type='text']",
        ),
    )
    senha = _primeiro_presente(
        driver,
        (
            "input[type='password']",
            "input[name='password']",
            "input[name='pwd']",
            "input#password",
            "input#pwd",
            "input[name*='password' i]",
            "input[id*='password' i]",
            "input[name*='senha' i]",
            "input[id*='senha' i]",
        ),
    )
    if not email:
        raise OnvioAutomacaoErro("Tela de login Onvio detectada, mas campo de e-mail nao foi encontrado.")

    email.clear()
    email.send_keys(current_app.config["ONVIO_EMAIL"])
    if not senha:
        _clicar_primeiro_texto(driver, ("Entrar", "Continuar", "Continue", "Next"))
        senha = wait.until(
            lambda d: _primeiro_presente(
                d,
                (
                    "input[type='password']",
                    "input[name='password']",
                    "input[name='pwd']",
                    "input#password",
                    "input#pwd",
                ),
            )
        )

    senha.clear()
    senha.send_keys(current_app.config["ONVIO_PASSWORD"])
    _clicar_primeiro_texto(driver, ("Entrar", "Login", "Sign in", "Acessar"))
    wait.until(lambda d: _esta_em_mfa(d) or not _esta_em_login(d))
    if _esta_em_mfa(driver):
        raise OnvioAutomacaoErro(
            "Onvio solicitou validacao adicional de login. "
            "Conclua a autenticacao manualmente no Chrome e tente subir novamente."
        )

    _registrar_etapa(
        contexto,
        etapa="login",
        status="SUCESSO",
        mensagem="Login Onvio concluido.",
        driver=driver,
    )


def _abrir_formulario_login_se_necessario(driver, wait):
    if _primeiro_presente(driver, ("input[name='username']", "input#username", "input[type='email']")):
        return

    url = driver.current_url.lower()
    if "onvio.com.br/login" in url:
        try:
            botao = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "#trauth-continue-signin-btn"))
            )
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", botao)
            botao.click()
        except Exception:
            _clicar_primeiro_texto(driver, ("Entrar", "Login", "Sign in", "Acessar"))

        wait.until(
            lambda d: "auth.thomsonreuters.com" in d.current_url.lower()
            or bool(_primeiro_presente(d, ("input[name='username']", "input#username", "input[type='email']")))
        )


def _esta_em_login(driver):
    url = driver.current_url.lower()
    if "login" in url or "signin" in url or "auth" in url:
        return True
    return bool(driver.find_elements(By.CSS_SELECTOR, "input[type='password']"))


def _esta_em_mfa(driver):
    url = driver.current_url.lower()
    if "mfa" in url or "multi-factor" in url or "multifactor" in url:
        return True
    seletores = (
        "input[name*='mfa' i]",
        "input[id*='mfa' i]",
        "input[name*='code' i]",
        "input[placeholder*='codigo' i]",
        "input[placeholder*='código' i]",
    )
    return any(driver.find_elements(By.CSS_SELECTOR, seletor) for seletor in seletores)


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
