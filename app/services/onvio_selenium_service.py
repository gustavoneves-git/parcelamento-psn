import json
import os
import sys
import unicodedata
from calendar import monthrange
from datetime import datetime
from pathlib import Path

from flask import current_app
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from app.services.onvio_log_service import registrar_onvio_log
from app.services.outlook_graph_service import (
    OutlookGraphErro,
    OutlookGraphNaoConfigurado,
    buscar_codigo_onvio,
)


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
            "PDF enviado ao cliente.",
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
            mensagem="Documento enviado ao cliente com sucesso.",
            driver=driver,
        )
        return "Guia enviada ao cliente com sucesso."
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
            "Nao foi possivel concluir o envio ao cliente. Verifique login, cliente e destino."
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
    if status == "ERRO":
        detalhe_tecnico.update(_capturar_artefatos_erro(contexto, etapa, driver))

    registrar_onvio_log(
        acao=f"onvio_selenium:{etapa}",
        empresa_id=contexto["empresa_id"],
        parcela_id=contexto["parcela_id"],
        status=status,
        mensagem=mensagem,
        detalhe_tecnico=json.dumps(detalhe_tecnico, ensure_ascii=True),
    )


def _capturar_artefatos_erro(contexto, etapa, driver):
    if not driver:
        return {}

    artefatos = {}
    try:
        log_dir = Path(current_app.config["LOG_DIR"])
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        cnpj = _texto_arquivo_seguro(contexto["empresa_cnpj"])
        etapa_segura = _texto_arquivo_seguro(etapa)
        prefixo = f"onvio_{timestamp}_{cnpj}_{etapa_segura}"

        if current_app.config.get("ONVIO_SAVE_ERROR_SCREENSHOT", True):
            screenshot_path = log_dir / "screenshots" / f"{prefixo}.png"
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            driver.save_screenshot(str(screenshot_path))
            artefatos["screenshot_path"] = str(screenshot_path)

        if current_app.config.get("ONVIO_SAVE_ERROR_HTML", True):
            html_path = log_dir / "html" / f"{prefixo}.html"
            html_path.parent.mkdir(parents=True, exist_ok=True)
            html_path.write_text(driver.page_source[:500000], encoding="utf-8")
            artefatos["html_path"] = str(html_path)
    except Exception as exc:
        artefatos["artifact_error"] = f"{type(exc).__name__}: {exc}"

    return artefatos


def _texto_arquivo_seguro(texto):
    texto = str(texto or "")
    permitido = []
    for caractere in texto:
        if caractere.isalnum() or caractere in ("-", "_"):
            permitido.append(caractere)
        else:
            permitido.append("_")
    return "".join(permitido).strip("_")[:80] or "sem_identificador"


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
    options.add_argument("--window-size=1366,900")
    options.add_argument("--disable-dev-shm-usage")
    if sys.platform != "win32":
        options.add_argument("--no-sandbox")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])


def _abrir_documentos_cliente(driver, wait):
    driver.get(current_app.config["ONVIO_URL"])
    wait.until(lambda d: d.execute_script("return document.readyState") == "complete")
    if "onvio.com.br/staff/" in driver.current_url.lower():
        wait.until(
            lambda d: _esta_em_login(d)
            or bool(
                d.find_elements(
                    By.XPATH,
                    "//input[contains(@placeholder, 'Selecione um cliente')]"
                    "|//*[contains(normalize-space(.), 'DOCUMENTOS DO CLIENTE')]",
                )
            )
        )


