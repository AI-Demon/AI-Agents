from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, Self

if TYPE_CHECKING:
    from src.dto import FileDTO


class BaseAgentInterface(Protocol):
    """Базовый интерфейс для агента."""  # noqa: RUF002

    name: str  # Имя агента, используется для идентификации агента в системе.

    def __init__(self: Self, api_key: str) -> None:
        """Инициализация агента.

        Args:
            api_key (str): Ключ доступа к АПИ модели.

        """
        raise NotImplementedError

    def __repr__(self: Self) -> str:  # noqa: D105
        return self.name

    def description(self: Self) -> str:
        """Описание агента."""
        return self.__doc__ if self.__doc__ else self.__class__.__name__


class KeyRatesAgentInterface(BaseAgentInterface, Protocol):  # noqa: D101
    def __init__(self: Self, api_key: str, doc_url: str, doc_attrs_url: str, key_rate_doc_names_url: str) -> None:
        """Инициализация агента.

        Args:
            api_key (str): Ключ доступа к АПИ модели.
            doc_url (str): Адрес сервиса загрузки документов.
            doc_attrs_url (str): URL для загрузки атрибутов документов.
            key_rate_doc_names_url (str): URL для загрузки названий документов.

        """
        raise NotImplementedError

    def load_file(self: Self, file_dto: FileDTO) -> tuple[str | None, str | None]:
        """Загрузить пользовательский файл в модель и вернуть его идентификатор.

        #### Args:
        - file_dto (FileDTO): Данные о пользовательском файле.

        #### Returns:
        - tuple[str | None, str | None]: Сообщение об ошибке и идентификатор файла.
        """  # noqa: RUF002
        raise NotImplementedError

    def process_file(self: Self, file_id: str) -> None:
        """Обработать пользовательский файл."""
        raise NotImplementedError
