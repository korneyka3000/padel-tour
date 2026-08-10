"""Settings, and the two things about them that are easy to get wrong.

The object is trivial. What is not trivial is *when* it reads the environment, and *whose*
environment it reads.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from padel_tour.settings import DEFAULT_SMTP_PORT, settings

if TYPE_CHECKING:
    import pytest


def test_a_fresh_checkout_needs_no_environment_at_all() -> None:
    """Defaults describe a working local run: SQLite in a file, mail to the log, no bot."""
    current = settings()

    assert current.database_url == ""
    assert current.smtp_host == ""
    assert current.bot_token == ""
    assert current.smtp_port == DEFAULT_SMTP_PORT


def test_the_environment_is_read_when_asked_not_when_imported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A module-level object would freeze whatever the shell held at import time."""
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")

    assert settings().smtp_host == "smtp.example.com"


def test_a_change_is_seen_by_the_next_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """Not cached, deliberately.

    A cached object goes stale the moment anything moves a variable underneath it, and the
    first place that happens is a test that then quietly asserts against the wrong world.
    Building one costs about 110 microseconds against one to three calls per request, so
    the cache would buy half a millisecond and cost that.
    """
    monkeypatch.setenv("SMTP_HOST", "first.example.com")
    assert settings().smtp_host == "first.example.com"

    monkeypatch.setenv("SMTP_HOST", "second.example.com")
    assert settings().smtp_host == "second.example.com"


def test_the_sender_falls_back_to_the_account(monkeypatch: pytest.MonkeyPatch) -> None:
    """Gmail rewrites a From that is not the authenticated account, so defaulting to
    anything else would mean sending mail that silently claims a different sender."""
    monkeypatch.setenv("SMTP_USER", "padel@example.com")
    monkeypatch.delenv("MAIL_FROM", raising=False)

    assert settings().sender == "padel@example.com"


def test_variables_that_are_not_ours_are_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    """Vercel and Docker hand us dozens. Rejecting them would refuse to start."""
    monkeypatch.setenv("SOME_PLATFORM_THING", "whatever")

    assert settings().database_url == ""
