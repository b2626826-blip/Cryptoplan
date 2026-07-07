from unittest.mock import patch, MagicMock
import pytest
from config import Config
from notify.email_notifier import EmailNotifier


def _cfg():
    return Config(
        testnet=True, log_level="INFO", log_file="logs/bot.log",
        email_smtp_host="smtp.test", email_smtp_port=587,
        email_sender="a@b.c", email_password="pw", email_recipient="d@e.f",
    )


def test_build_message_contains_subject_and_recipient():
    n = EmailNotifier(_cfg())
    msg = n._build_message("進場成交", "BTCUSDT @ 98000")
    assert "進場成交" in msg
    assert "d@e.f" in msg
    assert "BTCUSDT @ 98000" in msg


@pytest.mark.asyncio
async def test_send_calls_smtp():
    n = EmailNotifier(_cfg())
    with patch("notify.email_notifier.smtplib.SMTP") as smtp_cls:
        smtp = MagicMock()
        smtp_cls.return_value.__enter__.return_value = smtp
        await n.send("主旨", "內文")
        smtp.starttls.assert_called_once()
        smtp.login.assert_called_once_with("a@b.c", "pw")
        smtp.sendmail.assert_called_once()


@pytest.mark.asyncio
async def test_send_swallows_errors():
    n = EmailNotifier(_cfg())
    with patch("notify.email_notifier.smtplib.SMTP", side_effect=OSError("boom")):
        # 不應拋出
        await n.send("主旨", "內文")
