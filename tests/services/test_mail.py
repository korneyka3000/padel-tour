"""Which mailer we get, and that the test one behaves."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from padel_tour.services.mail import (
    InMemoryMailer,
    LoggingMailer,
    SmtpMailer,
    mailer_from_env,
)

if TYPE_CHECKING:
    import pytest


async def test_the_test_mailer_remembers() -> None:
    mailer = InMemoryMailer()
    await mailer.send("a@b.c", "Вход", "ссылка")

    assert len(mailer.sent) == 1
    assert mailer.sent[0].to == "a@b.c"
    assert mailer.last_to("a@b.c") is not None
    assert mailer.last_to("nobody@b.c") is None


def test_without_smtp_configured_we_log(monkeypatch: pytest.MonkeyPatch) -> None:
    """A fresh checkout must not be blocked on having a mail account."""
    monkeypatch.delenv("SMTP_HOST", raising=False)
    assert isinstance(mailer_from_env(), LoggingMailer)


def test_with_smtp_configured_we_send(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USER", "bot@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("MAIL_FROM", "Padel <bot@example.com>")

    mailer = mailer_from_env()
    assert isinstance(mailer, SmtpMailer)
    assert mailer.config.port == 587
    assert mailer.config.sender == "Padel <bot@example.com>"


def test_the_sender_falls_back_to_the_login(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USER", "bot@example.com")
    monkeypatch.delenv("MAIL_FROM", raising=False)

    mailer = mailer_from_env()
    assert isinstance(mailer, SmtpMailer)
    assert mailer.config.sender == "bot@example.com"


async def test_the_fallback_mailer_is_loud_enough_to_be_seen(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Info goes nowhere under uvicorn's defaults, and a silent sign-in link is a dead end."""
    with caplog.at_level(logging.WARNING):
        await LoggingMailer().send("anya@example.com", "Вход", "https://example.com?token=abc")

    assert "anya@example.com" in caplog.text
    assert "token=abc" in caplog.text