def _autenticar_se_necessario(driver, wait, contexto):
    estado_login = _estado_login_onvio(driver)
    if estado_login == "autenticado":
        _registrar_etapa(
            contexto,
            etapa="sessao_ativa",
            status="INFO",
            mensagem="Sessao Onvio ja estava autenticada.",
            driver=driver,
        )
        return

    if estado_login == "validacao_adicional":
        _resolver_validacao_adicional(driver, wait, contexto)
        return

    _registrar_etapa(
        contexto,
        etapa="login",
        status="INFO",
        mensagem=f"Sessao Onvio nao autenticada. Executando login simples ({estado_login}).",
        driver=driver,
    )
    _abrir_formulario_login_se_necessario(driver, wait)

    estado_login = _estado_login_onvio(driver)
    if estado_login == "autenticado":
        return
    if estado_login == "validacao_adicional":
        _resolver_validacao_adicional(driver, wait, contexto)
        return

    email = _campo_email_login(driver)
    senha = _campo_senha_login(driver)
    if not email and not senha:
        raise OnvioAutomacaoErro(
            "Tela de login Onvio detectada, mas nenhum campo de e-mail ou senha foi encontrado."
        )

    if email:
        email.clear()
        email.send_keys(current_app.config["ONVIO_EMAIL"])

    if not senha:
        _avancar_login(driver)
        senha = wait.until(lambda d: _campo_senha_login(d) or _esta_em_mfa(d))
        if _esta_em_mfa(driver):
            _resolver_validacao_adicional(driver, wait, contexto)
            return

    senha.clear()
    senha.send_keys(current_app.config["ONVIO_PASSWORD"])
    _avancar_login(driver)
    wait.until(lambda d: _esta_em_mfa(d) or not _esta_em_login(d))
    if _esta_em_mfa(driver):
        _resolver_validacao_adicional(driver, wait, contexto)
        return

    _registrar_etapa(
        contexto,
        etapa="login",
        status="SUCESSO",
        mensagem="Login Onvio concluido.",
        driver=driver,
    )


def _abrir_formulario_login_se_necessario(driver, wait):
    if _campo_email_login(driver) or _campo_senha_login(driver):
        return

    url = driver.current_url.lower()
    if "onvio.com.br/login" in url:
        _clicar_inicio_onvio(driver, wait)

        wait.until(
            lambda d: "auth.thomsonreuters.com" in d.current_url.lower()
            or "onvio.com.br/staff/" in d.current_url.lower()
            or bool(_campo_email_login(d))
            or bool(_campo_senha_login(d))
        )


def _clicar_inicio_onvio(driver, wait):
    seletores = (
        "#trauth-continue-signin-btn",
        "#trta1-auth0-continue-signin-btn",
        "button[type='submit']",
        "button",
    )
    ultimo_erro = None
    for _ in range(2):
        for seletor in seletores:
            try:
                elementos = driver.find_elements(By.CSS_SELECTOR, seletor)
                for elemento in elementos:
                    if not elemento.is_displayed() or not elemento.is_enabled():
                        continue
                    texto = (elemento.text or "").strip().lower()
                    if seletor == "button" and "entrar" not in texto:
                        continue
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elemento)
                    try:
                        elemento.click()
                    except WebDriverException:
                        driver.execute_script("arguments[0].click();", elemento)
                    return
            except Exception as exc:
                ultimo_erro = exc

        try:
            _clicar_primeiro_texto(driver, ("Entrar", "Login", "Sign in", "Acessar"))
            return
        except Exception as exc:
            ultimo_erro = exc
            wait.until(lambda d: d.execute_script("return document.readyState") == "complete")

    raise OnvioAutomacaoErro("Botao inicial Entrar do Onvio nao foi encontrado.") from ultimo_erro


def _estado_login_onvio(driver):
    if _esta_em_mfa(driver):
        return "validacao_adicional"
    url = driver.current_url.lower()
    email = _campo_email_login(driver)
    senha = _campo_senha_login(driver)
    if "onvio.com.br/staff/" in url and not email and not senha:
        return "autenticado"
    if senha and not email:
        return "senha_salva"
    if email and senha:
        return "email_e_senha"
    if email:
        return "email_primeiro"
    if _esta_em_login(driver):
        return "login_indefinido"
    return "autenticado"


def _campo_email_login(driver):
    return _primeiro_presente(
        driver,
        (
            "input[name='username']",
            "input#username",
            "input[type='email']",
            "input[name='uid']",
            "input[name*='email' i]",
            "input[id*='email' i]",
        ),
    )


