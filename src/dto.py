from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    import datetime as dt


@dataclass
class FileDTO:
    """Data Transfer Object for WebSocket file operations."""

    type_: str  # Тип файла
    name: str  # Имя файла
    content: bytes  # Содержимое файла

    def _init__(self: Self, type_: str, name: str, content: bytes) -> None:
        if type_ == "pdf" and not isinstance(content, bytes):
            msg = f"content must be bytes but {content.__class__} was given."
            raise TypeError(msg)

        self.type_ = type_
        self.name = name
        self.content = content


@dataclass
class EmailDTO:
    """Data Transfer Object for email operations."""

    sender: str  # Ящик отправителя
    subject: str  # Тема письма
    recived_at: dt.datetime  # Дата и время получения письма
    text: str  # Текст письма
    attachments: list[FileDTO]  # Прикреплённые файлы
