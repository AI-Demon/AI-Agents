from __future__ import annotations

import logging
from typing import Literal

logger = logging.getLogger("tmp_name")


def init_logger(name: str, level: Literal["DEBUG", "INFO"]) -> logging.Logger:
    """Инициализация логгера."""
    logger.name = name
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(name)s:%(module)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    logger.name = name
    for log in logging.Logger.manager.loggerDict.values():
        if not isinstance(log, logging.Logger):
            continue

        if log.name != name:
            log.setLevel(logging.WARNING)
        else:
            log.setLevel(level)
    return logger
