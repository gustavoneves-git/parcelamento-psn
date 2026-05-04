import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _path_from_env(name, default=""):
    value = os.environ.get(name, default)
    if not value:
        return ""

    path = Path(value)
    if path.is_absolute():
        return str(path)
    return str(BASE_DIR / path)


class Config:
    SECRET_KEY = os.environ.get("PSN_SECRET_KEY", "psn-local-dev")
    DATABASE_PATH = BASE_DIR / "data" / "psn.db"
    PARCELAS_PATH = BASE_DIR / "storage" / "parcelas"
    ONVIO_SAIDA_PADRAO = BASE_DIR / "storage" / "onvio_saida"

    SERPRO_CONSUMER_KEY = os.environ.get("SERPRO_CONSUMER_KEY", "")
    SERPRO_CONSUMER_SECRET = os.environ.get("SERPRO_CONSUMER_SECRET", "")
    SERPRO_CERT_PATH = _path_from_env("SERPRO_CERT_PATH")
    SERPRO_CERT_PASSWORD = os.environ.get("SERPRO_CERT_PASSWORD", "")
    SERPRO_TOKEN_URL = os.environ.get("SERPRO_TOKEN_URL", "")
    SERPRO_API_URL = os.environ.get("SERPRO_API_URL", "")
    SERPRO_TIMEOUT_SECONDS = int(os.environ.get("SERPRO_TIMEOUT_SECONDS", "40"))
    SERPRO_USE_MTLS = os.environ.get("SERPRO_USE_MTLS", "0") == "1"
    SERPRO_JWT_HEADER_NAME = os.environ.get("SERPRO_JWT_HEADER_NAME", "jwt_token")
    SERPRO_AUTH_ROLE_TYPE = os.environ.get("SERPRO_AUTH_ROLE_TYPE", "TERCEIROS")
    SERPRO_CONTRATANTE_CNPJ = os.environ.get("SERPRO_CONTRATANTE_CNPJ", "")
    SERPRO_AUTOR_PEDIDO_CPF = os.environ.get("SERPRO_AUTOR_PEDIDO_CPF", "")
