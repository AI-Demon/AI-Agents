"""Gemini (Google) assistants."""

from __future__ import annotations

from functools import cache
from http import HTTPMethod, HTTPStatus
from io import BytesIO
from typing import TYPE_CHECKING, Self

from google import genai
from google.genai import types as gtypes

from src.core.intrfaces import KeyRatesAgentInterface
from src.core.logger import logger as log

from .tools import http_request, url_tool

if TYPE_CHECKING:
    from src.dto import FileDTO

# Самая быстрая
# USE_MODEL = "gemini-2.5-flash-lite-preview-06-17"
USE_MODEL = "gemini-2.5-flash"
# Самая умная
# USE_MODEL = "gemini-2.5-pro"

LOAD_KEY_RATES_PROMPT = """
Документация  OpenAPI: %s
Адрес сервера - %s
Список допустимых атрибутов: %s
Список допустимых видов данных: %s

Прочитай файл. Обрати внимание - с какой даты его содержимое (это очень важная дата).
Все числа должны быть представлены в ответе ровно в том же формате (десятичные дроби, если они есть)
без округления или преобразования в целые числа, как в исходном документе.
В соответствии с документацией OpenAPI составь запросы для загрузки данных на сервер.
При создании джсонов название столбцов переведи на латинницу в соответствии со списком атрибутов.
Никакие другие названия использовать нельзя.
Для каждого вида данных - отдельный запрос.
В `comment` вставь заголовок из файла.
`name` должно быть уникально для каждого вида данных поищи подходящее значение в списке допустимых данных.

Если для атрибутов или `name` нет подходящего значения - не создавай запрос, а напиши ошибку.

Отправь данные на сервер.
"""


class KeyRatesAgent(KeyRatesAgentInterface):
    """Агент загружает файл в формате PDF, вытаскивает из него нужную информацию и отправляет на сервер."""

    name = "KeyRatesPDF"

    def __init__(  # noqa: D107
        self: Self,
        api_key: str,
        doc_url: str,
        doc_attrs_url: str,
        key_rate_doc_names_url: str,
    ) -> None:
        tools = gtypes.Tool(function_declarations=[url_tool])

        self._doc_url = doc_url
        self._doc_attrs_url = doc_attrs_url
        self._key_rate_doc_names_url = key_rate_doc_names_url
        self._model = genai.Client(api_key=api_key)
        self._config = gtypes.GenerateContentConfig(temperature=0, tools=[tools])
        self._sys_prompt = LOAD_KEY_RATES_PROMPT % (self._api_doc(), self._doc_url, self._attrs(), self._doc_names())
        return None

    @cache  # noqa: B019
    def _api_doc(self: Self) -> str | None:
        status, api_doc = http_request(HTTPMethod.GET, f"{self._doc_url}/openapi.json")
        return None if status != HTTPStatus.OK or not api_doc else api_doc

    @cache  # noqa: B019
    def _attrs(self: Self) -> str | None:
        status, attrs = http_request(HTTPMethod.GET, self._doc_attrs_url)
        return None if status != HTTPStatus.OK or not attrs else attrs

    @cache  # noqa: B019
    def _doc_names(self: Self) -> str | None:
        status, doc_names = http_request(HTTPMethod.GET, self._key_rate_doc_names_url)
        return None if status != HTTPStatus.OK or not doc_names else doc_names

    def load_file(self: Self, file_dto: FileDTO) -> tuple[str | None, str | None]:  # noqa: D102
        try:
            up_file = self._model.files.upload(
                file=BytesIO(file_dto.content),
                config=gtypes.UploadFileConfig(mime_type=f"application/{file_dto.type_}"),
            )
        except Exception as e:
            log.info("%s: %s", e.__class__.__name__, e.args)
            return "Не удалось загрузить файл. Проверьте формат и попробуйте снова.", None

        log.info("Файл загружен. ID: %s", up_file.uri)
        return None, up_file.uri

    def process_file(self: Self, file_id: str) -> None:  # noqa: D102
        if not self._api_doc() or not self._attrs() or not self._doc_names():
            log.error("Не удалось получить данные от %s", self._doc_url)
            return None

        contents_parts = [
            gtypes.Part(text=self._sys_prompt),
            gtypes.Part(file_data=gtypes.FileData(file_uri=file_id, mime_type="application/pdf")),
        ]
        response = self._model.models.generate_content(model=USE_MODEL, contents=contents_parts, config=self._config)  # type: ignore[union-attr]
        if (
            response.candidates is None
            or not response.candidates
            or response.candidates[0].content is None
            or not response.candidates[0].content.parts
        ):
            log.error("Не удалось получить данные от: %s", USE_MODEL)
            log.debug(response)
            # pprint(response)
            return None

        for part in response.candidates[0].content.parts:
            if part.function_call:
                # pprint(part.function_call.args)
                if part.function_call.name != "http_request" or part.function_call.args is None:
                    log.error("Модель не предоставила данные для вызова функции.")
                    continue

                status, text = http_request(**part.function_call.args)
                if status != HTTPStatus.CREATED:
                    log.warning(text)
                else:
                    log.info(text)
            else:
                log.error("Модель не предоставила данные для вызова функции.")
                # pprint(response)

        return None
