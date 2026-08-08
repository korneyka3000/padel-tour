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

from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from padel_tour.db import Account, create_engine, create_session_factory, database_url
from padel_tour.services import account_for_session
from padel_tour.services.permissions import ANONYMOUS, Anonymous

logger = logging.getLogger(__name__)

#: Everything the API serves lives under this prefix. In production it is also what tells
#: the deployment to route a request to the function rather than to the web app.
API_PREFIX = "/api"

#: The session cookie. HttpOnly so script cannot read it, SameSite=Lax rather than Strict
#: because arriving from a link in an email must still carry it.
SESSION_COOKIE = "pt_session"


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


async def current_account(
    session: Session,
    pt_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> Account | Anonymous:
    """Who is making this request.

    Never ``None``: to the service layer ``None`` means *system*, the trusted caller behind
    the CLI and the migrations. A request that arrives with no cookie is a stranger, and
    saying so with :data:`ANONYMOUS` is what keeps the two from being the same thing.

    Answering "nobody" rather than refusing is deliberate — a tournament page is readable by
    anyone holding its link, so most endpoints want to know who is asking without insisting
    on an answer.
    """
    if not pt_session:
        return ANONYMOUS
    return await account_for_session(session, pt_session) or ANONYMOUS


CurrentAccount = Annotated[Account | Anonymous, Depends(current_account)]


async def require_account(actor: CurrentAccount) -> Account:
    if isinstance(actor, Anonymous):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Нужно войти")
    return actor


RequiredAccount = Annotated[Account, Depends(require_account)]
