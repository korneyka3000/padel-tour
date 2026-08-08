"""Sending email.

Plain SMTP rather than any provider's API, so the provider is a setting rather than a
decision in code — Gmail today, anything else tomorrow, by changing environment variables.

Three implementations: one that sends, one that writes to the log so a fresh checkout needs
no mail service at all, and one that remembers, so tests never open a socket and never fail
because a provider is having a bad day.
"""

from __future__ import annotations

import logging
import os
import smtplib
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Protocol, runtime_checkable

from asyncer import asyncify

logger = logging.getLogger(__name__)

DEFAULT_SMTP_PORT = 587


@runtime_checkable
class Mailer(Protocol):
    """Anything that can deliver a message."""

    async def send(self, to: str, subject: str, body: str) -> None: ...


@dataclass(frozen=True, slots=True)
class Sent:
    to: str
    subject: str
    body: str


@dataclass(slots=True)
class InMemoryMailer:
    """Remembers instead of sending. For tests."""

    sent: list[Sent] = field(default_factory=list)

    async def send(self, to: str, subject: str, body: str) -> None:
        self.sent.append(Sent(to, subject, body))

    def last_to(self, address: str) -> Sent | None:
        for message in reversed(self.sent):
            if message.to == address:
                return message
        return None


@dataclass(slots=True)
class LoggingMailer:
    """Writes the message to the log.

    What a fresh checkout gets. Local development should never be blocked on having a mail
    account, and a sign-in link in the terminal is perfectly usable.
    """

    async def send(self, to: str, subject: str, body: str) -> None:
        logger.info("mail to %s — %s\n%s", to, subject, body)


@dataclass(frozen=True, slots=True)
class SmtpConfig:
    host: str
    port: int
    user: str
    password: str
    sender: str


@dataclass(slots=True)
class SmtpMailer:
    """Sends over SMTP with STARTTLS."""

    config: SmtpConfig

    async def send(self, to: str, subject: str, body: str) -> None:
        # smtplib blocks, and this runs inside an async handler. On a platform that serves
        # several requests from one instance, blocking the loop stalls all of them, not just
        # the one waiting on the mail server.
        await asyncify(self._send_blocking)(to=to, subject=subject, body=body)

    def _send_blocking(self, to: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = self.config.sender
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)

        with smtplib.SMTP(self.config.host, self.config.port, timeout=20) as smtp:
            smtp.starttls()
            smtp.login(self.config.user, self.config.password)
            smtp.send_message(message)


def mailer_from_env() -> Mailer:
    """The mailer this process should use.

    No SMTP host configured means development, and development gets the log.
    """
    host = os.environ.get("SMTP_HOST", "").strip()
    if not host:
        return LoggingMailer()

    return SmtpMailer(
        SmtpConfig(
            host=host,
            port=int(os.environ.get("SMTP_PORT", DEFAULT_SMTP_PORT)),
            user=os.environ.get("SMTP_USER", ""),
            password=os.environ.get("SMTP_PASSWORD", ""),
            sender=os.environ.get("MAIL_FROM", os.environ.get("SMTP_USER", "")),
        )
    )
