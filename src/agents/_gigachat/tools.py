from __future__ import annotations

from typing import Annotated

import httpx
from pydantic import BaseModel, Field

from src.core.logger import logger as log


class HttpResult(BaseModel):
    """Результат выполнения `httpx.request`."""

    status: int = Field(description="Статус выполнения запроса")
    text: str | None = Field(description="Тело ответа")


def http_request(
    method: Annotated[str, Field(description="Метод HTTP-запроса")],
    url: Annotated[str, Field(description="URL-адрес сервера, куда нужно отправить HTTP-запрос")],
    data: Annotated[dict | None, Field(description="Данные для отправки в теле запроса")] = None,
) -> HttpResult:
    """Выполнить HTTP-запрос."""
    log.debug(f"! {method} {url} {data}")
    response = httpx.request(method, url, json=data)

    return HttpResult(status=response.status_code, text=response.text)


def http_request_s(
    method: str,
    url: str,
    # data: dict | None = None,  Ломается препроцессор GigaChat
    data: str | None = None,
) -> tuple[int, str]:
    """Выполнить HTTP-запрос.

    Args:
        method (str): Метод HTTP-запроса.
        url (str): URL-адрес сервера, куда нужно отправить HTTP-запрос.
        data (dict | None, optional): Данные для отправки в теле запроса.


    Returns:
        tuple[int, str]: Статус выполнения запроса и тело ответа
    """
    log.debug(f"! {method} {url} {data}")
    response = httpx.request(method, url, json=data)

    return response.status_code, response.text