def _campo_senha_login(driver):
    return _primeiro_presente(
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


def _avancar_login(driver):
    _clicar_primeiro_texto(driver, ("Entrar", "Login", "Sign in", "Acessar", "Continuar", "Continue", "Next"))


def _resolver_validacao_adicional(driver, wait, contexto):
    _registrar_etapa(
        contexto,
        etapa="codigo_onvio",
        status="INFO",
        mensagem="Onvio solicitou codigo de verificacao. Buscando codigo no Outlook via Microsoft Graph.",
        driver=driver,
    )
    try:
        codigo = buscar_codigo_onvio()
    except OutlookGraphNaoConfigurado as exc:
        raise OnvioAutomacaoErro(str(exc)) from exc
    except OutlookGraphErro as exc:
        raise OnvioAutomacaoErro(f"Nao foi possivel obter o codigo Onvio no Outlook: {exc}") from exc

    campo_codigo = _campo_codigo_mfa(driver)
    if not campo_codigo:
        raise OnvioAutomacaoErro("Onvio solicitou codigo, mas o campo de codigo nao foi encontrado.")

    campo_codigo.clear()
    campo_codigo.send_keys(codigo)
    _avancar_login(driver)
    wait.until(lambda d: not _esta_em_mfa(d) or _estado_login_onvio(d) == "autenticado")
    if _esta_em_mfa(driver):
        raise OnvioAutomacaoErro("Codigo Onvio preenchido, mas a validacao adicional permaneceu ativa.")

    _registrar_etapa(
        contexto,
        etapa="codigo_onvio",
        status="SUCESSO",
        mensagem=f"Codigo Onvio preenchido automaticamente via Outlook Graph: ***{codigo[-3:]}.",
        driver=driver,
    )


def _campo_codigo_mfa(driver):
    return _primeiro_presente(
        driver,
        (
            "input[name*='mfa' i]",
            "input[id*='mfa' i]",
            "input[name*='code' i]",
            "input[id*='code' i]",
            "input[autocomplete='one-time-code']",
            "input[placeholder*='codigo' i]",
            "input[placeholder*='código' i]",
            "input[type='tel']",
            "input[inputmode='numeric']",
        ),
    )


def _mensagem_validacao_adicional():
    return (
        "Onvio solicitou validacao adicional de login. "
        "Conclua a autenticacao manualmente no Chrome e tente subir novamente."
    )


def _esta_em_login(driver):
    url = driver.current_url.lower()
    if "login" in url or "signin" in url or "auth" in url:
        return True
    return bool(_campo_senha_login(driver))


def _esta_em_mfa(driver):
    url = driver.current_url.lower()
    if "mfa" in url or "multi-factor" in url or "multifactor" in url:
        return True
    return bool(_campo_codigo_mfa(driver))


def _pesquisar_e_abrir_cliente(driver, wait, empresa):
    seletores_cliente = (
        "input[placeholder*='Selecione um cliente' i]",
        "input[aria-label*='Select Here' i]",
        "input[placeholder*='Cliente' i]",
    )
    wait.until(lambda d: _cliente_realmente_selecionado(d) or _primeiro_presente(d, seletores_cliente))
    if _cliente_selecionado_corresponde(driver, empresa):
        return

    identificador_onvio = empresa["nome_onvio"] or ""
    nome_empresa = empresa["nome_empresa"] or ""
    cnpj = empresa["cnpj"] or ""
    termos_busca = _termos_busca_cliente(nome_empresa, identificador_onvio, cnpj)
    alvos = [nome_empresa, identificador_onvio, cnpj]
    campo_busca = _primeiro_presente(
        driver,
        (
            "input[placeholder*='Selecione um cliente' i]",
            "input[aria-label*='Select Here' i]",
            "input[placeholder*='Pesquisar' i]",
            "input[placeholder*='Cliente' i]",
            "input[aria-label*='Pesquisar' i]",
            "input[type='search']",
            "input[type='text']",
        ),
    )
    if not campo_busca:
        raise OnvioAutomacaoErro("Campo de pesquisa de cliente nao encontrado no Onvio.")

    ultimo_erro = None
    for termo in termos_busca:
        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", campo_busca)
            campo_busca.click()
            campo_busca.send_keys(Keys.CONTROL, "a")
            campo_busca.send_keys(termo)
            opcao = wait.until(lambda d: _encontrar_opcao_cliente(d, alvos + [termo]))
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", opcao)
            try:
                opcao.click()
            except WebDriverException:
                driver.execute_script("arguments[0].click();", opcao)
            wait.until(lambda d: _cliente_selecionado_corresponde(d, empresa))
            return
        except Exception as exc:
            ultimo_erro = exc

    raise OnvioAutomacaoErro(
        "Cliente nao encontrado no Onvio: " + ", ".join(texto for texto in alvos if texto)
    ) from ultimo_erro


def _termos_busca_cliente(nome_empresa, identificador_onvio, cnpj):
    termos = []
    nome_empresa = (nome_empresa or "").strip()
    identificador_onvio = (identificador_onvio or "").strip()
    if nome_empresa:
        termos.append(nome_empresa)
        nome_sem_acentos = _remover_acentos(nome_empresa)
        if nome_sem_acentos and nome_sem_acentos not in termos:
            termos.append(nome_sem_acentos)
        primeiro_nome = nome_empresa.split(" ")[0]
        if len(primeiro_nome) >= 3 and primeiro_nome not in termos:
            termos.append(primeiro_nome)
    if nome_empresa and identificador_onvio and identificador_onvio not in nome_empresa:
        termos.append(f"{nome_empresa} ({identificador_onvio})")

    for termo in (identificador_onvio, cnpj):
        termo = (termo or "").strip()
        if termo and termo not in termos:
            termos.append(termo)
        primeiro = termo.split(" ")[0] if termo else ""
        if len(primeiro) >= 3 and primeiro not in termos:
            termos.append(primeiro)
    return termos


def _encontrar_opcao_cliente(driver, textos):
    for texto in [texto for texto in textos if texto]:
        xpath = (
            "//tr[contains(normalize-space(.), {texto})]"
            "|//li[contains(normalize-space(.), {texto})]"
            "|//a[contains(normalize-space(.), {texto})]"
            "|//td[contains(normalize-space(.), {texto})]"
        ).format(texto=_xpath_literal(texto))
        for elemento in driver.find_elements(By.XPATH, xpath):
            try:
                if not elemento.is_displayed():
                    continue
                if elemento.tag_name.lower() == "td":
                    linha = elemento.find_element(By.XPATH, "./ancestor::tr[1]")
                    if linha.is_displayed():
                        return linha
                return elemento
            except WebDriverException:
                continue
    return None


def _cliente_realmente_selecionado(driver):
    url = driver.current_url.lower()
    if "/documents/client/" in url and not url.rstrip("/").endswith("/documents/client"):
        return True
    try:
        texto = driver.find_element(By.TAG_NAME, "body").text.lower()
    except WebDriverException:
        return False
    return "por favor, selecione um cliente" not in texto and "fiscal" in texto


def _cliente_selecionado_corresponde(driver, empresa):
    nome_empresa = _normalizar_texto(empresa["nome_empresa"] or "")
    identificador_onvio = _normalizar_texto(empresa["nome_onvio"] or "")
    cnpj = (empresa["cnpj"] or "").strip()
    textos_alvo = [texto for texto in (nome_empresa, identificador_onvio, cnpj) if texto]

    for seletor in (
        "input[placeholder*='Selecione um cliente' i]",
        "input[aria-label*='Select Here' i]",
        "input[placeholder*='Cliente' i]",
    ):
        for elemento in driver.find_elements(By.CSS_SELECTOR, seletor):
            try:
                valor = _normalizar_texto(elemento.get_attribute("value") or elemento.text or "")
                if valor and any(texto in valor for texto in textos_alvo):
                    return True
            except WebDriverException:
                continue

    try:
        texto = _normalizar_texto(driver.find_element(By.TAG_NAME, "body").text)
    except WebDriverException:
        return False
    return bool(nome_empresa and nome_empresa in texto)


def _normalizar_texto(texto):
    return _remover_acentos(texto).strip().lower()


def _remover_acentos(texto):
    return "".join(
        caractere
        for caractere in unicodedata.normalize("NFKD", texto or "")
        if not unicodedata.combining(caractere)
    )


def _abrir_pasta_fiscal_parcelamentos(driver, wait):
    _abrir_pasta_documentos(driver, wait, "Fiscal", "Parcelamentos")
    _abrir_pasta_documentos(driver, wait, "Parcelamentos", "Upload")


def _abrir_pasta_documentos(driver, wait, nome_pasta, texto_esperado):
    elemento = wait.until(lambda d: _encontrar_pasta_documentos(d, nome_pasta))
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elemento)
    try:
        elemento.click()
    except WebDriverException:
        driver.execute_script("arguments[0].click();", elemento)

    try:
        wait.until(lambda d: _texto_visivel_contem(d, texto_esperado))
    except TimeoutException:
        # Em algumas grades do Onvio o primeiro clique apenas seleciona a linha.
        # O segundo clique abre a pasta.
        try:
            elemento = _encontrar_pasta_documentos(driver, nome_pasta) or elemento
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elemento)
            driver.execute_script("arguments[0].click();", elemento)
        except WebDriverException:
            pass
        wait.until(lambda d: _texto_visivel_contem(d, texto_esperado))


