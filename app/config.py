import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Config:
    SECRET_KEY = os.environ.get("PSN_SECRET_KEY", "psn-local-dev")
    DATABASE_PATH = BASE_DIR / "data" / "psn.db"
    PARCELAS_PATH = BASE_DIR / "storage" / "parcelas"
    ONVIO_SAIDA_PADRAO = BASE_DIR / "storage" / "onvio_saida"

    SERPRO_CONSUMER_KEY = os.environ.get("SERPRO_CONSUMER_KEY", "")
    SERPRO_CONSUMER_SECRET = os.environ.get("SERPRO_CONSUMER_SECRET", "")
    SERPRO_CERT_PATH = os.environ.get("SERPRO_CERT_PATH", "")
    SERPRO_CERT_PASSWORD = os.environ.get("SERPRO_CERT_PASSWORD", "")
