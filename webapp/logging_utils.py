from __future__ import annotations

import logging

from .config import settings

LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"


def configure_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if getattr(logger, "_d3_configured", False):
        return logger

    logger.setLevel(getattr(logging, settings.log_level, logging.INFO))
    logger.propagate = False

    formatter = logging.Formatter(LOG_FORMAT)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    if settings.log_file is not None:
        settings.log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(settings.log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    setattr(logger, "_d3_configured", True)
    return logger


LOGGER = configure_logger("conciliador.web")