def _encontrar_pasta_documentos(driver, nome_pasta):
    xpath = (
        "//*[self::a or self::button or self::span or self::div]"
        f"[normalize-space(.) = { _xpath_literal(nome_pasta) }]"
    )
    candidatos = []
    for elemento in driver.find_elements(By.XPATH, xpath):
        try:
            if not elemento.is_displayed() or not elemento.is_enabled():
                continue
            rect = elemento.rect
            tag = elemento.tag_name.lower()
            prioridade_tag = 0 if tag in ("a", "button") else 1
            # Preferimos a arvore lateral quando ela estiver expandida, mas
            # aceitamos a grade principal porque ela tambem lista pastas.
            painel = 0 if rect.get("x", 9999) <= 330 else 1
            candidatos.append((painel, prioridade_tag, rect.get("x", 9999), rect.get("y", 9999), elemento))
        except WebDriverException:
            continue

    if not candidatos:
        return None
    candidatos.sort(key=lambda item: item[:4])
    return candidatos[0][4]


def _fazer_upload(driver, wait, caminho_pdf):
    _clicar_primeiro_texto(driver, ("Upload", "Enviar", "Carregar"))
    file_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='file']")))
    file_input.send_keys(str(caminho_pdf))
    wait.until(lambda d: caminho_pdf.name.lower() in d.page_source.lower())


