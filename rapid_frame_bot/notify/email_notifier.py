from __future__ import annotations
import asyncio
import smtplib
from loguru import logger
from config import Config


class EmailNotifier:
    def __init__(self, config: Config) -> None:
        self.cfg = config

    def _build_message(self, subject: str, body: str) -> str:
        full_subject = f"[急速框] {subject}"
        msg = (
            f"Subject: {full_subject}\n"
            f"From: {self.cfg.email_sender}\n"
            f"To: {self.cfg.email_recipient}\n"
            f"Content-Type: text/plain; charset=\"utf-8\"\n"
            f"\n"
            f"{body}\n"
        )
        return msg

    def _send_blocking(self, raw: str) -> None:
        with smtplib.SMTP(self.cfg.email_smtp_host,
                          self.cfg.email_smtp_port, timeout=15) as smtp:
            smtp.starttls()
            smtp.login(self.cfg.email_sender, self.cfg.email_password)
            smtp.sendmail(self.cfg.email_sender,
                          [self.cfg.email_recipient], raw)

    async def send(self, subject: str, body: str) -> None:
        raw = self._build_message(subject, body)
        try:
            await asyncio.to_thread(self._send_blocking, raw)
            logger.info(f"Email sent: {subject}")
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Email failed ({subject}): {exc}")
