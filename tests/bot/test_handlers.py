"""Handlers, driven through a fake bot.

The point of these is the one thing screen tests cannot show: that pressing buttons rewrites
a single message instead of posting new ones, and that the state behind it actually moves.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

import pytest

from conftest import NAMES
from padel_tour.bot import handlers, screens
from padel_tour.bot.callbacks import Action, Callback, Screen, plain, points, show, toggle, winner
from padel_tour.db import PROVIDER_TELEGRAM, Tournament
from padel_tour.services import (
    active_tournament,
    add_player,
    create_group,
    link_group,
    list_players,
)

if TYPE_CHECKING:
    import uuid

    from aiogram import Bot
    from aiogram.types import InlineKeyboardMarkup
    from sqlalchemy.ext.asyncio import AsyncSession

CHAT_ID = -100500
ORGANISER = 4242
BYSTANDER = 777


@dataclass(frozen=True)
class Posted:
    """A message the bot would have sent or rewritten."""

    chat_id: int
    text: str
    markup: InlineKeyboardMarkup | None
    message_id: int | None = None

    @property
    def buttons(self) -> list[str]:
        """Button labels — half of what a screen says lives here, not in the text."""
        if self.markup is None:
            return []
        return [button.text for row in self.markup.inline_keyboard for button in row]


@dataclass(frozen=True)
class FakeMessage:
    message_id: int


@dataclass
class FakeBot:
    """Records what the bot would have said, and hands back plausible message ids."""

    sent: list[Posted] = field(default_factory=list)
    edited: list[Posted] = field(default_factory=list)
    next_message_id: int = 1000

    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: InlineKeyboardMarkup | None = None,
        **_: object,
    ) -> FakeMessage:
        self.sent.append(Posted(chat_id, text, reply_markup))
        self.next_message_id += 1
        return FakeMessage(self.next_message_id)

    async def edit_message_text(
        self,
        text: str,
        chat_id: int,
        message_id: int,
        reply_markup: InlineKeyboardMarkup | None = None,
        **_: object,
    ) -> None:
        self.edited.append(Posted(chat_id, text, reply_markup, message_id))


@dataclass
class Answer:
    text: str | None
    alert: bool


@dataclass
class FakeChat:
    id: int
    title: str


@dataclass
class FakeQueryMessage:
    chat: FakeChat
    message_id: int


@dataclass
class FakeUser:
    id: int
    full_name: str


@dataclass
class FakeQuery:
    """Just enough of a CallbackQuery for the handler to work with."""

    data: str
    message: FakeQueryMessage
    from_user: FakeUser
    answers: list[Answer] = field(default_factory=list)

    async def answer(self, text: str | None = None, *, show_alert: bool = False) -> None:
        self.answers.append(Answer(text, show_alert))


def make_query(data: str, *, message_id: int = 1001, user_id: int = ORGANISER) -> FakeQuery:
    return FakeQuery(
        data=data,
        message=FakeQueryMessage(FakeChat(CHAT_ID, "Вторничный падел"), message_id),
        from_user=FakeUser(user_id, "Организатор"),
    )


async def press(
    session: AsyncSession, bot: FakeBot, data: str, *, user_id: int = ORGANISER
) -> FakeQuery:
    """Push a button the way aiogram would, bypassing its Message type check."""
    query = make_query(data, user_id=user_id)
    parsed = Callback.parse(data)
    assert parsed is not None

    chat_id = CHAT_ID
    group_id = await handlers._group_for(session, chat_id, "Вторничный падел")
    actor = await handlers._account_for(session, user_id)
    try:
        rendered, tournament_id, note = await handlers._dispatch(
            session, parsed, chat_id, group_id, actor
        )
    except Exception as exc:
        await query.answer(str(exc), show_alert=True)
        return query

    await query.answer(note or None)
    if rendered is not None:
        await handlers._paint(
            # FakeBot is a stand-in: it implements the two calls the painter makes and
            # nothing else, which is the point of using one.
            cast("Bot", bot),
            session,
            chat_id,
            rendered,
            tournament_id=tournament_id,
            message_id=query.message.message_id,
        )
    return query


@pytest.fixture(autouse=True)
def _clean_drafts() -> None:
    """Drafts are module-level state; one test must not leak into the next."""
    handlers.drafts.clear(CHAT_ID)
    handlers._pending_score.clear()


@pytest.fixture
def bot() -> FakeBot:
    return FakeBot()


async def seeded_group(session: AsyncSession) -> uuid.UUID:
    group = await create_group(session, "Вторничный падел")
    await link_group(session, group.id, PROVIDER_TELEGRAM, str(CHAT_ID))
    for name in NAMES:
        await add_player(session, group.id, name)
    return group.id


async def start_from_buttons(
    session: AsyncSession, bot: FakeBot, *, user_id: int = ORGANISER
) -> uuid.UUID:
    """Walk the real path: roster → tick everyone → setup → draw."""
    group_id = await seeded_group(session)
    await press(session, bot, show(Screen.ROSTER), user_id=user_id)
    for player in await list_players(session, group_id):
        await press(session, bot, toggle(player.id), user_id=user_id)
    await press(session, bot, show(Screen.SETUP), user_id=user_id)
    await press(session, bot, plain(Action.BEGIN), user_id=user_id)
    return group_id


# --------------------------------------------------------------------------- one message


async def test_pressing_buttons_never_posts_a_second_message(
    session: AsyncSession, bot: FakeBot
) -> None:
    """The whole point of the design: one screen, rewritten."""
    await start_from_buttons(session, bot)
    for data in (show(Screen.TABLE), show(Screen.CHART), show(Screen.ROUND)):
        await press(session, bot, data)

    assert bot.sent == []
    assert {edit.message_id for edit in bot.edited} == {1001}


async def test_the_screen_location_is_stored_for_a_restart(
    session: AsyncSession, bot: FakeBot
) -> None:
    group_id = await start_from_buttons(session, bot)
    view = await active_tournament(session, group_id)
    assert view is not None

    row = await session.get(Tournament, view.id)
    assert row is not None
    assert (row.screen_chat_id, row.screen_message_id) == (CHAT_ID, 1001)


# --------------------------------------------------------------------------- setting up


async def test_ticking_a_player_redraws_with_the_tick(session: AsyncSession, bot: FakeBot) -> None:
    group_id = await seeded_group(session)
    await press(session, bot, show(Screen.ROSTER))
    first = (await list_players(session, group_id))[0]

    await press(session, bot, toggle(first.id))

    assert f"✅ {first.name}" in bot.edited[-1].buttons


async def test_the_draw_appears_once_everyone_is_ticked(
    session: AsyncSession, bot: FakeBot
) -> None:
    group_id = await start_from_buttons(session, bot)
    view = await active_tournament(session, group_id)

    assert view is not None
    assert len(view.rounds) == 7
    assert "Жеребьёвка" in bot.edited[-1].text


async def test_settings_survive_between_presses(session: AsyncSession, bot: FakeBot) -> None:
    await seeded_group(session)
    await press(session, bot, show(Screen.ROSTER))
    for player in await list_players(session, (await handlers._group_for(session, CHAT_ID, ""))):
        await press(session, bot, toggle(player.id))

    await press(session, bot, Callback(Action.SETTING, "pts", "32").pack())
    assert "• до 32" in bot.edited[-1].buttons


# --------------------------------------------------------------------------- scoring


async def test_two_taps_record_a_score(session: AsyncSession, bot: FakeBot) -> None:
    group_id = await start_from_buttons(session, bot)

    await press(session, bot, Callback(Action.COURT, "1").pack())
    assert "Кто выиграл" in bot.edited[-1].text

    await press(session, bot, winner("a"))
    assert "Сколько очков" in bot.edited[-1].text

    await press(session, bot, points(17))

    view = await active_tournament(session, group_id)
    assert view is not None
    scored = view.rounds[0].matches[0]
    assert (scored.score_a, scored.score_b) == (17, 7)


async def test_a_draw_skips_the_second_step(session: AsyncSession, bot: FakeBot) -> None:
    group_id = await start_from_buttons(session, bot)

    await press(session, bot, Callback(Action.COURT, "1").pack())
    await press(session, bot, winner("draw"))

    view = await active_tournament(session, group_id)
    assert view is not None
    assert view.rounds[0].matches[0].score_a == 12
    assert view.rounds[0].matches[0].score_b == 12


async def test_cancelling_a_half_entered_score_goes_back(
    session: AsyncSession, bot: FakeBot
) -> None:
    group_id = await start_from_buttons(session, bot)
    await press(session, bot, Callback(Action.COURT, "1").pack())
    await press(session, bot, winner("a"))

    await press(session, bot, plain(Action.CANCEL))

    view = await active_tournament(session, group_id)
    assert view is not None
    assert not view.rounds[0].matches[0].played
    assert "Раунд 1" in bot.edited[-1].text


async def test_a_mexicano_draws_its_next_round_by_itself(
    session: AsyncSession, bot: FakeBot
) -> None:
    """Finishing a round should not need a separate 'next round' tap."""
    group = await create_group(session, "Вторник")
    await link_group(session, group.id, PROVIDER_TELEGRAM, str(CHAT_ID))
    for name in NAMES:
        await add_player(session, group.id, name)

    await press(session, bot, show(Screen.ROSTER))
    for player in await list_players(session, group.id):
        await press(session, bot, toggle(player.id))
    await press(session, bot, Callback(Action.SETTING, "fmt", "mexicano").pack())
    await press(session, bot, plain(Action.BEGIN))

    view = await active_tournament(session, group.id)
    assert view is not None
    for match in view.rounds[0].matches:
        await press(session, bot, Callback(Action.COURT, str(match.court)).pack())
        await press(session, bot, winner("a"))
        await press(session, bot, points(15))

    view = await active_tournament(session, group.id)
    assert view is not None
    assert len(view.rounds) == 2
    assert "Раунд 2" in bot.edited[-1].text


# --------------------------------------------------------------------------- permissions


async def test_only_the_organiser_may_finish(session: AsyncSession, bot: FakeBot) -> None:
    await start_from_buttons(session, bot, user_id=ORGANISER)

    refused = await press(session, bot, plain(Action.FINISH), user_id=BYSTANDER)
    assert refused.answers[-1].alert
    assert "начал турнир" in (refused.answers[-1].text or "")

    allowed = await press(session, bot, plain(Action.FINISH), user_id=ORGANISER)
    assert not allowed.answers[-1].alert


async def test_anyone_may_enter_a_score(session: AsyncSession, bot: FakeBot) -> None:
    """On court the phone belongs to whoever is nearest."""
    group_id = await start_from_buttons(session, bot, user_id=ORGANISER)

    await press(session, bot, Callback(Action.COURT, "1").pack(), user_id=BYSTANDER)
    await press(session, bot, winner("b"), user_id=BYSTANDER)
    await press(session, bot, points(20), user_id=BYSTANDER)

    view = await active_tournament(session, group_id)
    assert view is not None
    assert view.rounds[0].matches[0].played


async def test_two_people_scoring_at_once_do_not_cross_wires(
    session: AsyncSession, bot: FakeBot
) -> None:
    """Two courts, two phones, one chat.

    The court is chosen in one press and used in the next, so where it waits decides whose
    match gets the score. Keyed by chat, the second person's choice overwrites the first
    person's, and the first person's score lands on a match they never watched.
    """
    group_id = await start_from_buttons(session, bot, user_id=ORGANISER)

    await press(session, bot, Callback(Action.COURT, "1").pack(), user_id=ORGANISER)
    await press(session, bot, Callback(Action.COURT, "2").pack(), user_id=BYSTANDER)

    await press(session, bot, winner("a"), user_id=ORGANISER)
    await press(session, bot, points(20), user_id=ORGANISER)

    view = await active_tournament(session, group_id)
    assert view is not None
    courts = {match.court: match for match in view.rounds[0].matches}
    assert (courts[1].score_a, courts[1].score_b) == (20, 4)
    assert not courts[2].played


# --------------------------------------------------------------------------- errors


async def test_a_score_that_cannot_win_is_refused(session: AsyncSession, bot: FakeBot) -> None:
    """The winner's score has to be a winning one.

    The keyboard only ever offers scores above half the target, so this press cannot come
    from the screen in front of you — but callback data is whatever arrives, and older
    messages from a shorter match are still sitting in the chat with their own buttons.
    Trusting the number would record the declared winner as having lost 10:14.
    """
    group_id = await start_from_buttons(session, bot)
    await press(session, bot, Callback(Action.COURT, "1").pack())
    await press(session, bot, winner("a"))

    await press(session, bot, points(10))

    view = await active_tournament(session, group_id)
    assert view is not None
    assert not view.rounds[0].matches[0].played


async def test_a_score_above_the_target_is_refused(session: AsyncSession, bot: FakeBot) -> None:
    """The other end of the same hole: 30 out of 24 would leave the loser on minus six."""
    group_id = await start_from_buttons(session, bot)
    await press(session, bot, Callback(Action.COURT, "1").pack())
    await press(session, bot, winner("a"))

    await press(session, bot, points(30))

    view = await active_tournament(session, group_id)
    assert view is not None
    assert not view.rounds[0].matches[0].played


async def test_a_court_outside_this_round_is_refused(session: AsyncSession, bot: FakeBot) -> None:
    """Eight players make two courts. A button for a third comes from another tournament."""
    await start_from_buttons(session, bot)

    query = await press(session, bot, Callback(Action.COURT, "9").pack())

    # Not an alert: an alert here would be an internal failure leaking out as a message,
    # because nothing in the flow raises on purpose for a court that is simply not there.
    assert not query.answers[-1].alert
    assert "Кто выиграл" not in bot.edited[-1].text


@pytest.mark.parametrize(
    "data",
    [
        Callback(Action.COURT, "one").pack(),
        Callback(Action.POINTS, "").pack(),
    ],
)
async def test_a_scoring_press_carrying_nonsense_does_nothing(
    session: AsyncSession, bot: FakeBot, data: str
) -> None:
    """Nothing we draw sends these, but callback data is whatever reaches the endpoint.

    ``int()`` on it raises, no handler catches ``ValueError``, and nothing above them turns
    an exception into a reply — so under a webhook the press answers 500 instead of nothing.
    """
    await start_from_buttons(session, bot)

    query = await press(session, bot, data)

    assert not query.answers[-1].alert


async def test_a_setup_press_carrying_nonsense_does_nothing(
    session: AsyncSession, bot: FakeBot
) -> None:
    """The same hole on the setup screen. Pressed while a draft exists, or it proves nothing."""
    group_id = await seeded_group(session)
    await press(session, bot, show(Screen.ROSTER))
    for player in await list_players(session, group_id):
        await press(session, bot, toggle(player.id))
    await press(session, bot, show(Screen.SETUP))

    query = await press(session, bot, Callback(Action.SETTING, "pts", "lots").pack())

    assert not query.answers[-1].alert
    # The bullet marks the chosen target: still 24, so nonsense changed nothing.
    assert "• до 24" in bot.edited[-1].buttons


async def test_an_error_is_shown_as_an_alert_not_a_crash(
    session: AsyncSession, bot: FakeBot
) -> None:
    await seeded_group(session)
    query = await press(session, bot, show(Screen.ROUND))
    assert query.answers[-1].alert
    assert "нет активного турнира" in (query.answers[-1].text or "")


async def test_stale_buttons_do_nothing(session: AsyncSession, bot: FakeBot) -> None:
    """A message from an older version of the bot is still sitting in someone's chat."""
    await seeded_group(session)
    assert Callback.parse("obsolete:thing") is None
    assert bot.edited == []


