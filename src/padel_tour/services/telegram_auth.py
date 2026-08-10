"""Trusting what a Telegram Mini App says about who is looking at it.

A Mini App is our own web page opened inside Telegram. Telegram hands it an ``initData``
string describing the user, signed with a key derived from the bot token — so the page can
prove who it belongs to without a password, an email, or a mail server.

The signature is the whole thing. ``initData`` arrives through the browser, which means it
arrives through the user, which means an unverified one is a claim rather than a fact:
anybody can type ``user={"id":1}`` into a query string. Everything below exists to turn the
claim into a fact.

Scheme, from Telegram's documentation:

1. drop ``hash`` from the fields
2. sort what is left by key and join as ``key=value`` separated by newlines
3. HMAC-SHA256 that string with a secret key, which is itself
   ``HMAC-SHA256(bot token, "WebAppData")``
4. compare, in constant time, with the ``hash`` that came in
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import timedelta
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qsl

from padel_tour.db import PROVIDER_TELEGRAM
from padel_tour.db.models import utc_now

from .accounts import ensure_identity
from .errors import InvalidTokenError, TokenExpiredError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from padel_tour.db import Account

#: Telegram's constant, not ours.
_SECRET_SALT = b"WebAppData"

#: How old a launch may be before it is refused.
#:
#: ``initData`` is valid until somebody rotates the bot token, which is to say indefinitely.
#: A copy lifted out of one person's browser would otherwise be a permanent key to their
#: account, so it expires here even though Telegram does not expire it.
MAX_AGE = timedelta(hours=24)


def _data_check_string(fields: dict[str, str]) -> str:
    return "\n".join(f"{key}={fields[key]}" for key in sorted(fields) if key != "hash")


def verify(init_data: str, bot_token: str) -> dict[str, Any]:
    """The fields of a launch we have proved came from Telegram.

    Raises rather than returning ``None``: every caller of this turns a failure into a
    refusal, and an ``if`` that somebody forgets to write is the one bug this module cannot
    afford.
    """
    if not bot_token:
        raise InvalidTokenError("this deployment has no bot configured")

    fields = dict(parse_qsl(init_data, keep_blank_values=True))
    given = fields.get("hash", "")
    if not given:
        raise InvalidTokenError("this launch carries no signature")

    secret = hmac.new(_SECRET_SALT, bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, _data_check_string(fields).encode(), hashlib.sha256).hexdigest()
    # Constant time: a comparison that returns early leaks how much of a guess was right.
    if not hmac.compare_digest(expected, given):
        raise InvalidTokenError("this launch is not signed by Telegram")

    issued = int(fields.get("auth_date", "0"))
    if issued <= 0 or utc_now().timestamp() - issued > MAX_AGE.total_seconds():
        raise TokenExpiredError("this launch is too old — reopen the app")

    return fields


def _user(fields: dict[str, Any]) -> dict[str, Any]:
    try:
        parsed = json.loads(fields.get("user", "{}"))
    except json.JSONDecodeError as exc:
        raise InvalidTokenError("this launch describes no user") from exc
    if not isinstance(parsed, dict) or not parsed.get("id"):
        raise InvalidTokenError("this launch describes no user")
    return parsed


async def account_for_launch(session: AsyncSession, init_data: str, bot_token: str) -> Account:
    """The account behind a Mini App launch, minted on first sight.

    The same identity the bot uses, so somebody who has claimed a player in a chat is the
    same person on the web — rather than a second account with none of their history.
    """
    person = _user(verify(init_data, bot_token))
    display = " ".join(part for part in (person.get("first_name"), person.get("last_name")) if part)
    return await ensure_identity(
        session, PROVIDER_TELEGRAM, str(person["id"]), display_name=display or None
    )


__all__ = ["MAX_AGE", "account_for_launch", "verify"]
