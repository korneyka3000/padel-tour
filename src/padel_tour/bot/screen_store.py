"""Keeping one message per tournament up to date.

The bot never posts a running commentary. It owns a single message per tournament and
rewrites it. Over an eight-player Americano that is the difference between one pinned screen
and fifty messages with the current table buried somewhere in the middle.

The message's coordinates live on the tournament row, so a restarted bot keeps redrawing the
same message instead of starting a new conversation.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import select

from padel_tour.db import Tournament

if TYPE_CHECKING:
    import uuid

    from aiogram import Bot
    from aiogram.types import InlineKeyboardMarkup
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

#: Telegram says this when an edit would leave the message exactly as it is. Two people
#: pressing the same button is ordinary, not a failure.
_UNCHANGED = "message is not modified"
#: The message we were redrawing is gone — deleted, or too old for Telegram to edit.
_GONE = ("message to edit not found", "message can't be edited", "MESSAGE_ID_INVALID")


async def remember_screen(
    session: AsyncSession, tournament_id: uuid.UUID, chat_id: int, message_id: int
) -> None:
    """Record which message belongs to this tournament."""
    row = await session.get(Tournament, tournament_id)
    if row is not None:
        row.screen_chat_id = chat_id
        row.screen_message_id = message_id


async def screen_location(
    session: AsyncSession, tournament_id: uuid.UUID
) -> tuple[int, int] | None:
    """Where this tournament's live message is, if we have posted one."""
    row = await session.scalar(select(Tournament).where(Tournament.id == tournament_id))
    if row is None or row.screen_chat_id is None or row.screen_message_id is None:
        return None
    return row.screen_chat_id, row.screen_message_id


async def redraw(
    bot: Bot,
    chat_id: int,
    message_id: int,
    text: str,
    markup: InlineKeyboardMarkup,
) -> bool:
    """Rewrite the live message. ``False`` means it is gone and a new one is needed."""
    try:
        await bot.edit_message_text(
            text=text, chat_id=chat_id, message_id=message_id, reply_markup=markup
        )
    except TelegramBadRequest as exc:
        message = str(exc)
        if _UNCHANGED in message:
            return True
        if any(marker in message for marker in _GONE):
            logger.info("live message %s/%s is gone, will repost", chat_id, message_id)
            return False
        raise
    return True


async def show_screen(
    bot: Bot,
    session: AsyncSession,
    chat_id: int,
    rendered: tuple[str, InlineKeyboardMarkup],
    *,
    tournament_id: uuid.UUID | None = None,
    message_id: int | None = None,
) -> int:
    """Put ``text`` on screen, editing in place when there is a message to edit.

    Returns the message id now holding the screen. When a tournament is given, that id is
    stored against it so any later handler — or a later run of the bot — can find it.
    """
    text, markup = rendered
    target = message_id
    if target is None and tournament_id is not None:
        located = await screen_location(session, tournament_id)
        if located is not None and located[0] == chat_id:
            target = located[1]

    if target is not None and await redraw(bot, chat_id, target, text, markup):
        posted = target
    else:
        sent = await bot.send_message(chat_id=chat_id, text=text, reply_markup=markup)
        posted = sent.message_id

    if tournament_id is not None:
        await remember_screen(session, tournament_id, chat_id, posted)
    return posted