# --------------------------------------------------------------------------- navigation


async def test_history_lists_what_has_been_played(session: AsyncSession, bot: FakeBot) -> None:
    await start_from_buttons(session, bot)
    await press(session, bot, plain(Action.FINISH))

    await press(session, bot, show(Screen.HISTORY))
    assert "Американо" in bot.edited[-1].text


async def test_going_home_abandons_a_half_built_draft(session: AsyncSession, bot: FakeBot) -> None:
    group_id = await seeded_group(session)
    await press(session, bot, show(Screen.ROSTER))
    first = (await list_players(session, group_id))[0]
    await press(session, bot, toggle(first.id))

    await press(session, bot, show(Screen.HOME))
    assert handlers.drafts.get(CHAT_ID) is None

    await press(session, bot, show(Screen.ROSTER))
    assert "Выбрано: <b>0</b>" in bot.edited[-1].text


async def test_the_home_screen_names_the_group(session: AsyncSession, bot: FakeBot) -> None:
    await seeded_group(session)
    await press(session, bot, show(Screen.HOME))
    assert "Вторничный падел" in bot.edited[-1].text


def test_rendered_screens_always_carry_a_keyboard() -> None:
    """A screen with no buttons is a dead end in a chat."""
    text, markup = screens.home("Клуб", [])
    assert text
    assert markup.inline_keyboard
