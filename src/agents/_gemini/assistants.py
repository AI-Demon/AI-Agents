"""Gemini (Google) assistants."""

from __future__ import annotations

from io import BytesIO
from time import sleep
from typing import TYPE_CHECKING, Self

from google import genai
from google.genai import types as gtypes
from google.genai.errors import ClientError as GClientError
from google.genai.errors import ServerError as GServerError

from src.core.intrfaces import KeyRatesAgentInterface
from src.core.logger import logger as log

from .tools import http_request, url_tool

if TYPE_CHECKING:
    from src.dto import FileDTO

ERROR_WORD = "ERROR"
STOP_WORD = "STOP"
FUNC_MAP = {http_request.__name__: http_request}

END_QUOTA = "429 RESOURCE_EXHAUSTED."

# Самая быстрая, но при длинной цепи вызовов начинает ошибаться.
# Может быть несколько чатов спасёт её.
# USE_MODEL = "gemini-2.5-flash-lite-preview-06-17"
USE_MODEL = "gemini-2.5-flash"
# Самая умная
# USE_MODEL = "gemini-2.5-pro"

LOAD_KEY_RATES_PROMPT = f"""
# Задача по работе с API

Тебе необходимо взаимодействовать с внешним API для загрузки данных.
Следуй инструкциям ниже для выполнения этой задачи.
Используй внешнюю функцию для доступа к серверу по адресу: %s.

Когда задача выполнена, отправь в ответе только слово {STOP_WORD}.

## Поиск документации OpenAPI:

Последовательно добавляй суффиксы к базовому URL и выполняй запрос, пока не получишь документацию openapi.json.

После успешного получения документации, изучи её,
чтобы определить доступные конечные точки (URL-адреса) для получения и загрузки данных.

## Определение допустимых атрибутов и данных:

На основе документации OpenAPI, определи полный список допустимых названий атрибутов (полей)
и типов данных, которые могут быть использованы в запросах.
Возможно, понадобятся дополнительные запросы к сервису
для определения допустимых имен (названий) данных и атрибутов.
Запомни эти названия - они понадобятся при составлении запросов.

## Чтение и обработка файла:

Когда разберёшься с документацией OpenAPI прочитай предоставленный файл.
В файле должна быть таблица с данными, разделённая на столбцы.
Каждый столбец содержит отдельные данные - загрузи их по отдельности.
Особое внимание удели дате, с которой начинается содержимое файла. Эта дата является критически важной.

Все числовые значения из файла должны быть сохранены и использованы в точно таком же формате,
как и в исходном документе, без округления или преобразования в целые числа.

## Составление JSON-запросов для загрузки данных:

Для каждого вида данных, найденного в файле, составь отдельный JSON-запрос
в соответствии с требованиями документации OpenAPI (там есть и примеры).
Если при загрузке сервер отвечает ошибкой 422, то исправь запрос.

Важно:
Названия столбцов из файла должны быть переведены на латиницу в соответствии со списком допустимых атрибутов,
полученных из документации OpenAPI или из запросов к сервису.
Использование любых других названий строго запрещено.

Поле comment в каждом запросе должно содержать заголовок из исходного файла.
Поле name должно быть уникальным для каждого вида данных.
Выбери подходящее значение для name из списка допустимых данных, определённых в первом шаге.
Названия атрибутов в запросе должны быть переведены на латиницу в соответствии со списком допустимых атрибутов.

## Отправка данных на сервер:

После составления всех валидных JSON-запросов, отправь данные на сервер,
используя соответствующие конечные точки и форматы, определённые в первом шаге.

## Проверка загруженных данных:

После успешной загрузки данных, проверь появились ли они на сервере.

## Обработка ошибок:

Если для какого-либо атрибута или для поля name не удаётся найти подходящего значения в списке допустимых атрибутов
из документации OpenAPI, НЕ СОЗДАВАЙ запрос для этого вида данных,
вместо этого, запиши сообщение об ошибке, указывающее на проблему, например:
"{ERROR_WORD}: не найдено подходящего атрибута для X".
"""


class KeyRatesAgent(KeyRatesAgentInterface):
    """Агент загружает файл в формате PDF, вытаскивает из него нужную информацию и отправляет на сервер."""

    name = "KeyRatesPDF"

    def __init__(  # noqa: D107
        self: Self,
        api_key: str,
        doc_url: str,
        doc_attrs_url: str,  # noqa: ARG002
        key_rate_doc_names_url: str,  # noqa: ARG002
    ) -> None:
        tools = gtypes.Tool(function_declarations=[url_tool])

        self._doc_url = doc_url
        self._model = genai.Client(api_key=api_key)
        self._config = gtypes.GenerateContentConfig(
            temperature=0,
            tools=[tools],
            thinking_config=gtypes.ThinkingConfig(include_thoughts=False),
        )
        self._sys_prompt = LOAD_KEY_RATES_PROMPT % self._doc_url
        return None

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
        return (
            None,
            up_file.uri,
        )

    def delete_file(self: Self, file_id: str) -> None:  # noqa: D102
        self._model.files.delete(name=file_id)
        try:
            self._model.files.get(name=file_id)
        except GClientError:
            log.info("Файл удален.")
        else:
            log.info("Файл не удален. %s", file_id)

        return None

    def process_file(self: Self, file_id: str) -> None:  # noqa: D102
        spent_tokens = 0
        contents_parts = [gtypes.Part(text=self._sys_prompt), gtypes.Part(file_data=gtypes.FileData(file_uri=file_id))]
        for step in range(1, 21):
            log.info("Step %d", step)
            try:
                response = self._model.models.generate_content(
                    model=USE_MODEL,
                    contents=contents_parts,  # type: ignore[union-attr]
                    config=self._config,
                )
            except GClientError as gce:
                if gce.args[0].startswith(END_QUOTA):
                    log.critical("Достигнут лимит токенов. Повторите запрос позже.")

                log.error(gce.args[0])
                return None
            except GServerError as gse:
                log.error(gse.args[0])
                return None

            if (
                response.candidates is None
                or not response.candidates
                or response.candidates[0].content is None
                or not response.candidates[0].content.parts
                or response.usage_metadata is None
                or response.usage_metadata.total_token_count is None
            ):
                log.error("Не удалось получить данные от: %s", USE_MODEL)
                log.info(response)
                return None

            spent_tokens += response.usage_metadata.total_token_count
            for part in response.candidates[0].content.parts:
                if part.text:
                    log.info("Got text: %s", part.text[:33])
                    if part.text.strip() == STOP_WORD:
                        log.info("Обработка файла завершена за %d шагов. Использовано токенов: %d", step, spent_tokens)
                        return None

                    if part.text.startswith(ERROR_WORD):
                        log.error(part.text)
                        return None

                contents_parts.append(part)
                if part.function_call:
                    log.info("Вызываем функцию: %s", part.function_call.name)
                    # TODO: Возможны функции не требующие аргументов? Добавить в маппинг флаг?
                    if part.function_call.name not in FUNC_MAP or part.function_call.args is None:
                        log.error("Модель не предоставила данные для вызова функции.")
                        continue

                    status, server_text = FUNC_MAP[part.function_call.name](**part.function_call.args)
                    contents_parts.append(
                        gtypes.Part(
                            function_response=gtypes.FunctionResponse(
                                name=part.function_call.name,
                                response={"status": status, "data": server_text},
                            ),
                        ),
                    )
                    log.info("%d: %s", status, server_text[:111])

                if not part.text and not part.function_call:
                    log.warning(response)
            sleep(5)
        return None
