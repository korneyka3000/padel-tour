"""The signature on a Mini App launch.

``initData`` reaches us through the browser, which means it reaches us through the user.
Unverified, ``user={"id":1}`` is a sentence anybody can type. These tests are about the one
function standing between that sentence and somebody else's account.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import TYPE_CHECKING
from urllib.parse import urlencode

import pytest

from padel_tour.db import PROVIDER_TELEGRAM
from padel_tour.db.models import utc_now
from padel_tour.services import account_for_identity, account_for_launch
from padel_tour.services.errors import InvalidTokenError, TokenExpiredError
from padel_tour.services.telegram_auth import MAX_AGE, verify

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

TOKEN = "123456:test-bot-token"  # noqa: S105 - a fixture, not a credential
OTHER_BOT = "999:not-our-bot"
ANYA = 4242


def launch(*, token: str = TOKEN, age_seconds: int = 0, **overrides: str) -> str:
    """A launch string signed the way Telegram signs one."""
    fields = {
        "auth_date": str(int(utc_now().timestamp()) - age_seconds),
        "query_id": "AAA",
        "user": json.dumps({"id": ANYA, "first_name": "Аня"}, ensure_ascii=False),
        **overrides,
    }
    check = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def test_a_launch_signed_with_our_token_is_accepted() -> None:
    assert verify(launch(), TOKEN)["query_id"] == "AAA"


def test_a_launch_signed_with_somebody_elses_token_is_refused() -> None:
    """The whole point. Without this check the endpoint is "tell me who you are"."""
    with pytest.raises(InvalidTokenError):
        verify(launch(token=OTHER_BOT), TOKEN)


def test_an_unsigned_launch_is_refused() -> None:
    with pytest.raises(InvalidTokenError):
        verify(urlencode({"user": '{"id": 1}'}), TOKEN)


def test_a_tampered_field_invalidates_the_signature() -> None:
    """Editing the user id after signing is the attack this is here to stop."""
    signed = dict(pair.split("=", 1) for pair in launch().split("&"))
    signed["user"] = '{"id": 1}'

    with pytest.raises(InvalidTokenError):
        verify(urlencode(signed), TOKEN)


def test_a_stale_launch_is_refused() -> None:
    """Telegram never expires initData, so we do: a copy lifted out of somebody's browser
    would otherwise be a permanent key to their account."""
    with pytest.raises(TokenExpiredError):
        verify(launch(age_seconds=int(MAX_AGE.total_seconds()) + 60), TOKEN)


def test_a_deployment_with_no_bot_trusts_nothing() -> None:
    """An empty token would otherwise be a key everybody knows."""
    with pytest.raises(InvalidTokenError):
        verify(launch(), "")


async def test_a_launch_signs_in_as_the_telegram_account(session: AsyncSession) -> None:
    """The same identity the bot uses, so a claimed player comes with the person."""
    account = await account_for_launch(session, launch(), TOKEN)

    known = await account_for_identity(session, PROVIDER_TELEGRAM, str(ANYA))
    assert known is not None
    assert account.id == known.id


async def test_a_launch_describing_nobody_is_refused(session: AsyncSession) -> None:
    with pytest.raises(InvalidTokenError):
        await account_for_launch(session, launch(user="not json"), TOKEN)
