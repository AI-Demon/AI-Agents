from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

APP_DIR = Path(__file__).parent
BASE_DIR = APP_DIR.parent
ENV_FILE = BASE_DIR / ".env"


@dataclass
class Config:
    """Configuration class."""

    GEMINI_KEY: str
    GIGACHAT_KEY: str
    APP_NAME: str
    LOG_LEVEL: Literal["DEBUG", "INFO"]
    MAIL_HOST: str
    MAIL_PORT: int
    MAIL_BOX: str
    MAIL_PASSWORD: str

    URL_KEY_RATES: str
    URL_KEY_RATES_ATTRS: str
    URL_KEY_RATES_NAMES: str


def get_config() -> Config:
    """Load configuration from environment file (.env) if it exists, else from system environment.

    Returns:
        Config: Configuration object.
    """
    if ENV_FILE.exists():
        load_dotenv(ENV_FILE, override=True)
    else:
        load_dotenv()

    return Config(
        APP_NAME="AIAgents",
        GEMINI_KEY=os.environ["GEMINI_KEY"],
        GIGACHAT_KEY=os.environ["GIGACHAT_KEY"],
        MAIL_BOX=os.environ["MAIL_BOX"],
        MAIL_HOST=os.environ["MAIL_HOST"],
        MAIL_PASSWORD=os.environ["MAIL_PASSWORD"],
        MAIL_PORT=int(os.environ["MAIL_PORT"]),
        LOG_LEVEL=os.getenv("LOG_LEVEL", "INFO"),  # type: ignore
        URL_KEY_RATES=os.getenv("URL_KEY_RATES", "http://127.0.0.1:23232").strip("/"),
        URL_KEY_RATES_ATTRS=os.getenv("URL_KEY_RATES_ATTRS", "http://127.0.0.1:23232/api/v1/attrs/all").strip("/"),
        URL_KEY_RATES_NAMES=os.getenv("URL_KEY_RATES_NAMES", "http://127.0.0.1:23232/api/v1/docs/known-names").strip(
            "/",
        ),
    )


config = get_config()
