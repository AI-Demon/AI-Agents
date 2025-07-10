from __future__ import annotations

from http import HTTPMethod  # noqa: TC003
from typing import Annotated

import httpx
from pydantic import Field

from src.core.logger import logger as log

from .utils import func_to_gemi


def http_request(
    method: Annotated[HTTPMethod, Field(description="Метод HTTP-запроса")],
    url: Annotated[str, Field(description="URL-адрес сервера, куда нужно отправить HTTP-запрос")],
    data: Annotated[dict | None, Field(description="Данные для отправки в теле запроса")] = None,
) -> tuple[int, str]:
    """Выполнить HTTP-запрос.

    Returns:
        tuple[int, str]: Статус выполнения запроса и тело ответа.
    """
    log.info("%s %s", method, url)
    try:
        response = httpx.request(method, url, json=data)
    except Exception as e:
        return 0, str(e)

    return response.status_code, response.text


url_tool = func_to_gemi(http_request)
