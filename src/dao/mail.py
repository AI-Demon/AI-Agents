"""Обработчик почты."""

from __future__ import annotations

import contextlib
import email
import imaplib
from email.header import decode_header
from email.utils import parsedate_to_datetime
from typing import TYPE_CHECKING, Self

from src.dto import EmailDTO, FileDTO

if TYPE_CHECKING:
    import datetime as dt
    from email.message import Message

STATUS_OK = "OK"


class Mailer:
    """Обработчик почты."""

    def __init__(self: Self, host: str, port: int, username: str, password: str) -> None:
        """Инициализация обработчика почты.

        Args:
            host (str): Сервер почты.
            port (int): Порт почты.
            username (str): Логин почты.
            password (str): Пароль почты.
        """
        self._host = host
        self._port = port
        self._username = username
        self._password = password

        return None

    def read_new_messages(self: Self, from_: dt.datetime) -> list[EmailDTO]:
        """Обработка новых сообщений."""
        mail = imaplib.IMAP4_SSL(self._host, self._port)
        mail.login(self._username, self._password)
        mail.select("inbox")

        date_str = from_.strftime("%d-%b-%Y")
        status, uids = mail.search(None, f'(SINCE "{date_str}")')
        uids: list[bytes]  # type: ignore # [b'1 2 3 4']
        if status != STATUS_OK:
            return []

        email_dtos: list[EmailDTO] = []
        for uid in map(bytes.decode, uids[0].split()):
            email_dto = self.get_email(mail, from_, uid)
            if email_dto:
                email_dtos.append(email_dto)

        mail.logout()
        return email_dtos

    def get_email(self: Self, mail: imaplib.IMAP4, from_: dt.datetime, uid: str) -> EmailDTO | None:
        """Получение сообщения."""
        status, msg_data = mail.fetch(uid, "(RFC822)")  # type: ignore
        msg_data: list[tuple[bytes, ...]]  # type: ignore
        if status != STATUS_OK:
            return None

        text = ""
        attachments: list[FileDTO] = []
        msg = email.message_from_bytes(msg_data[0][1])  # type: ignore
        sender = self._get_sender(msg)
        subject = self._get_subject(msg)
        recived_at = self._get_date(msg, from_)
        if not msg.is_multipart():
            with contextlib.suppress(Exception):
                text = msg.get_payload(decode=True).decode("utf-8", errors="ignore")  # type: ignore
        else:
            for part in msg.walk():
                content_disposition = part.get("Content-Disposition", "")
                content_type = part.get_content_type()
                if content_type == "text/plain" and "attachment" not in content_disposition:
                    try:
                        charset = part.get_content_charset() or "utf-8"
                        text += part.get_payload(decode=True).decode(charset, errors="ignore")  # type: ignore
                    except Exception:  # noqa: S110
                        pass
                elif "attachment" in content_disposition:
                    file_dto = self._get_file(part, content_type)
                    if file_dto:
                        attachments.append(file_dto)

        if recived_at < from_:
            return None

        return EmailDTO(
            sender=sender,
            subject=subject,
            recived_at=recived_at,
            text=text.strip(),
            attachments=attachments,
        )

    def _get_sender(self: Self, msg: Message) -> str:
        return msg.get("From", "")

    def _get_subject(self: Self, msg: Message) -> str:
        decoded_header = decode_header(msg.get("Subject", ""))[0]
        subject: bytes | str = decoded_header[0]
        encoding: str | None = decoded_header[1]
        if isinstance(subject, bytes):
            return subject.decode(encoding or "utf-8", errors="ignore")

        return subject  # type: ignore

    def _get_date(self: Self, msg: Message, default: dt.datetime) -> dt.datetime:
        _dt = parsedate_to_datetime(msg.get("Date", ""))
        return _dt or default

    def _get_file(self: Self, part: Message, content_type: str) -> FileDTO | None:
        filename = part.get_filename()
        if not filename:
            return None

        decoded_parts = decode_header(filename)
        decoded_filename = ""
        for p, enc in decoded_parts:
            if isinstance(p, bytes):
                decoded_filename += p.decode(enc or "utf-8", errors="ignore")
            else:
                decoded_filename += p

        content = part.get_payload(decode=True)
        return FileDTO(type_=content_type.split("/")[-1], name=decoded_filename, content=content)  # type: ignore
