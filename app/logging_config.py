import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


LOGGERS = {
    "psn": "psn.log",
    "serpro": "serpro.log",
    "onvio": "onvio.log",
}

SENSITIVE_WORDS = (
    "secret",
    "senha",
    "password",
    "token",
    "jwt",
    "cert",
    "consumer",
)


def setup_logging(app):
    log_dir = Path(app.config["LOG_DIR"])
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "screenshots").mkdir(parents=True, exist_ok=True)
    (log_dir / "html").mkdir(parents=True, exist_ok=True)

    level = getattr(logging, str(app.config["LOG_LEVEL"]).upper(), logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    )

    for logger_name, filename in LOGGERS.items():
        logger = logging.getLogger(logger_name)
        logger.setLevel(level)
        logger.propagate = False

        if _has_managed_handler(logger):
            continue

        handler = RotatingFileHandler(
            log_dir / filename,
            maxBytes=app.config["LOG_MAX_BYTES"],
            backupCount=app.config["LOG_BACKUP_COUNT"],
            encoding="utf-8",
        )
        handler.setFormatter(formatter)
        handler._psn_managed_handler = True
        logger.addHandler(handler)


def log_event(logger_name, level, message, **fields):
    logger = logging.getLogger(logger_name)
    logger.log(level, _format_message(message, fields))


def safe_json(value, limit=4000):
    try:
        text = json.dumps(_redact(value), ensure_ascii=False, default=str)
    except TypeError:
        text = str(value)
    return text[:limit]


def _has_managed_handler(logger):
    return any(
        getattr(handler, "_psn_managed_handler", False)
        for handler in logger.handlers
    )


def _format_message(message, fields):
    clean = {
        key: _redact(value)
        for key, value in fields.items()
        if value not in (None, "")
    }
    if not clean:
        return message
    return f"{message} | {safe_json(clean)}"


def _redact(value):
    if isinstance(value, dict):
        return {
            key: "***"
            if _is_sensitive_key(key)
            else _redact(inner_value)
            for key, inner_value in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    return value


def _is_sensitive_key(key):
    key_lower = str(key).lower()
    return any(word in key_lower for word in SENSITIVE_WORDS)
