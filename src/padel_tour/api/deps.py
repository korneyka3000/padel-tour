"""Shared plumbing: the database engine, request sessions, and who is making the request.

These three sit together because everything else in the package depends on them and they
depend on nothing in it. Putting the "who is this" dependency beside the route module that
signs people in would make the two import each other.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from padel_tour.db import Account, create_engine, create_session_factory, database_url
from padel_tour.services import account_for_session
from padel_tour.services.errors import NotSignedInError
from padel_tour.services.permissions import ANONYMOUS, Anonymous
from padel_tour.settings import base_url

logger = logging.getLogger(__name__)

#: Everything the API serves lives under this prefix. In production it is also what tells
#: the deployment to route a request to the function rather than to the web app.
API_PREFIX = "/api"

#: The session cookie. HttpOnly so script cannot read it, SameSite=Lax rather than Strict
#: because arriving from a link in an email must still carry it.
SESSION_COOKIE = "pt_session"

#: The same cookie where TLS makes the hardened name legal.
#:
#: ``__Host-`` is not decoration: browsers refuse to store a cookie under this prefix unless
#: it is Secure, host-only, and path ``/``. That last pair is the useful part — no sibling
#: host and no subdomain can write it, so nothing can plant a session on somebody. Today the
#: deployment has no subdomains and the risk is theoretical; the day it gets a custom domain
#: it stops being, and this is not a change anyone would remember to make then.
SECURE_SESSION_COOKIE = f"__Host-{SESSION_COOKIE}"


def secure_cookies() -> bool:
    """Off only where there is no TLS to require: a developer's machine."""
    return base_url().startswith("https://")


def session_cookie_name() -> str:
    """What to write. The prefixed name needs Secure, so plain ``http`` cannot use it."""
    return SECURE_SESSION_COOKIE if secure_cookies() else SESSION_COOKIE


def read_session_cookie(request: Request) -> str | None:
    """What to read: the hardened name first, the plain one after.

    Both, because they coexist twice over — local development never uses the prefix, and
    every session issued before it existed is still in a browser under the old name. Reading
    both is what makes that a rename rather than a forced sign-out for everyone.
    """
    return request.cookies.get(SECURE_SESSION_COOKIE) or request.cookies.get(SESSION_COOKIE)


@lru_cache(maxsize=1)
def _engine_and_factory() -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """One engine per process, not per request.

    Serverless reuses warm instances, so a pool that lives for a single request is just a
    slow way of having no pool at all.
    """
    engine = create_engine(database_url())
    return engine, create_session_factory(engine)


def session_factory() -> async_sessionmaker[AsyncSession]:
    return _engine_and_factory()[1]


async def dispose_engine() -> None:
    """Close the pool on shutdown. Also lets tests start from a clean engine."""
    engine, _ = _engine_and_factory()
    await engine.dispose()
    _engine_and_factory.cache_clear()


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """A session per request, committed if the request succeeded.

    One transaction per request rather than a commit inside each endpoint: a handler that
    writes twice must not be able to leave half of it behind, and a handler that raises
    must leave none of it. Reads commit an empty transaction, which costs nothing.

    A test can override the factory by putting one on ``app.state``.
    """
    factory: async_sessionmaker[AsyncSession] = (
        getattr(request.app.state, "session_factory", None) or session_factory()
    )
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        else:
            await session.commit()


Session = Annotated[AsyncSession, Depends(get_session)]


async def current_account(request: Request, session: Session) -> Account | Anonymous:
    """Who is making this request.

    Never ``None``: to the service layer ``None`` means *system*, the trusted caller behind
    the CLI and the migrations. A request that arrives with no cookie is a stranger, and
    saying so with :data:`ANONYMOUS` is what keeps the two from being the same thing.

    Answering "nobody" rather than refusing is deliberate — a tournament page is readable by
    anyone holding its link, so most endpoints want to know who is asking without insisting
    on an answer.
    """
    token = read_session_cookie(request)
    if not token:
        return ANONYMOUS
    return await account_for_session(session, token) or ANONYMOUS


CurrentAccount = Annotated[Account | Anonymous, Depends(current_account)]


async def require_account(actor: CurrentAccount) -> Account:
    """The account behind this request, or a refusal.

    Raises the service layer's error rather than an ``HTTPException`` so that every refusal
    in this API looks the same on the wire. An ``HTTPException`` here would answer 401 with
    a bare ``detail`` and no code, and a page trying to translate it would have exactly one
    message it could not — the one it shows most often.
    """
    if isinstance(actor, Anonymous):
        raise NotSignedInError("sign in first")
    return actor


RequiredAccount = Annotated[Account, Depends(require_account)]
