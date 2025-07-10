from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from time import sleep

sys.path.insert(0, str(str(Path(__file__).parent.parent)))

from typing import TYPE_CHECKING

from src.agents import GCKeyRatesAgent, GCKeyRatesAgentClean, GeminiKeyRatesAgent
from src.config import config
from src.core.logger import init_logger
from src.dao.mail import Mailer

if TYPE_CHECKING:
    from src.core.intrfaces import KeyRatesAgentInterface

loggger = init_logger(config.APP_NAME, config.LOG_LEVEL)


def main(mode: str) -> None:  # noqa: D103, PLR0912
    agent: KeyRatesAgentInterface
    if mode == "SL":
        agent = GCKeyRatesAgent(
            config.GIGACHAT_KEY,
            config.URL_KEY_RATES,
            config.URL_KEY_RATES_ATTRS,
            config.URL_KEY_RATES_NAMES,
        )
    elif mode == "G":
        agent = GeminiKeyRatesAgent(
            config.GEMINI_KEY,
            config.URL_KEY_RATES,
            config.URL_KEY_RATES_ATTRS,
            config.URL_KEY_RATES_NAMES,
        )
    elif mode == "S":
        agent = GCKeyRatesAgentClean(
            config.GIGACHAT_KEY,
            config.URL_KEY_RATES,
            config.URL_KEY_RATES_ATTRS,
            config.URL_KEY_RATES_NAMES,
        )
    else:
        raise ValueError("Unknown mode")

    start_time = dt.datetime.now(tz=dt.UTC) - dt.timedelta(days=12)
    m = Mailer(host=config.MAIL_HOST, port=config.MAIL_PORT, username=config.MAIL_BOX, password=config.MAIL_PASSWORD)
    while True:
        try:
            emails = m.read_new_messages(start_time)
            if not emails:
                loggger.info("No new messages")
            else:
                start_time = emails[-1].recived_at + dt.timedelta(seconds=1)
                loggger.info("Found %d new messages", len(emails))
                for email in emails:
                    loggger.info("Processing email: %s", email.subject)
                    if email.attachments:
                        for attachment in email.attachments:
                            if attachment.type_ == "pdf":
                                err, file_id = agent.load_file(attachment)
                                if file_id:
                                    agent.process_file(file_id)
                                    agent.delete_file(file_id)
                    sleep(30)
            sleep(60)
        except KeyboardInterrupt:
            break
        except Exception as e:
            loggger.error(e.__class__, exc_info=True)


if __name__ == "__main__":
    try:
        mode = ""
        while mode not in ["G", "SL", "S"]:
            mode = input("Select mode: G (Gemini), SL (Gigachat + LC), S (Gigachat)\n>>> ").upper()

        main(mode)

    except KeyboardInterrupt:
        pass
