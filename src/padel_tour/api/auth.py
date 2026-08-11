"""Signing in over HTTP: the endpoints that get somebody into a session, and out of one.

Reading a session back is in :mod:`~padel_tour.api.deps`, next to the cookie itself, because
every route needs that and only these four need this.

There is no password anywhere. A link in an inbox — or a signature from Telegram — is the
whole of the proof, which is why every rule about that link (one use, fifteen minutes, one
send a minute) is enforced in the service layer rather than here.

What a session *is*, is a row. Not a JWT, and not on the way to being one: a stateless token
saves a database lookup this application never gets to skip, since every endpoint below
reads the database anyway, and charges for it in the one thing that matters here — the
ability to end a session that has gone somewhere it should not.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from padel_tour.db import Account
from padel_tour.services import (
    account_for_launch,
    close_session,
    groups_for_account,
    open_session,
    redeem_magic_link,
    request_magic_link,
)
from padel_tour.services.accounts import SESSION_TTL
from padel_tour.services.mail import Mailer, mailer_from_env
from padel_tour.settings import base_url, settings

from .deps import (
    API_PREFIX,
    SECURE_SESSION_COOKIE,
    SESSION_COOKIE,
    RequiredAccount,
    Session,
    read_session_cookie,
    secure_cookies,
    session_cookie_name,
)
from .schemas import Accepted, EnterRequest, LaunchRequest, MagicLinkRequest, Me

router = APIRouter(prefix=f"{API_PREFIX}/auth", tags=["auth"])

#: How long the cookie lasts, matching the absolute deadline on the session row behind it.
#:
#: Only the outer limit. The row also dies after :data:`~padel_tour.services.accounts.
#: SESSION_IDLE_TTL` of silence, which a cookie cannot express — so a browser may well keep
#: sending one the server has already stopped honouring. That is the right way round.
SESSION_MAX_AGE = int(SESSION_TTL.total_seconds())

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


# ----------------------------------------------------------------------------------- wire


def _hand_over(response: Response, token: str) -> None:
    """Attach a session to the response.

    One function rather than the same eight arguments at every place somebody can sign in.
    They were copied twice already, and a flag that is right in two of three places is worse
    than no flag at all.
    """
    response.set_cookie(
        session_cookie_name(),
        token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=secure_cookies(),
        samesite="lax",
        path="/",
    )


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
    _hand_over(response, await open_session(session, account))
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
    _hand_over(response, await open_session(session, account))
    return await _me(session, account)


@router.post("/sign-out", status_code=status.HTTP_204_NO_CONTENT)
async def sign_out(request: Request, session: Session, response: Response) -> None:
    """Close this session. Asking twice is not an error — the outcome is the one wanted.

    Deletes the row first: clearing the cookie only ends the session on this browser, and a
    token that survives in a log or a proxy is a token that still works. Then clears both
    cookie names, because signing out has to work for a session issued under the old one.
    """
    token = read_session_cookie(request)
    if token:
        await close_session(session, token)
    for name in (SECURE_SESSION_COOKIE, SESSION_COOKIE):
        response.delete_cookie(name, path="/")


@router.get("/me")
async def me(session: Session, actor: RequiredAccount) -> Me:
    """Who is signed in, and which groups they can see."""
    return await _me(session, actor)


async def _me(session: Session, account: Account) -> Me:
    return Me(
        id=str(account.id),
        display_name=account.display_name,
        groups=await groups_for_account(session, account),
    )


__all__ = ["router"]