def _gerenciar_vencimento(driver, wait, nome_arquivo):
    _aguardar_onvio_ocioso(driver, wait)
    _filtrar_documento(driver, wait, nome_arquivo)
    _selecionar_documento_por_nome(driver, wait, nome_arquivo)
    _aguardar_onvio_ocioso(driver, wait)
    _clicar_primeiro_texto(driver, ("Gerenciar", "Manage"))
    _aguardar_onvio_ocioso(driver, wait)
    _clicar_texto_aproximado(driver, wait, ("Definir data de vencimento", "Vencimento", "Due date"))

    vencimento = _ultimo_dia_mes_atual()
    _marcar_documento_no_calendario_impostos(driver)
    campo_data = _primeiro_presente(
        driver,
        (
            "input[type='date']",
            "input#dueDate",
            "input[name='dateField']",
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
        campo_data.send_keys(vencimento.strftime("%Y-%m-%d"))
    else:
        campo_data.send_keys(vencimento.strftime("%d/%m/%Y"))

    _clicar_primeiro_texto(driver, ("Salvar", "Aplicar", "Concluir", "OK"))


def _marcar_documento_no_calendario_impostos(driver):
    checkbox = _primeiro_presente(
        driver,
        (
            "input[name='taxDocument']",
            "input[type='checkbox'][name*='tax' i]",
            "input[type='checkbox']",
        ),
    )
    if not checkbox:
        raise OnvioAutomacaoErro("Checkbox do calendario de impostos nao encontrado no Onvio.")

    marcado = (checkbox.get_attribute("checked") or "").lower() in ("true", "checked")
    marcado = marcado or bool(checkbox.is_selected())
    if marcado:
        return

    try:
        checkbox.click()
    except WebDriverException:
        driver.execute_script("arguments[0].click();", checkbox)


def _filtrar_documento(driver, wait, nome_arquivo):
    campo = _primeiro_presente(
        driver,
        (
            "input[name='search']",
            "input[placeholder*='Pesquisar' i]",
            "input[aria-label*='Pesquisar' i]",
        ),
    )
    if not campo:
        return

    for termo in _termos_busca_documento(nome_arquivo):
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", campo)
        campo.click()
        _definir_valor_input(driver, campo, termo)
        try:
            wait.until(lambda d: _encontrar_linha_documento(d, nome_arquivo))
            return
        except TimeoutException:
            continue

    campo.click()
    _definir_valor_input(driver, campo, "")


def _ultimo_dia_mes_atual():
    hoje = datetime.now()
    ultimo_dia = monthrange(hoje.year, hoje.month)[1]
    return hoje.replace(day=ultimo_dia)


def _termos_busca_documento(nome_arquivo):
    nome = Path(nome_arquivo).stem
    termos = [nome_arquivo, nome]
    if " - " in nome:
        termos.append(nome.split(" - ")[0])
    if "competencia_" in nome:
        termos.append(nome.split("competencia_", 1)[1])
    return [termo for termo in termos if termo]


def _selecionar_documento_por_nome(driver, wait, nome_arquivo):
    linha = wait.until(lambda d: _encontrar_linha_documento(d, nome_arquivo))
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", linha)

    checkbox = _checkbox_na_linha(linha)
    if checkbox:
        try:
            checkbox.click()
        except WebDriverException:
            driver.execute_script("arguments[0].click();", checkbox)
        return

    _clicar_checkbox_lateral_documento(driver, linha)


def _encontrar_linha_documento(driver, nome_arquivo):
    candidatos = []
    textos = [nome_arquivo]
    if " - " in nome_arquivo:
        textos.append(nome_arquivo.split(" - ")[0])
    if "competencia_" in nome_arquivo:
        textos.append(nome_arquivo.split("competencia_", 1)[1].replace(".pdf", ""))

    for texto in [texto for texto in textos if texto]:
        xpath = (
            "//*[contains(normalize-space(.), {texto})]"
        ).format(texto=_xpath_literal(texto))
        for elemento in driver.find_elements(By.XPATH, xpath):
            try:
                if not elemento.is_displayed():
                    continue
                linha = _ancestral_linha(elemento)
                if linha and linha.is_displayed():
                    candidatos.append(linha)
            except WebDriverException:
                continue

    return candidatos[0] if candidatos else None


def _ancestral_linha(elemento):
    for xpath in (
        "./ancestor::*[@role='row'][1]",
        "./ancestor::*[contains(@class, 'wj-row')][1]",
        "./ancestor::tr[1]",
    ):
        try:
            return elemento.find_element(By.XPATH, xpath)
        except WebDriverException:
            continue
    return None


def _checkbox_na_linha(linha):
    for seletor in ("input[type='checkbox']", "[role='checkbox']"):
        elementos = linha.find_elements(By.CSS_SELECTOR, seletor)
        for elemento in elementos:
            try:
                if elemento.is_displayed() and elemento.is_enabled():
                    return elemento
            except WebDriverException:
                continue
    return None


def _clicar_checkbox_lateral_documento(driver, linha):
    celulas = []
    for elemento in linha.find_elements(By.CSS_SELECTOR, ".wj-cell, [role='gridcell'], td"):
        try:
            if not elemento.is_displayed():
                continue
            rect = elemento.rect
            if rect.get("width", 0) <= 0 or rect.get("height", 0) <= 0:
                continue
            celulas.append((rect.get("x", 0), rect.get("y", 0), rect, elemento))
        except WebDriverException:
            continue

    if not celulas:
        raise OnvioAutomacaoErro("Linha do documento encontrada, mas celulas da grade nao foram localizadas.")

    celulas.sort(key=lambda item: (item[1], item[0]))
    primeira_celula = celulas[0][2]
    x = max(1, primeira_celula["x"] - 22)
    y = primeira_celula["y"] + max(6, min(primeira_celula["height"] / 2, 18))
    _clicar_ponto_tela(driver, x, y)


def _clicar_ponto_tela(driver, x, y):
    try:
        driver.execute_cdp_cmd("Input.dispatchMouseEvent", {
            "type": "mousePressed",
            "x": x,
            "y": y,
            "button": "left",
            "clickCount": 1,
        })
        driver.execute_cdp_cmd("Input.dispatchMouseEvent", {
            "type": "mouseReleased",
            "x": x,
            "y": y,
            "button": "left",
            "clickCount": 1,
        })
        return
    except WebDriverException:
        pass

    driver.execute_script(
        """
        const x = arguments[0];
        const y = arguments[1];
        const target = document.elementFromPoint(x, y);
        if (!target) {
            throw new Error(`Nenhum elemento encontrado em ${x},${y}`);
        }
        for (const type of ['mousemove', 'mousedown', 'mouseup', 'click']) {
            target.dispatchEvent(new MouseEvent(type, {
                bubbles: true,
                cancelable: true,
                view: window,
                clientX: x,
                clientY: y
            }));
        }
        """,
        x,
        y,
    )


def _definir_valor_input(driver, elemento, valor):
    elemento.clear()
    driver.execute_script(
        """
        const input = arguments[0];
        const value = arguments[1];
        input.value = value;
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
        """,
        elemento,
        valor,
    )


def _primeiro_presente(driver, seletores):
    for seletor in seletores:
        elementos = driver.find_elements(By.CSS_SELECTOR, seletor)
        for elemento in elementos:
            try:
                if elemento.is_displayed() and elemento.is_enabled():
                    return elemento
            except WebDriverException:
                continue
    return None


def _clicar_texto_aproximado(driver, wait, textos):
    textos = [texto for texto in textos if texto]
    ultimo_erro = None
    for texto in textos:
        try:
            elemento = wait.until(
                lambda d: _encontrar_elemento_texto_clicavel(d, texto)
            )
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elemento)
            try:
                elemento.click()
            except WebDriverException:
                driver.execute_script("arguments[0].click();", elemento)
            return
        except Exception as exc:
            ultimo_erro = exc
    raise OnvioAutomacaoErro(f"Elemento nao encontrado no Onvio: {', '.join(textos)}") from ultimo_erro


def _encontrar_elemento_texto_clicavel(driver, texto):
    xpath = (
        "//*[self::a or self::button or @role='button' or self::span or self::div"
        " or self::li or self::tr or self::td]"
        f"[contains(normalize-space(.), { _xpath_literal(texto) })]"
    )
    candidatos = []
    for elemento in driver.find_elements(By.XPATH, xpath):
        try:
            if not elemento.is_displayed() or not elemento.is_enabled():
                continue
            texto_elemento = (elemento.text or "").strip()
            if not texto_elemento:
                continue
            rect = elemento.rect
            area = rect.get("width", 0) * rect.get("height", 0)
            exato = texto_elemento.lower() == texto.lower()
            tag = elemento.tag_name.lower()
            prioridade_tag = 0 if tag in ("a", "button") else 1 if tag in ("span", "td") else 2
            candidatos.append((not exato, prioridade_tag, len(texto_elemento), area, elemento))
        except WebDriverException:
            continue

    if not candidatos:
        return None
    candidatos.sort(key=lambda item: item[:4])
    return candidatos[0][4]


def _texto_visivel_contem(driver, texto):
    if not texto:
        return False
    try:
        return texto.lower() in driver.find_element(By.TAG_NAME, "body").text.lower()
    except WebDriverException:
        return False


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
                try:
                    elemento.click()
                except WebDriverException:
                    driver.execute_script("arguments[0].click();", elemento)
                return
    raise OnvioAutomacaoErro(f"Botao nao encontrado no Onvio: {', '.join(textos)}")


def _aguardar_onvio_ocioso(driver, wait):
    wait.until(
        lambda d: not any(
            elemento.is_displayed()
            for elemento in d.find_elements(
                By.CSS_SELECTOR,
                ".bento-busyloader, .bento-busyloader-inner, .loading, .spinner",
            )
        )
    )


def _xpath_literal(texto):
    if "'" not in texto:
        return f"'{texto}'"
    if '"' not in texto:
        return f'"{texto}"'
    partes = texto.split("'")
    return "concat(" + ", \"'\", ".join(f"'{parte}'" for parte in partes) + ")"
