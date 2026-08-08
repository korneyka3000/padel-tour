"""One database session per update.

Handlers take a ``session`` argument and never manage the transaction themselves. An update
either succeeds and commits, or fails and rolls back whole — there is no state where half a
score got written.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from aiogram import BaseMiddleware

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from aiogram.types import TelegramObject
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)


class SessionMiddleware(BaseMiddleware):
    """Give each handler a session, and commit it if the handler returns cleanly."""

    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory

    # aiogram's middleware contract is `Any` in and `Any` out — a handler may return
    # anything, and the framework passes it along untouched. Narrowing it here would be a
    # lie about what actually arrives.
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:  # noqa: ANN401
        async with self._factory() as session:
            data["session"] = session
            try:
                result = await handler(event, data)
            except BaseException:
                await session.rollback()
                raise
            await session.commit()
            return result
