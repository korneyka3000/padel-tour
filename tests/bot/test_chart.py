"""The chart, and the second message it has to live in.

Two things worth pinning. That the picture is a picture — the thing it replaced was a table
pretending to be one. And that the extra message stays a strict two: replaced while the
chart is up, deleted the moment the chat goes anywhere else. The bot's whole design is one
message per tournament, and this is the only exception to it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from typing import TYPE_CHECKING, Any, cast

import pytest
from PIL import Image

from conftest import make_tournament, play_round
from padel_tour.bot import chart, screens
from padel_tour.bot.screen_store import hide_chart, show_chart
from padel_tour.db import Tournament

if TYPE_CHECKING:
    from aiogram import Bot
    from sqlalchemy.ext.asyncio import AsyncSession

CHAT_ID = -100500

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


@dataclass
class PhotoBot:
    """Just the three calls the chart makes."""

    sent: list[int] = field(default_factory=list)
    edited: list[int] = field(default_factory=list)
    deleted: list[int] = field(default_factory=list)
    next_message_id: int = 5000

    async def send_photo(self, chat_id: int, photo: Any, **_: object) -> Any:  # noqa: ANN401, ARG002
        self.next_message_id += 1
        self.sent.append(self.next_message_id)
        return type("Sent", (), {"message_id": self.next_message_id})()

    async def edit_message_media(self, *, message_id: int, **_: object) -> None:
        self.edited.append(message_id)

    async def delete_message(self, *, chat_id: int, message_id: int) -> None:  # noqa: ARG002
        self.deleted.append(message_id)


# --------------------------------------------------------------------------- the picture


async def test_nothing_played_means_no_chart(session: AsyncSession) -> None:
    """A picture of nothing is worse than the round screen, which at least says who is on."""
    view = await make_tournament(session)

    assert chart.render(view) is None


async def test_a_played_round_draws_a_png(session: AsyncSession) -> None:
    view = await make_tournament(session)
    view = await play_round(session, view, 1)

    png = chart.render(view)

    assert png is not None
    assert png.startswith(PNG_MAGIC)


async def test_the_picture_is_as_tall_as_the_field(session: AsyncSession) -> None:
    """One row per place. Eight players is eight rows, and the height has to follow or the
    bottom half of the field falls off the bottom of the image."""
    view = await make_tournament(session)
    view = await play_round(session, view, 1)

    png = chart.render(view)
    assert png is not None

    image = Image.open(BytesIO(png))
    expected = chart.TOP + chart.ROW * (len(view.standings) - 1) + chart.BOTTOM
    assert image.size == (chart.WIDTH, expected)


# --------------------------------------------------------------------------- the message


async def test_the_first_chart_is_posted_and_remembered(session: AsyncSession) -> None:
    view = await make_tournament(session)
    view = await play_round(session, view, 1)
    png = chart.render(view)
    assert png is not None
    bot = PhotoBot()

    await show_chart(cast("Bot", bot), session, CHAT_ID, view.id, png, screens.chart_caption(view))

    row = await session.get(Tournament, view.id)
    assert row is not None
    assert row.chart_message_id == bot.sent[-1]


async def test_a_second_look_replaces_the_first_rather_than_posting_again(
    session: AsyncSession,
) -> None:
    """Otherwise the chat fills with charts, which is the thing this bot does not do."""
    view = await make_tournament(session)
    view = await play_round(session, view, 1)
    png = chart.render(view)
    assert png is not None
    bot = PhotoBot()
    caption = screens.chart_caption(view)

    await show_chart(cast("Bot", bot), session, CHAT_ID, view.id, png, caption)
    await show_chart(cast("Bot", bot), session, CHAT_ID, view.id, png, caption)

    assert len(bot.sent) == 1
    assert bot.edited == [bot.sent[0]]


async def test_leaving_the_chart_takes_it_down(session: AsyncSession) -> None:
    view = await make_tournament(session)
    view = await play_round(session, view, 1)
    png = chart.render(view)
    assert png is not None
    bot = PhotoBot()
    await show_chart(cast("Bot", bot), session, CHAT_ID, view.id, png, screens.chart_caption(view))

    await hide_chart(cast("Bot", bot), session, CHAT_ID, view.group_id)

    assert bot.deleted == [bot.sent[0]]
    row = await session.get(Tournament, view.id)
    assert row is not None
    assert row.chart_message_id is None


async def test_leaving_when_no_chart_is_up_does_nothing(session: AsyncSession) -> None:
    """Called before every press, so the common case is that there is nothing to do."""
    view = await make_tournament(session)
    bot = PhotoBot()

    await hide_chart(cast("Bot", bot), session, CHAT_ID, view.group_id)

    assert bot.deleted == []


@pytest.mark.parametrize("size", [4, 8])
async def test_every_field_size_renders(session: AsyncSession, size: int) -> None:
    view = await make_tournament(session, size=size)
    view = await play_round(session, view, 1)

    assert chart.render(view) is not None


def test_the_palette_wraps_rather_than_running_out() -> None:
    """A group larger than the palette is a colour repeat, not an exception. Twenty-four
    players is four more than the twelve lanes, and the twenty-fifth line has to get one."""
    assert chart._lane(len(chart.LANES)) == chart._lane(0)
    assert chart._lane(len(chart.LANES) * 2 + 3) == chart._lane(3)
