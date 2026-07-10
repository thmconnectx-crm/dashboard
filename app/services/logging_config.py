import logging
from logging.handlers import RotatingFileHandler

from app.config import DATA_DIR


def configure_logging() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("paid_traffic_dashboard")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if any(isinstance(handler, RotatingFileHandler) for handler in logger.handlers):
        return
    handler = RotatingFileHandler(DATA_DIR / "app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)


def get_logger() -> logging.Logger:
    configure_logging()
    return logging.getLogger("paid_traffic_dashboard")
