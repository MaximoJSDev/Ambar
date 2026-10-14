"""Configuración de logs compartida por el cliente y el servidor SIGE."""
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_file_logging(logger_name: str, file_name: str) -> logging.Logger:
    """Configura un archivo rotativo en SIGE_LOG_DIR o en ~/.ambar/logs."""
    log_dir = Path(os.getenv("SIGE_LOG_DIR", Path.home() / ".ambar" / "logs")).expanduser()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = (log_dir / file_name).resolve()

    logger = logging.getLogger(logger_name)
    if not any(
        isinstance(handler, RotatingFileHandler)
        and Path(handler.baseFilename) == log_path
        for handler in logger.handlers
    ):
        handler = RotatingFileHandler(
            log_path,
            maxBytes=5_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s"
        ))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger
