# Несмотря на то, что API GigaChat проверяет функцию и подтверждает, что её описание корректно,
# при передаче функции в чат возвращается ошбка 422 из препроцессинга модели.
# Без передачи функции, всё равно не формируется json, как указано в промте.

from __future__ import annotations

import json
from functools import cache
from http import HTTPMethod, HTTPStatus
from pathlib import Path
from pprint import pprint
from typing import TYPE_CHECKING, Self

import httpx
from gigachat import GigaChat
from gigachat.api.utils import build_headers
from gigachat.assistants import AssistantsSyncClient
from gigachat.exceptions import ResponseError
from gigachat.models import Chat, Messages, MessagesRole

from src.core.intrfaces import KeyRatesAgentInterface
from src.core.logger import logger as log

from .tools import http_request
from .utils import func_to_giga, pdf_to_dict

if TYPE_CHECKING:
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

http_tool = func_to_giga(http_request)


class KeyRatesAgent(KeyRatesAgentInterface):
    """Агент загружает файл в формате PDF и вытаскивает из него нужную информацию."""

    name = "KeyRatesPDF"
    _func_validate_url = "https://gigachat.devices.sberbank.ru/api/v1/functions/validate"

    def __init__(  # noqa: D107
        self: Self,
        api_key: str,
        doc_url: str,
        doc_attrs_url: str,
        key_rate_doc_names_url: str,
    ) -> None:
        self._model = GigaChat(
            credentials=api_key,
            scope="GIGACHAT_API_PERS",
            model=USE_MODEL,
            verify_ssl_certs=False,
        )
        self._doc_url = doc_url
        self._doc_attrs_url = doc_attrs_url
        self._key_rate_doc_names_url = key_rate_doc_names_url
        self._tools = [http_tool]
        self._sys_prompt = LOAD_KEY_RATES_PROMPT % (self._api_doc(), self._doc_url, self._attrs(), self._doc_names())
        self._assistant = AssistantsSyncClient(self._model)
        if not self.check_tools():
            raise KeyboardInterrupt("Не удалось загрузить инструменты")
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

    def check_tools(self: Self) -> bool:
        """Проверка инструментов через GigaChat-API."""
        self._model._update_token()  # noqa: SLF001
        headers = build_headers(self._model.token)
        headers["Content-Type"] = "application/json"
        for tool in self._tools:
            response = httpx.post(
                self._func_validate_url,
                headers=headers,
                json=tool.dict(exclude_none=True, by_alias=True),
                verify=False,  # noqa: S501
                timeout=10,
            )
            if response.status_code != HTTPStatus.OK:
                return False

            data = response.json()
            if "errors" in data:
                log.critical(data["errors"])
                return False

            if "warnings" in data:
                log.warning(data["warnings"])
        return True

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
        messages = [
            Messages(
                role=MessagesRole.SYSTEM,
                content="Твоя задача разбирать входные данные из следующих запросов и формировать json`ы. "
                "Никаких дополнений не делай. В ответах должны быть только json`ы.",
            ),
        ]
        response = self._model.chat(Chat(messages=messages))
        messages.append(response.choices[0].message)
        pprint(response.choices[0].message.content)  # noqa: T203
        file_data = pdf_to_dict(file_id)
        Path(file_id).unlink()
        messages.append(
            Messages(
                role=MessagesRole.USER,
                content=self._sys_prompt,
                data_for_context=[Messages(role=MessagesRole.USER, content=json.dumps(file_data))],
            ),
        )
        payload = Chat(messages=messages, functions=self._tools)
        for _ in range(3):
            response = self._model.chat(payload)
            pprint(response.choices[0].message.content)  # noqa: T203
            print(response.choices[0].message.function_call)  # noqa: T201
            if response.choices[0].message.function_call:
                function_call = response.choices[0].message.function_call
                print(f"Function to call: {function_call.name}")  # noqa: T201
                print(f"Arguments: {function_call.arguments}")  # noqa: T201
                return

            prompt = "Не предоставлены функция и аргументы. Попробуй снова."
            payload.messages.append(response.choices[0].message)
            payload.messages.append(Messages(role=MessagesRole.USER, content=prompt))

        log.error("Не удалось получить данные от модели.")
        return None
