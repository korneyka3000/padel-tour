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
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from padel_tour.db import PROVIDER_TELEGRAM
from padel_tour.engine import Format, PadelEngineError, PairingPattern
from padel_tour.services import (
    ServiceError,
    active_tournament,
    add_player,
    advance_round,
    create_group,
    ensure_identity,
    extend_tournament,
    finish_tournament,
    get_tournament,
    group_for_link,
    issue_sign_in_link,
    link_group,
    list_players,
    list_tournaments,
    record_score,
    redeem_invite,
    reroll_tournament,
    start_tournament,
)
from padel_tour.services.errors import (
    DuplicatePlayerNameError,
    NoActiveTournamentError,
    NoTournamentsYetError,
    UnidentifiedCallerError,
)
from padel_tour.services.groups import deactivate_player, get_group, rename_player
from padel_tour.settings import base_url

from . import chart, podium, screens
from .callbacks import Action, Callback, Screen, parse_number, parse_player_id
from .screen_store import hide_chart, remember_screen, show_chart, show_screen
from .setup_state import Draft, DraftStore
from .wording import say

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from padel_tour.db import Account
    from padel_tour.services import TournamentView

logger = logging.getLogger(__name__)

router = Router(name="padel")
drafts = DraftStore()

#: Where a pending score sits between "who won" and "how many", keyed by chat *and person*.
#: Both halves matter. The chat, because one account may play in several groups; the person,
#: because a tournament runs on more than one court and the phones nearest each of them
#: belong to different people. Keyed by chat alone, whoever pressed a court button second
#: would silently steal the first person's match, and the score would land where nobody was
#: watching.
_pending_score: dict[tuple[int, uuid.UUID], tuple[int, str]] = {}

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

    A group made this way is left **without an owner**, which the service layer reads as
    open. That is deliberate: the chat is the membership list. Telegram already decides who
    can see these buttons, and naming one of them owner would only mean the other seven
    cannot add a player. Groups created on the web do get an owner — there the chat is not
    there to answer the question.
    """
    existing = await group_for_link(session, PROVIDER_TELEGRAM, str(chat_id))
    if existing is not None:
        return existing.id
    created = await create_group(session, title or f"Chat {chat_id}")
    await link_group(session, created.id, PROVIDER_TELEGRAM, str(chat_id))
    return created.id


async def _account_for(session: AsyncSession, user_id: int) -> Account:
    """The account behind a Telegram user, minted on first sight.

    A bot already knows who is pressing, so an unfamiliar id is a first visit rather than
    an error — which is why the bot needs no sign-in flow of its own.
    """
    return await ensure_identity(session, PROVIDER_TELEGRAM, str(user_id))


async def _actor(session: AsyncSession, message: Message) -> Account:
    """Who sent this.

    A message with no sender is a channel post. There is nobody to attribute it to, and
    passing "nobody" downstream would read as *system*, which skips every permission check.
    """
    if message.from_user is None:
        raise UnidentifiedCallerError("no sender on this message — write under your own name")
    return await _account_for(session, message.from_user.id)


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
        raise NoActiveTournamentError("no tournament is running right now")
    return view


async def _active_or_last(session: AsyncSession, group_id: uuid.UUID) -> TournamentView:
    """The running tournament, or the most recent one if nothing is live."""
    view = await active_tournament(session, group_id)
    if view is not None:
        return view
    recent = await list_tournaments(session, group_id, limit=1)
    if not recent:
        raise NoTournamentsYetError("no tournaments have been played yet")
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
    """Bind this chat to a group and show where things stand.

    ``/start <token>`` is how an invitation is accepted in Telegram: the owner shares a
    ``t.me/bot?start=<token>`` link and Telegram hands the token back here. It is the same
    token the web accepts, because it invites someone to a *player*, not to a surface.
    """
    payload = (message.text or "").partition(" ")[2].strip()
    if payload:
        await _accept_invite(session, message, payload)
        return

    title = message.chat.title or (message.from_user.full_name if message.from_user else "")
    group_id = await _group_for(session, message.chat.id, title)
    await _paint(bot, session, message.chat.id, await _current_screen(session, group_id))


async def _accept_invite(session: AsyncSession, message: Message, token: str) -> None:
    """Claim the player an invitation names."""
    try:
        player = await redeem_invite(session, token, await _actor(session, message))
    except ServiceError as exc:
        await message.reply(say(exc))
        return
    await message.reply(f"Готово — теперь вы играете как <b>{player.name}</b>")


@router.message(Command("add"))
async def on_add(message: Message, session: AsyncSession, bot: Bot) -> None:
    """``/add Аня, Боря`` — put people on the roster."""
    _, _, rest = (message.text or "").partition(" ")
    names = [name.strip() for name in rest.split(",") if name.strip()]
    if not names:
        await message.reply("Кого добавить? Например: <code>/add Аня, Боря</code>")
        return

    actor = await _actor(session, message)
    group_id = await _group_for(session, message.chat.id, message.chat.title or "")
    added, already = [], []
    for name in names:
        try:
            player = await add_player(session, group_id, name, actor=actor)
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


@router.message(Command("login"))
async def on_login(message: Message, session: AsyncSession) -> None:
    """A way into the web for somebody the bot already knows.

    **Private chats only, and that is not a nicety.** The link signs its holder in as the
    person who asked for it; posted in a group it would hand the whole chat one member's
    account. Telegram gives no way to make a message visible to one person in a group, so
    the answer there is to say where to ask instead.

    No mail server involved: the bot has already established who this is, which is the
    entire thing an emailed link exists to do.
    """
    if message.chat.type != "private":
        await message.reply("Напишите мне <code>/login</code> в личку — ссылка личная.")
        return

    actor = await _actor(session, message)
    token = await issue_sign_in_link(session, actor)
    await message.reply(
        "Ссылка для входа на сайт — она одноразовая и живёт пятнадцать минут:\n"
        f"{base_url()}/auth/enter?token={token}"
    )


@router.message(Command("rename"))
async def on_rename(message: Message, session: AsyncSession, bot: Bot) -> None:
    """``/rename Аня = Анна`` — fix a name without touching the history behind it."""
    _, _, rest = (message.text or "").partition(" ")
    before, sign, after = rest.partition("=")
    if not sign or not before.strip() or not after.strip():
        await message.reply("Как переименовать? Например: <code>/rename Аня = Анна</code>")
        return

    actor = await _actor(session, message)
    group_id = await _group_for(session, message.chat.id, message.chat.title or "")
    roster = await list_players(session, group_id)
    match = next((p for p in roster if p.name.casefold() == before.strip().casefold()), None)
    if match is None:
        await message.reply(f"В составе нет игрока «{before.strip()}»")
        return

    renamed = await rename_player(session, match.id, after.strip(), actor=actor)
    await message.reply(f"{match.name} → {renamed.name}")
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
    actor = await _account_for(session, query.from_user.id)
    group_id = await _group_for(session, chat_id, query.message.chat.title or "")

    if parsed.action is Action.SHOW and parsed.arg == Screen.CHART:
        await _chart(bot, session, chat_id, group_id, query)
        return

    # Which tournament was running before this press, so the one press that ends one can be
    # told apart from every press afterwards. Compared rather than flagged: the alternative
    # is threading "did it just finish" back through four handlers that have no other reason
    # to know.
    running = await active_tournament(session, group_id)

    # Any other press means the chat has moved on, and the picture goes with it. Done here
    # rather than in each handler so nobody has to remember.
    await hide_chart(bot, session, chat_id, group_id)

    try:
        rendered, tournament_id, note = await _dispatch(session, parsed, chat_id, group_id, actor)
    except (PadelEngineError, ServiceError) as exc:
        # These messages are written for people. Show the reason, then put the screen back
        # in step with what is actually stored.
        await query.answer(say(exc), show_alert=True)
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
    if running is not None and await active_tournament(session, group_id) is None:
        await _celebrate(bot, session, chat_id, running.id)
    if rendered is not None:
        await _paint(
            bot, session, chat_id, rendered, tournament_id=tournament_id, message_id=message_id
        )


async def _dispatch(
    session: AsyncSession,
    press: Callback,
    chat_id: int,
    group_id: uuid.UUID,
    actor: Account,
) -> Outcome:
    """Work out what a press means.

    Split by phase rather than handled in one long match: assembling a tournament, scoring
    one, and ending one are three separate concerns that happen not to share a button bar.
    Each sub-dispatcher returns ``None`` for presses that are not its business.
    """
    if press.action is Action.SHOW:
        return await _show(session, press.arg, chat_id, group_id, actor)

    for phase in (_setup_action, _scoring_action, _lifecycle_action):
        outcome = await phase(session, press, chat_id, group_id, actor)
        if outcome is not None:
            return outcome
    return _NOTHING


async def _setup_action(
    session: AsyncSession,
    press: Callback,
    chat_id: int,
    group_id: uuid.UUID,
    actor: Account,
) -> Outcome | None:
    """Assembling a tournament: roster, options, draw."""
    match press.action:
        case Action.TOGGLE:
            return await _toggle(session, press.arg, chat_id, group_id)
        case Action.DROP:
            return await _drop(session, press.arg, group_id, actor)
        case Action.SETTING:
            return _setting(press, chat_id)
        case Action.BEGIN:
            return await _begin(session, chat_id, group_id, actor)
        case Action.REROLL:
            return await _reroll(session, group_id, actor)
    return None


async def _scoring_action(
    session: AsyncSession,
    press: Callback,
    chat_id: int,
    group_id: uuid.UUID,
    actor: Account,
) -> Outcome | None:
    """Entering a result, in its two steps."""
    match press.action:
        case Action.COURT if (court_no := parse_number(press.arg)) is not None:
            return await _court(session, group_id, chat_id, court_no, actor)
        case Action.WINNER:
            return await _winner(session, group_id, chat_id, press.arg, actor)
        case Action.POINTS if (value := parse_number(press.arg)) is not None:
            return await _points(session, group_id, chat_id, value, actor)
        case Action.CANCEL:
            _pending_score.pop((chat_id, actor.id), None)
            return await _round(session, group_id)
    return None


async def _lifecycle_action(
    session: AsyncSession,
    press: Callback,
    chat_id: int,
    group_id: uuid.UUID,
    actor: Account,
) -> Outcome | None:
    """Moving a tournament on, or ending it."""
    _ = chat_id
    match press.action:
        case Action.CONFIRM:
            view = await _require_active(session, group_id)
            return screens.confirm_finish(view), view.id, ""
        case Action.FINISH:
            return await _finish(session, group_id, actor)
        case Action.ADVANCE:
            active = await _require_active(session, group_id)
            view = await advance_round(session, active.id, actor=actor)
            return screens.round_screen(view), view.id, ""
        case Action.EXTEND:
            active = await _require_active(session, group_id)
            view = await extend_tournament(session, active.id, actor=actor)
            view = await advance_round(session, view.id, actor=actor)
            return screens.round_screen(view), view.id, "Ещё раунд"
    return None


# --------------------------------------------------------------------------- navigation


async def _show(
    session: AsyncSession, raw: str, chat_id: int, group_id: uuid.UUID, actor: Account
) -> Outcome:
    """Navigate. Unknown screen names come from stale messages and simply do nothing."""
    try:
        screen = Screen(raw)
    except ValueError:
        return _NOTHING

    lobby = await _show_lobby(session, screen, chat_id, group_id, actor)
    if lobby is not None:
        return lobby
    return await _show_tournament(session, screen, group_id)


async def _show_lobby(
    session: AsyncSession,
    screen: Screen,
    chat_id: int,
    group_id: uuid.UUID,
    actor: Account,
) -> Outcome | None:
    """Screens that exist whether or not a tournament is running."""
    match screen:
        case Screen.HOME:
            drafts.clear(chat_id)
            return await _home(session, group_id), None, ""
        case Screen.SQUAD:
            return screens.squad_screen(await list_players(session, group_id)), None, ""
        case Screen.ROSTER:
            return await _who_plays(session, chat_id, group_id)
        case Screen.SETUP:
            return await _setup_screen(session, chat_id, group_id, actor)
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
            # Handled before dispatch, in on_press — it is a photo, and this function can
            # only return text. Falling through to the round screen would be a lie, so the
            # case is spelled out rather than left to the default.
            return _NOTHING
    return _NOTHING


async def _celebrate(
    bot: Bot, session: AsyncSession, chat_id: int, tournament_id: uuid.UUID
) -> None:
    """Post the final card, once, at the moment a tournament ends.

    Its own message, and unlike the chart it is not taken down again. Two hours on court
    end in something the group can scroll back to and send to whoever missed it — deleting
    that on the next button press would be the opposite of the point.

    A failure here is swallowed. The tournament is over either way, and a chat that cannot
    receive a photo should still see its final table.
    """
    view = await get_tournament(session, tournament_id)
    card = podium.render(view)
    if card is None:  # pragma: no cover - a tournament with no played round cannot finish here
        return
    try:
        await bot.send_photo(
            chat_id=chat_id,
            photo=BufferedInputFile(card, filename="podium.png"),
            caption=f"🏆 <b>{screens.esc(view.standings[0].name)}</b> берёт турнир",
        )
    except TelegramBadRequest:
        logger.info("could not post the final card to %s", chat_id)


async def _chart(
    bot: Bot,
    session: AsyncSession,
    chat_id: int,
    group_id: uuid.UUID,
    query: CallbackQuery,
) -> None:
    """Draw the chart and put it up as its own message.

    Outside the ordinary dispatch because everything else on this screen is text, and a
    text message cannot become a photo one. A tournament with nothing played yet has no
    chart to show, so it says so instead of posting an empty grid.
    """
    try:
        view = await _active_or_last(session, group_id)
    except ServiceError as exc:
        await query.answer(say(exc), show_alert=True)
        return

    png = chart.render(view)
    if png is None:
        await query.answer("Сыграйте раунд — тогда будет что показать", show_alert=True)
        return

    await query.answer()
    await show_chart(bot, session, chat_id, view.id, png, screens.chart_caption(view))


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


async def _setup_screen(
    session: AsyncSession, chat_id: int, group_id: uuid.UUID, actor: Account
) -> Outcome:
    """Tournament options. Without a draft there is nothing to configure, so go back a step."""
    draft = drafts.get(chat_id)
    if draft is None:
        return await _show(session, Screen.ROSTER.value, chat_id, group_id, actor)
    return _setup_view(draft), None, ""


async def _who_plays(session: AsyncSession, chat_id: int, group_id: uuid.UUID) -> Outcome:
    """The selection screen, with everybody already in.

    Starting from nobody made the organiser tick eight names to describe the ordinary
    evening — the whole group turning up. Starting from everybody makes the taps describe
    the exception instead, which is who could not make it.
    """
    roster = await list_players(session, group_id)
    draft = drafts.get(chat_id)
    if draft is None:
        draft = drafts.start(chat_id, group_id)
        draft.selected = {player.id for player in roster}
    return screens.roster_screen(roster, draft.selected, draft.allowed_counts()), None, ""


async def _drop(session: AsyncSession, raw: str, group_id: uuid.UUID, actor: Account) -> Outcome:
    """Take somebody off the roster.

    Hidden, not deleted: the row carries every match they played, and dropping it would
    rewrite the group's history to say those games never happened. ``/add`` with the same
    name brings them back, which is why one tap is enough.
    """
    player_id = parse_player_id(raw)
    if player_id is None:
        return _NOTHING
    player = await deactivate_player(session, player_id, actor=actor)
    return screens.squad_screen(await list_players(session, group_id)), None, f"{player.name} убран"


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
        case "pts" if (target := parse_number(press.extra)) is not None:
            draft.points_per_match = target
        case "pat":
            draft.pairing_pattern = PairingPattern(press.extra)
        case "rnd":
            current = draft.rounds or draft.default_rounds
            delta = {"+1": 1, "-1": -1}.get(press.extra, 0)
            draft.rounds = max(1, current + delta)

    if not draft.ready:
        return None, None, "Состав больше не подходит под формат — поправьте на прошлом экране"
    return _setup_view(draft), None, ""


async def _begin(
    session: AsyncSession, chat_id: int, group_id: uuid.UUID, actor: Account
) -> Outcome:
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
        actor=actor,
    )
    drafts.clear(chat_id)
    return screens.draw_screen(view), view.id, "Жеребьёвка готова"


async def _reroll(session: AsyncSession, group_id: uuid.UUID, actor: Account) -> Outcome:
    view = await _require_active(session, group_id)
    view = await reroll_tournament(session, view.id, actor=actor)
    return screens.draw_screen(view), view.id, "Пересдал"


# --------------------------------------------------------------------------- scoring


async def _court(
    session: AsyncSession, group_id: uuid.UUID, chat_id: int, court_no: int, actor: Account
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
    if not any(match.court == court_no for match in rnd.matches):
        # Twelve players make three courts, eight make two, and the old message is still in
        # the chat with a button for the third. Nothing is wrong here worth an alert.
        return screens.round_screen(view), view.id, ""
    _pending_score[chat_id, actor.id] = (court_no, "")
    return screens.winner_screen(view, rnd, court_no), view.id, ""


async def _winner(
    session: AsyncSession, group_id: uuid.UUID, chat_id: int, side: str, actor: Account
) -> Outcome:
    view = await _require_active(session, group_id)
    rnd = view.next_unfinished_round
    if rnd is None:
        return screens.round_screen(view), view.id, ""

    pending = _pending_score.get((chat_id, actor.id))
    if pending is None:
        # The court button is what selects a match; without it we would be guessing.
        return screens.round_screen(view), view.id, ""
    court_no = pending[0]

    if side == "draw":
        half = view.points_per_match // 2
        return await _apply_score(session, group_id, chat_id, court_no, half, half, actor)

    _pending_score[chat_id, actor.id] = (court_no, side)
    return screens.points_screen(view, court_no), view.id, ""


async def _points(
    session: AsyncSession, group_id: uuid.UUID, chat_id: int, value: int, actor: Account
) -> Outcome:
    pending = _pending_score.get((chat_id, actor.id))
    if pending is None:
        return await _round(session, group_id)

    court_no, side = pending
    view = await _require_active(session, group_id)

    # The keyboard only offers scores that win, so a number outside that range arrived from
    # somewhere else — an older message, a shorter match, a replayed press. Deriving the
    # loser's score from it anyway would file the declared winner as the loser and look like
    # a perfectly ordinary result. Checked here rather than in the engine: the engine sees
    # two numbers that add up correctly and has no way to know which side was called out.
    lowest = view.points_per_match // 2 + 1
    if not lowest <= value <= view.points_per_match:
        note = f"Счёт победителя — от {lowest} до {view.points_per_match}"
        return screens.points_screen(view, court_no), view.id, note

    loser = view.points_per_match - value
    score_a, score_b = (value, loser) if side == "a" else (loser, value)
    return await _apply_score(session, group_id, chat_id, court_no, score_a, score_b, actor)


async def _apply_score(
    session: AsyncSession,
    group_id: uuid.UUID,
    chat_id: int,
    court_no: int,
    score_a: int,
    score_b: int,
    actor: Account,
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
        actor=actor,
    )
    _pending_score.pop((chat_id, actor.id), None)

    if view.finished:
        return screens.table_screen(view), view.id, "Турнир завершён"

    # A Mexicano cannot show the next round until it has been drawn from the new standing.
    if view.next_unfinished_round is None and len(view.rounds) < view.total_rounds:
        view = await advance_round(session, view.id, actor=actor)
        return screens.round_screen(view), view.id, "Следующий раунд"

    return screens.round_screen(view), view.id, "Записал"


# --------------------------------------------------------------------------- finishing


async def _finish(session: AsyncSession, group_id: uuid.UUID, actor: Account) -> Outcome:
    view = await _require_active(session, group_id)
    view = await finish_tournament(session, view.id, actor=actor)
    return screens.table_screen(view), view.id, "Турнир завершён"
