"""Signing in over HTTP.

Two things live here: the dependency that answers *who is this request*, and the four
endpoints that get someone into that state. Both belong together — the cookie is the only
thing connecting them, and it is defined once.

There is no password anywhere. A link in an inbox is the whole of the proof, which is why
every rule about that link — one use, fifteen minutes, one send a minute — is enforced in
the service layer rather than here.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Request, Response, status
from pydantic import BaseModel, EmailStr

from padel_tour.db import Account
from padel_tour.services import (
    account_for_launch,
    close_session,
    groups_for_account,
    open_session,
    redeem_magic_link,
    request_magic_link,
)
from padel_tour.services.mail import Mailer, mailer_from_env
from padel_tour.settings import base_url, settings

from .deps import API_PREFIX, SESSION_COOKIE, RequiredAccount, Session
from .schemas import Group

router = APIRouter(prefix=f"{API_PREFIX}/auth", tags=["auth"])

#: How long the cookie lasts, matching the session row behind it.
SESSION_MAX_AGE = 30 * 24 * 60 * 60

#: The page a sign-in link lands on.
ENTER_PATH = "/auth/enter"


def link_base() -> str:
    """Where the link in the email points.

    Read from configuration rather than from the request. A caller-supplied base would make
    this an open redirect that mails sign-in tokens to whoever asked for them.
    """
    return f"{base_url()}{ENTER_PATH}"


def mailer_for(request: Request) -> Mailer:
    """The mailer this app should use. Tests put their own on ``app.state``."""
    configured: Mailer | None = getattr(request.app.state, "mailer", None)
    return configured or mailer_from_env()


def secure_cookies() -> bool:
    """Off only where there is no TLS to require: a developer's machine."""
    return base_url().startswith("https://")


# ----------------------------------------------------------------------------------- wire


class MagicLinkRequest(BaseModel):
    email: EmailStr


class LaunchRequest(BaseModel):
    """The opaque string Telegram hands a Mini App. Never trusted before it is verified."""

    init_data: str


class EnterRequest(BaseModel):
    token: str


class Accepted(BaseModel):
    """Deliberately says nothing about whether the address is known."""

    detail: str = "Если такой адрес есть, письмо отправлено"


class Me(BaseModel):
    id: str
    display_name: str | None
    groups: list[Group]


# ------------------------------------------------------------------------------ endpoints


@router.post("/magic-link", status_code=status.HTTP_202_ACCEPTED)
async def send_magic_link(
    body: MagicLinkRequest,
    session: Session,
    mailer: Annotated[Mailer, Depends(mailer_for)],
) -> Accepted:
    """Ask for a sign-in link.

    Answers the same whether or not the address is known. Otherwise the form is a way to
    find out who has an account here.
    """
    await request_magic_link(session, body.email, mailer=mailer, link_base=link_base())
    return Accepted()


@router.post("/enter")
async def enter(body: EnterRequest, session: Session, response: Response) -> Me:
    """Exchange a link for a session."""
    account = await redeem_magic_link(session, body.token)
    token = await open_session(session, account)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=secure_cookies(),
        samesite="lax",
        path="/",
    )
    return await _me(session, account)


@router.post("/telegram")
async def enter_from_telegram(body: LaunchRequest, session: Session, response: Response) -> Me:
    """Sign in from inside a Telegram Mini App.

    No password, no email, no mail server: Telegram has already established who this is and
    signs the claim with a key derived from the bot token. Verifying that signature is the
    whole of the authentication — see :mod:`padel_tour.services.telegram_auth`.

    The identity is the one the bot uses, so somebody who claimed a player in a chat is the
    same person here rather than a second account with none of their history.
    """
    account = await account_for_launch(session, body.init_data, settings().bot_token)
    token = await open_session(session, account)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=secure_cookies(),
        samesite="lax",
        path="/",
    )
    return await _me(session, account)


@router.post("/sign-out", status_code=status.HTTP_204_NO_CONTENT)
async def sign_out(
    session: Session,
    response: Response,
    pt_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> None:
    """Close this session. Asking twice is not an error — the outcome is the one wanted."""
    if pt_session:
        await close_session(session, pt_session)
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me")
async def me(session: Session, actor: RequiredAccount) -> Me:
    """Who is signed in, and which groups they can see."""
    return await _me(session, actor)


async def _me(session: Session, account: Account) -> Me:
    return Me(
        id=str(account.id),
        display_name=account.display_name,
        groups=[Group.of(view) for view in await groups_for_account(session, account)],
    )


__all__ = ["router"]
