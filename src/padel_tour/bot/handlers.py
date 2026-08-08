"""Handlers: turn a press into a change of state, then redraw the screen.

Every callback ends the same way — work out the new state, ask :mod:`screens` for text and
buttons, and rewrite the one message this tournament owns.

Errors from the engine and the service layer are already written for a person, so they go
straight into the little alert Telegram shows above the message. Nothing is logged as a
crash that a user could cause by pressing a button twice.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from padel_tour.db import PROVIDER_TELEGRAM
from padel_tour.engine import Format, PadelEngineError, PairingPattern
from padel_tour.services import (
    ServiceError,
    active_tournament,
    add_player,
    advance_round,
    create_group,
    ensure_identity,
    finish_tournament,
    get_tournament,
    group_for_link,
    link_group,
    list_players,
    list_tournaments,
    record_score,
    reroll_tournament,
    start_tournament,
)
from padel_tour.services.errors import DuplicatePlayerNameError
from padel_tour.services.groups import get_group

from . import screens
from .callbacks import Action, Callback, Screen, parse_player_id
from .screen_store import remember_screen, show_screen
from .setup_state import Draft, DraftStore

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from padel_tour.services import TournamentView

logger = logging.getLogger(__name__)

router = Router(name="padel")
drafts = DraftStore()

#: Where a pending score sits between "who won" and "how many", keyed by chat. Two people
#: scoring different courts at the same second would collide; in a group standing around one
#: court that is not a real scenario, and the second entry simply replaces the first.
_pending_score: dict[int, tuple[int, str]] = {}

#: How many past tournaments the history screen shows.
HISTORY_LIMIT = 10

#: What a press produces: the screen to draw, which tournament owns it, and an optional note
#: to flash above the message.
type Outcome = tuple[screens.Rendered | None, "uuid.UUID | None", str]

_NOTHING: Outcome = (None, None, "")


# --------------------------------------------------------------------------- helpers


async def _group_for(session: AsyncSession, chat_id: int, title: str) -> uuid.UUID:
    """The group reachable from this chat, created the first time the bot is used here.

    Resolving a chat id to a group is the adapter's job. Below this line nothing knows
    that Telegram exists.
    """
    existing = await group_for_link(session, PROVIDER_TELEGRAM, str(chat_id))
    if existing is not None:
        return existing.id
    created = await create_group(session, title or f"Chat {chat_id}")
    await link_group(session, created.id, PROVIDER_TELEGRAM, str(chat_id))
    return created.id


async def _account_for(session: AsyncSession, user_id: int) -> uuid.UUID:
    """The account behind a Telegram user, minted on first sight.

    A bot already knows who is pressing, so an unfamiliar id is a first visit rather than
    an error — which is why the bot needs no sign-in flow of its own.
    """
    account = await ensure_identity(session, PROVIDER_TELEGRAM, str(user_id))
    return account.id


async def _group_name(session: AsyncSession, group_id: uuid.UUID) -> str:
    return (await get_group(session, group_id)).name


async def _home(session: AsyncSession, group_id: uuid.UUID) -> screens.Rendered:
    roster = await list_players(session, group_id)
    return screens.home(await _group_name(session, group_id), roster)


async def _current_screen(session: AsyncSession, group_id: uuid.UUID) -> screens.Rendered:
    """Whatever this chat should be looking at right now."""
    view = await active_tournament(session, group_id)
    if view is not None:
        return screens.round_screen(view)
    return await _home(session, group_id)


async def _paint(
    bot: Bot,
    session: AsyncSession,
    chat_id: int,
    rendered: screens.Rendered,
    *,
    tournament_id: uuid.UUID | None = None,
    message_id: int | None = None,
) -> None:
    await show_screen(
        bot,
        session,
        chat_id,
        rendered,
        tournament_id=tournament_id,
        message_id=message_id,
    )


async def _require_active(session: AsyncSession, group_id: uuid.UUID) -> TournamentView:
    view = await active_tournament(session, group_id)
    if view is None:
        raise ServiceError("Сейчас нет активного турнира")
    return view


async def _active_or_last(session: AsyncSession, group_id: uuid.UUID) -> TournamentView:
    """The running tournament, or the most recent one if nothing is live."""
    view = await active_tournament(session, group_id)
    if view is not None:
        return view
    recent = await list_tournaments(session, group_id, limit=1)
    if not recent:
        raise ServiceError("Турниров ещё не было")
    return await get_tournament(session, recent[0].id)


def _setup_view(draft: Draft) -> screens.Rendered:
    return screens.setup_screen(
        draft.format,
        draft.points_per_match,
        draft.pairing_pattern,
        draft.rounds or draft.default_rounds,
        len(draft.selected),
    )


# --------------------------------------------------------------------------- commands


@router.message(CommandStart())
async def on_start(message: Message, session: AsyncSession, bot: Bot) -> None:
    """Bind this chat to a group and show where things stand."""
    title = message.chat.title or (message.from_user.full_name if message.from_user else "")
    group_id = await _group_for(session, message.chat.id, title)
    await _paint(bot, session, message.chat.id, await _current_screen(session, group_id))


@router.message(Command("add"))
async def on_add(message: Message, session: AsyncSession, bot: Bot) -> None:
    """``/add Аня, Боря`` — put people on the roster."""
    _, _, rest = (message.text or "").partition(" ")
    names = [name.strip() for name in rest.split(",") if name.strip()]
    if not names:
        await message.reply("Кого добавить? Например: <code>/add Аня, Боря</code>")
        return

    group_id = await _group_for(session, message.chat.id, message.chat.title or "")
    added, already = [], []
    for name in names:
        try:
            player = await add_player(session, group_id, name)
        except DuplicatePlayerNameError:
            already.append(name)
        else:
            added.append(player.name)

    parts = []
    if added:
        parts.append("Добавлены: " + ", ".join(added))
    if already:
        parts.append("Уже были: " + ", ".join(already))
    await message.reply("\n".join(parts))
    await _paint(bot, session, message.chat.id, await _current_screen(session, group_id))


@router.message(Command("tournament"))
async def on_tournament(message: Message, session: AsyncSession, bot: Bot) -> None:
    """Repost the live screen, for when it has scrolled out of sight."""
    group_id = await _group_for(session, message.chat.id, message.chat.title or "")
    view = await active_tournament(session, group_id)
    text, markup = screens.round_screen(view) if view else await _home(session, group_id)
    sent = await bot.send_message(chat_id=message.chat.id, text=text, reply_markup=markup)
    if view is not None:
        await remember_screen(session, view.id, message.chat.id, sent.message_id)


# --------------------------------------------------------------------------- callbacks


@router.callback_query(F.data)
async def on_press(query: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    """Every button in the bot arrives here."""
    parsed = Callback.parse(query.data or "")
    if parsed is None or not isinstance(query.message, Message):
        await query.answer()
        return

    chat_id = query.message.chat.id
    message_id = query.message.message_id
    user_id = query.from_user.id
    group_id = await _group_for(session, chat_id, query.message.chat.title or "")

    try:
        rendered, tournament_id, note = await _dispatch(session, parsed, chat_id, group_id, user_id)
    except (PadelEngineError, ServiceError) as exc:
        # These messages are written for people. Show the reason, then put the screen back
        # in step with what is actually stored.
        await query.answer(str(exc), show_alert=True)
        view = await active_tournament(session, group_id)
        if view is not None:
            await _paint(
                bot,
                session,
                chat_id,
                screens.round_screen(view),
                tournament_id=view.id,
                message_id=message_id,
            )
        return

    await query.answer(note or None)
    if rendered is not None:
        await _paint(
            bot, session, chat_id, rendered, tournament_id=tournament_id, message_id=message_id
        )


async def _dispatch(
    session: AsyncSession,
    press: Callback,
    chat_id: int,
    group_id: uuid.UUID,
    user_id: int,
) -> Outcome:
    """Work out what a press means.

    Split by phase rather than handled in one long match: assembling a tournament, scoring
    one, and ending one are three separate concerns that happen not to share a button bar.
    Each sub-dispatcher returns ``None`` for presses that are not its business.
    """
    if press.action is Action.SHOW:
        return await _show(session, press.arg, chat_id, group_id, user_id)

    for phase in (_setup_action, _scoring_action, _lifecycle_action):
        outcome = await phase(session, press, chat_id, group_id, user_id)
        if outcome is not None:
            return outcome
    return _NOTHING


async def _setup_action(
    session: AsyncSession,
    press: Callback,
    chat_id: int,
    group_id: uuid.UUID,
    user_id: int,
) -> Outcome | None:
    """Assembling a tournament: roster, options, draw."""
    match press.action:
        case Action.TOGGLE:
            return await _toggle(session, press.arg, chat_id, group_id)
        case Action.SETTING:
            return _setting(press, chat_id)
        case Action.BEGIN:
            return await _begin(session, chat_id, group_id, user_id)
        case Action.REROLL:
            return await _reroll(session, group_id, user_id)
    return None


async def _scoring_action(
    session: AsyncSession,
    press: Callback,
    chat_id: int,
    group_id: uuid.UUID,
    user_id: int,
) -> Outcome | None:
    """Entering a result, in its two steps."""
    _ = user_id
    match press.action:
        case Action.COURT:
            return await _court(session, group_id, chat_id, int(press.arg))
        case Action.WINNER:
            return await _winner(session, group_id, chat_id, press.arg)
        case Action.POINTS:
            return await _points(session, group_id, chat_id, int(press.arg))
        case Action.CANCEL:
            _pending_score.pop(chat_id, None)
            return await _round(session, group_id)
    return None


async def _lifecycle_action(
    session: AsyncSession,
    press: Callback,
    chat_id: int,
    group_id: uuid.UUID,
    user_id: int,
) -> Outcome | None:
    """Moving a tournament on, or ending it."""
    _ = chat_id
    match press.action:
        case Action.CONFIRM:
            view = await _require_active(session, group_id)
            return screens.confirm_finish(view), view.id, ""
        case Action.FINISH:
            return await _finish(session, group_id, user_id)
        case Action.ADVANCE:
            active = await _require_active(session, group_id)
            view = await advance_round(session, active.id)
            return screens.round_screen(view), view.id, ""
    return None


# --------------------------------------------------------------------------- navigation


async def _show(
    session: AsyncSession, raw: str, chat_id: int, group_id: uuid.UUID, user_id: int
) -> Outcome:
    """Navigate. Unknown screen names come from stale messages and simply do nothing."""
    try:
        screen = Screen(raw)
    except ValueError:
        return _NOTHING

    lobby = await _show_lobby(session, screen, chat_id, group_id, user_id)
    if lobby is not None:
        return lobby
    return await _show_tournament(session, screen, group_id)


async def _show_lobby(
    session: AsyncSession,
    screen: Screen,
    chat_id: int,
    group_id: uuid.UUID,
    user_id: int,
) -> Outcome | None:
    """Screens that exist whether or not a tournament is running."""
    match screen:
        case Screen.HOME:
            drafts.clear(chat_id)
            return await _home(session, group_id), None, ""
        case Screen.ROSTER:
            draft = drafts.get(chat_id) or drafts.start(chat_id, group_id, user_id)
            roster = await list_players(session, group_id)
            return (
                screens.roster_screen(roster, draft.selected, draft.allowed_counts()),
                None,
                "",
            )
        case Screen.SETUP:
            draft = drafts.get(chat_id)
            if draft is None:
                return await _show(session, Screen.ROSTER.value, chat_id, group_id, user_id)
            return _setup_view(draft), None, ""
        case Screen.HISTORY:
            entries = await list_tournaments(session, group_id, limit=HISTORY_LIMIT)
            return screens.history_screen(entries), None, ""
    return None


async def _show_tournament(session: AsyncSession, screen: Screen, group_id: uuid.UUID) -> Outcome:
    """Screens that need a tournament to look at."""
    match screen:
        case Screen.DRAW:
            view = await _require_active(session, group_id)
            return screens.draw_screen(view), view.id, ""
        case Screen.ROUND:
            return await _round(session, group_id)
        case Screen.TABLE:
            view = await _active_or_last(session, group_id)
            return screens.table_screen(view), view.id, ""
        case Screen.CHART:
            view = await _active_or_last(session, group_id)
            return screens.chart_screen(view), view.id, ""
    return _NOTHING


async def _round(session: AsyncSession, group_id: uuid.UUID) -> Outcome:
    view = await _require_active(session, group_id)
    return screens.round_screen(view), view.id, ""


# --------------------------------------------------------------------------- setting up


async def _toggle(session: AsyncSession, raw: str, chat_id: int, group_id: uuid.UUID) -> Outcome:
    """Tick a player in or out. The screen must redraw, or the tick never appears."""
    draft = drafts.get(chat_id)
    player_id = parse_player_id(raw)
    if draft is None or player_id is None:
        return _NOTHING

    draft.toggle(player_id)
    roster = await list_players(session, group_id)
    return screens.roster_screen(roster, draft.selected, draft.allowed_counts()), None, ""


def _setting(press: Callback, chat_id: int) -> Outcome:
    """Change one tournament option."""
    draft = drafts.get(chat_id)
    if draft is None:
        return _NOTHING

    match press.arg:
        case "fmt":
            draft.format = Format(press.extra)
            # Americano schedules only certain player counts, so a switch can invalidate a
            # selection that was fine a moment ago. The roster screen says so plainly.
        case "pts":
            draft.points_per_match = int(press.extra)
        case "pat":
            draft.pairing_pattern = PairingPattern(press.extra)
        case "rnd":
            current = draft.rounds or draft.default_rounds
            delta = {"+1": 1, "-1": -1}.get(press.extra, 0)
            draft.rounds = max(1, current + delta)

    if not draft.ready:
        return None, None, "Состав больше не подходит под формат — поправьте на прошлом экране"
    return _setup_view(draft), None, ""


async def _begin(session: AsyncSession, chat_id: int, group_id: uuid.UUID, user_id: int) -> Outcome:
    """Draw the tournament and show it."""
    draft = drafts.get(chat_id)
    if draft is None:
        return await _home(session, group_id), None, "Начните заново"
    if not draft.ready:
        return _NOTHING

    roster = await list_players(session, group_id)
    order = [player.id for player in roster if player.id in draft.selected]
    view = await start_tournament(
        session,
        group_id,
        order,
        draft.config(),
        organiser_account_id=await _account_for(session, user_id),
    )
    drafts.clear(chat_id)
    return screens.draw_screen(view), view.id, "Жеребьёвка готова"


async def _reroll(session: AsyncSession, group_id: uuid.UUID, user_id: int) -> Outcome:
    view = await _require_active(session, group_id)
    _require_organiser(view, await _account_for(session, user_id))
    view = await reroll_tournament(session, view.id)
    return screens.draw_screen(view), view.id, "Пересдал"


# --------------------------------------------------------------------------- scoring


async def _court(
    session: AsyncSession, group_id: uuid.UUID, chat_id: int, court_no: int
) -> Outcome:
    """Step one: which court are we scoring.

    The court is remembered here rather than inferred later. Working it out at the next step
    would mean guessing, and with two courts in play the guess sends the score to the wrong
    match.
    """
    view = await _require_active(session, group_id)
    rnd = view.next_unfinished_round
    if rnd is None:
        return screens.round_screen(view), view.id, ""
    _pending_score[chat_id] = (court_no, "")
    return screens.winner_screen(view, rnd, court_no), view.id, ""


async def _winner(session: AsyncSession, group_id: uuid.UUID, chat_id: int, side: str) -> Outcome:
    view = await _require_active(session, group_id)
    rnd = view.next_unfinished_round
    if rnd is None:
        return screens.round_screen(view), view.id, ""

    pending = _pending_score.get(chat_id)
    if pending is None:
        # The court button is what selects a match; without it we would be guessing.
        return screens.round_screen(view), view.id, ""
    court_no = pending[0]

    if side == "draw":
        half = view.points_per_match // 2
        return await _apply_score(session, group_id, chat_id, court_no, half, half)

    _pending_score[chat_id] = (court_no, side)
    return screens.points_screen(view, court_no), view.id, ""


async def _points(session: AsyncSession, group_id: uuid.UUID, chat_id: int, value: int) -> Outcome:
    pending = _pending_score.get(chat_id)
    if pending is None:
        return await _round(session, group_id)

    court_no, side = pending
    view = await _require_active(session, group_id)
    loser = view.points_per_match - value
    score_a, score_b = (value, loser) if side == "a" else (loser, value)
    return await _apply_score(session, group_id, chat_id, court_no, score_a, score_b)


async def _apply_score(
    session: AsyncSession,
    group_id: uuid.UUID,
    chat_id: int,
    court_no: int,
    score_a: int,
    score_b: int,
) -> Outcome:
    """Record a score, then move the screen on to whatever comes next."""
    view = await _require_active(session, group_id)
    rnd = view.next_unfinished_round
    if rnd is None:
        return screens.round_screen(view), view.id, ""

    view = await record_score(
        session,
        view.id,
        round_no=rnd.number,
        court=court_no,
        score_a=score_a,
        score_b=score_b,
    )
    _pending_score.pop(chat_id, None)

    if view.finished:
        return screens.table_screen(view), view.id, "Турнир завершён"

    # A Mexicano cannot show the next round until it has been drawn from the new standing.
    if view.next_unfinished_round is None and len(view.rounds) < view.total_rounds:
        view = await advance_round(session, view.id)
        return screens.round_screen(view), view.id, "Следующий раунд"

    return screens.round_screen(view), view.id, "Записал"


# --------------------------------------------------------------------------- finishing


def _require_organiser(view: TournamentView, actor_account_id: uuid.UUID | None) -> None:
    """Anyone may enter a score; only the organiser may end or redraw.

    Entering scores has to stay open — on court the phone belongs to whoever is nearest.
    Ending a tournament or redrawing the schedule takes the game away from everyone else,
    so it stays with the person who started it. Proper roles arrive with accounts in M5.

    A tournament started before this rule existed, or from the CLI, has no organiser
    recorded; those stay open to everyone rather than locked to nobody.
    """
    if view.organiser_account_id is None:
        return
    if view.organiser_account_id != actor_account_id:
        raise ServiceError("Это может сделать только тот, кто начал турнир")


async def _finish(session: AsyncSession, group_id: uuid.UUID, user_id: int) -> Outcome:
    view = await _require_active(session, group_id)
    _require_organiser(view, await _account_for(session, user_id))
    view = await finish_tournament(session, view.id)
    return screens.table_screen(view), view.id, "Турнир завершён"
