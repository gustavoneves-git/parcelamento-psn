import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


class Config:
    SECRET_KEY = os.environ.get("PSN_SECRET_KEY", "psn-local-dev")
    DATABASE_PATH = BASE_DIR / "data" / "psn.db"
    PARCELAS_PATH = BASE_DIR / "storage" / "parcelas"
    ONVIO_SAIDA_PADRAO = BASE_DIR / "storage" / "onvio_saida"

    SERPRO_CLIENT_ID = os.environ.get("SERPRO_CLIENT_ID", "")
    SERPRO_CLIENT_SECRET = os.environ.get("SERPRO_CLIENT_SECRET", "")
    SERPRO_CERT_PATH = os.environ.get("SERPRO_CERT_PATH", "")
