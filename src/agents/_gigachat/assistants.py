"""Тоже не работает, как и соседний модуль."""

from __future__ import annotations

import json
from functools import cache
from http import HTTPMethod, HTTPStatus
from pathlib import Path
from pprint import pprint
from typing import TYPE_CHECKING, Self

from gigachat.exceptions import ResponseError
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_gigachat.chat_models import GigaChat
from langchain_gigachat.tools.giga_tool import giga_tool
from langgraph.prebuilt import create_react_agent

from src.core.intrfaces import KeyRatesAgentInterface
from src.core.logger import logger as log

from .tools import http_request, http_request_s
from .utils import pdf_to_dict

if TYPE_CHECKING:
    from langchain_core.messages import BaseMessage

    from src.dto import FileDTO

# Дешёвая, но не читает файлы
USE_MODEL = "GigaChat"
# Дорогая, но всё равно не работает как надо
# USE_MODEL = "GigaChat-2-Max"

LOAD_KEY_RATES_PROMPT = """
Документация  OpenAPI: %s
Адрес сервера - %s
Список допустимых атрибутов: %s
Список допустимых видов данных: %s

Прочитай данные.
Все числа должны быть представлены в ответе ровно в том же формате (десятичные дроби, если они есть)
без округления или преобразования в целые числа, как и исходных данных.
В соответствии с документацией OpenAPI составь запросы для загрузки данных на сервер.
При создании джсонов название столбцов переведи на латинницу в соответствии со списком атрибутов.
Никакие другие названия использовать нельзя.
Для каждого вида данных - отдельный запрос.
В `comment` вставь заголовок из исходных данных.
`name` должно быть уникально для каждого вида данных поищи подходящее значение в списке допустимых данных.

Если для атрибутов или `name` нет подходящего значения - не создавай запрос, а напиши ошибку.

Отправь данные на сервер.
"""

http_tool = giga_tool(http_request_s)


class KeyRatesAgent(KeyRatesAgentInterface):
    """Агент загружает файл в формате PDF и вытаскивает из него нужную информацию."""

    name = "KeyRatesPDF"

    def __init__(  # noqa: D107
        self: Self,
        api_key: str,
        doc_url: str,
        doc_attrs_url: str,
        key_rate_doc_names_url: str,
    ) -> None:
        self._doc_url = doc_url
        self._doc_attrs_url = doc_attrs_url
        self._key_rate_doc_names_url = key_rate_doc_names_url
        self._sys_prompt = LOAD_KEY_RATES_PROMPT % (self._api_doc(), self._doc_url, self._attrs(), self._doc_names())
        self._model = GigaChat(
            credentials=api_key,
            scope="GIGACHAT_API_PERS",
            model=USE_MODEL,
            verify_ssl_certs=False,
            # temperature=0.1
        )

        tools = [http_tool]
        bind_model = self._model.bind_functions(tools)
        self._agent = create_react_agent(bind_model, tools)
        return None

    @cache  # noqa: B019
    def _api_doc(self: Self) -> str | None:
        result = http_request(HTTPMethod.GET, f"{self._doc_url}/openapi.json")
        return None if result.status != HTTPStatus.OK or not result.text else result.text

    @cache  # noqa: B019
    def _attrs(self: Self) -> str | None:
        result = http_request(HTTPMethod.GET, self._doc_attrs_url)
        return None if result.status != HTTPStatus.OK or not result.text else result.text

    @cache  # noqa: B019
    def _doc_names(self: Self) -> str | None:
        result = http_request(HTTPMethod.GET, self._key_rate_doc_names_url)
        return None if result.status != HTTPStatus.OK or not result.text else result.text

        return None

    def load_file(self: Self, file_dto: FileDTO) -> tuple[str | None, str | None]:  # noqa: D102
        if USE_MODEL == "GigaChat":
            with open(file_dto.name, "wb") as f:  # noqa: PTH123
                f.write(file_dto.content)
            return None, file_dto.name

        try:
            up_file = self._model.upload_file(file=(file_dto.name, file_dto.content, f"application/{file_dto.type_}"))
        except ResponseError as re:
            details = json.loads(re.args[2]) if len(re.args) > 2 else {}  # noqa: PLR2004
            log.error(details)
            return "Некорректный формат файла", None
        except Exception as e:
            log.info("%s: %s", e.__class__.__name__, e.args)
            return "Не удалось загрузить файл. Проверьте формат и попробуйте снова.", None

        log.info(f"Файл загружен. ID: {up_file.id_}")
        return None, up_file.id_

    def process_file(self: Self, file_id: str) -> None:  # noqa: D102
        messages: list[BaseMessage] = [
            SystemMessage(
                content="Твоя задача разбирать входные данные из следующих запросов и формировать json`ы. "
                "Никаких дополнений не делай. В ответах должны быть только json`ы.",
            ),
        ]

        response = self._agent.invoke({"messages": messages})
        messages = response["messages"]
        log.info(messages[-1].content)
        if USE_MODEL == "GigaChat":
            file_data = pdf_to_dict(file_id)
            Path(file_id).unlink()
            messages.append(HumanMessage(content=self._sys_prompt + json.dumps(file_data)))
        else:
            messages.append(HumanMessage(content=self._sys_prompt, attachments=[file_id]))

        try:
            response = self._agent.invoke({"messages": messages})
            pprint(response["messages"][-1].content)  # noqa: T203
        except ResponseError as re:
            pprint(json.loads(re.args[2])["message"])  # noqa: T203

        return None
