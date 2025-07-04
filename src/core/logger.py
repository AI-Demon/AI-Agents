from __future__ import annotations

import logging
from typing import Literal

logger = logging.getLogger()


def init_logger(name: str, level: Literal["DEBUG", "INFO"]) -> logging.Logger:
    """Инициализация логгера."""
    logger.name = name
    logger.setLevel(level)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(name)s:%(module)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger
