"""Screens are pure functions, so the whole interface can be checked without Telegram.

What matters is not the exact wording but that the right buttons exist and the wrong ones
do not: a scored court must not offer to be scored again, and a roster that cannot be
scheduled must not offer to continue.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from conftest import NAMES, make_tournament, play_round
from padel_tour.bot import screens
from padel_tour.bot.callbacks import Action, Callback, Screen
from padel_tour.engine import Format, PairingPattern, TournamentConfig
from padel_tour.services import (
    PlayerView,
    TournamentSummary,
    add_player,
    create_group,
    finish_tournament,
    list_players,
    list_tournaments,
    record_score,
    start_tournament,
)

if TYPE_CHECKING:
    from aiogram.types import InlineKeyboardMarkup
    from sqlalchemy.ext.asyncio import AsyncSession


def actions(markup: InlineKeyboardMarkup) -> list[Callback]:
    """Every button on a screen, parsed."""
    parsed = []
    for row in markup.inline_keyboard:
        for button in row:
            if button.callback_data:
                press = Callback.parse(button.callback_data)
                if press is not None:
                    parsed.append(press)
    return parsed


def labels(markup: InlineKeyboardMarkup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


def fake_player(name: str) -> PlayerView:
    return PlayerView(id=uuid.uuid7(), group_id=uuid.uuid7(), name=name, is_active=True)


# --------------------------------------------------------------------------- home


def test_home_without_players_explains_how_to_add_them() -> None:
    text, markup = screens.home("Вторник", [])
    assert "/add" in text
    assert not any(press.arg == Screen.ROSTER.value for press in actions(markup))


def test_home_offers_a_tournament_once_there_are_four() -> None:
    roster = [fake_player(name) for name in NAMES[:4]]
    _, markup = screens.home("Вторник", roster)
    assert any(press.arg == Screen.ROSTER.value for press in actions(markup))


def test_home_collapses_a_long_roster() -> None:
    roster = [fake_player(f"Игрок {index}") for index in range(1, 21)]
    text, _ = screens.home("Вторник", roster)
    assert "…и ещё 8" in text


def test_names_are_escaped() -> None:
    """A player called '<b>' must not be able to break the message."""
    text, _ = screens.home("Клуб", [fake_player("<b>Аня</b>")])
    assert "<b>Аня</b>" not in text.split("\n", 1)[1]
    assert "&lt;b&gt;" in text


# --------------------------------------------------------------------------- roster


def test_roster_hides_continue_until_the_count_works() -> None:
    roster = [fake_player(name) for name in NAMES]
    chosen = {roster[0].id, roster[1].id}

    _, markup = screens.roster_screen(roster, chosen, (4, 8))
    assert not any(press.arg == Screen.SETUP.value for press in actions(markup))

    _, markup = screens.roster_screen(roster, {p.id for p in roster[:4]}, (4, 8))
    assert any(press.arg == Screen.SETUP.value for press in actions(markup))


def test_roster_marks_who_is_in() -> None:
    roster = [fake_player(name) for name in NAMES[:3]]
    _, markup = screens.roster_screen(roster, {roster[1].id}, (4,))
    # Comparing prefixes rather than first characters: the empty box is an emoji plus a
    # variation selector, so it is two codepoints, not one.
    ticked = [label.startswith("✅") for label in labels(markup)[:3]]
    assert ticked == [False, True, False]


def test_roster_says_what_counts_are_allowed() -> None:
    text, _ = screens.roster_screen([], set(), (8, 12, 16))
    assert "8, 12, 16" in text


# --------------------------------------------------------------------------- setup


def test_setup_marks_the_current_choices() -> None:
    _, markup = screens.setup_screen(Format.AMERICANO, 24, PairingPattern.CROSSOVER, 7, 8)
    marked = [label for label in labels(markup) if label.startswith("• ")]
    assert "• Американо" in marked
    assert "• до 24" in marked


def test_americano_setup_hides_mexicano_only_options() -> None:
    """Pairing pattern and round count mean nothing for a fixed whist schedule."""
    _, markup = screens.setup_screen(Format.AMERICANO, 24, PairingPattern.CROSSOVER, 7, 8)
    names = {press.arg for press in actions(markup) if press.action is Action.SETTING}
    assert names == {"fmt", "pts"}


def test_mexicano_setup_offers_pattern_and_rounds() -> None:
    _, markup = screens.setup_screen(Format.MEXICANO, 24, PairingPattern.SPLIT, 5, 8)
    names = {press.arg for press in actions(markup) if press.action is Action.SETTING}
    assert names == {"fmt", "pts", "pat", "rnd"}


# --------------------------------------------------------------------------- round


async def test_round_offers_a_button_per_unplayed_court(session: AsyncSession) -> None:
    view = await make_tournament(session)
    _, markup = screens.round_screen(view)
    courts = {int(press.arg) for press in actions(markup) if press.action is Action.COURT}
    assert courts == {1, 2}


async def test_a_scored_court_loses_its_button(session: AsyncSession) -> None:
    view = await make_tournament(session)
    view = await record_score(session, view.id, round_no=1, court=1, score_a=14, score_b=10)

    text, markup = screens.round_screen(view)
    courts = {int(press.arg) for press in actions(markup) if press.action is Action.COURT}
    assert courts == {2}
    assert "14:10" in text


async def test_round_shows_the_target(session: AsyncSession) -> None:
    view = await make_tournament(session, points=32)
    text, _ = screens.round_screen(view)
    assert "до 32" in text


# --------------------------------------------------------------------------- scoring


async def test_winner_screen_names_both_pairs(session: AsyncSession) -> None:
    view = await make_tournament(session)
    rnd = view.rounds[0]
    text, markup = screens.winner_screen(view, rnd, court_no=1)

    sides = {press.arg for press in actions(markup) if press.action is Action.WINNER}
    assert sides == {"a", "b", "draw"}
    assert "Корт 1" in text


async def test_an_odd_target_has_no_draw_button(session: AsyncSession) -> None:
    """21 points cannot be split evenly, so a draw is arithmetically impossible."""
    view = await make_tournament(session, points=21)
    _, markup = screens.winner_screen(view, view.rounds[0], court_no=1)
    sides = {press.arg for press in actions(markup) if press.action is Action.WINNER}
    assert sides == {"a", "b"}


@pytest.mark.parametrize(("target", "lowest"), [(24, 13), (32, 17), (16, 9)])
async def test_points_grid_only_offers_winning_scores(
    session: AsyncSession, target: int, lowest: int
) -> None:
    """Below half the target you did not win, so the number has no business being there."""
    view = await make_tournament(session, points=target)
    _, markup = screens.points_screen(view, court_no=1)
    offered = sorted(int(press.arg) for press in actions(markup) if press.action is Action.POINTS)
    assert offered == list(range(lowest, target + 1))


# --------------------------------------------------------------------------- table


async def test_table_ranks_everyone(session: AsyncSession) -> None:
    view = await make_tournament(session)
    view = await play_round(session, view, 1)
    text, _ = screens.table_screen(view)
    for name in NAMES:
        assert name in text


async def test_a_live_table_offers_to_finish(session: AsyncSession) -> None:
    view = await make_tournament(session)
    _, markup = screens.table_screen(view)
    assert any(press.action is Action.CONFIRM for press in actions(markup))


async def test_a_finished_table_crowns_the_winner(session: AsyncSession) -> None:
    view = await make_tournament(session)
    view = await play_round(session, view, 1)
    view = await finish_tournament(session, view.id)

    text, markup = screens.table_screen(view)
    assert "Победитель" in text
    assert view.standings[0].name in text
    assert not any(press.action is Action.CONFIRM for press in actions(markup))


async def test_confirming_before_finishing_says_how_far_we_got(
    session: AsyncSession,
) -> None:
    view = await make_tournament(session)
    view = await play_round(session, view, 1)
    text, markup = screens.confirm_finish(view)
    assert "1 из 7" in text
    assert any(press.action is Action.FINISH for press in actions(markup))


# --------------------------------------------------------------------------- chart


async def test_the_caption_names_the_podium_and_nobody_else(session: AsyncSession) -> None:
    """A caption is capped at 1024 characters. Showing three and pointing at the full table
    works for eight players and for twenty-four; showing all of them works for one of those
    and truncates silently for the other."""
    view = await make_tournament(session)
    view = await play_round(session, view, 1)

    text, _ = screens.chart_caption(view)

    named = [row.name for row in view.standings if row.name in text]
    assert len(named) == screens.PODIUM
    assert [row.name for row in view.standings[: screens.PODIUM]] == named


async def test_the_caption_offers_the_interactive_chart(session: AsyncSession) -> None:
    """The PNG is a preview. The page behind this button is the one you can poke at.

    With no Mini App configured the link is the plain site — which still works, it just
    opens in the in-app browser instead of inside Telegram.
    """
    view = await make_tournament(session)
    view = await play_round(session, view, 1)

    _, markup = screens.chart_caption(view)

    links = [button.url for row in markup.inline_keyboard for button in row if button.url]
    assert links == [f"http://localhost:5173/t/{view.id}"]


async def test_the_caption_opens_telegram_when_a_mini_app_is_configured(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A direct link, because a web_app button is private-chat only and this bot lives in
    groups. The direct kind opens the app full-screen from a group too — and needs only the
    username, since a Main Mini App has no short name."""
    monkeypatch.setenv("BOT_USERNAME", "padeltourbot")
    view = await make_tournament(session)
    view = await play_round(session, view, 1)

    _, markup = screens.chart_caption(view)

    links = [button.url for row in markup.inline_keyboard for button in row if button.url]
    assert links == [f"https://t.me/padeltourbot?startapp=t_{view.id}"]


# --------------------------------------------------------------------------- history


def test_empty_history_says_so() -> None:
    text, _ = screens.history_screen([])
    assert "Пока ни одного" in text


async def test_history_lists_the_winner(session: AsyncSession) -> None:
    view = await make_tournament(session)
    view = await play_round(session, view, 1)
    await finish_tournament(session, view.id)

    entries = await list_tournaments(session, view.group_id)
    text, _ = screens.history_screen(entries)
    assert view.standings[0].name in text


async def test_history_marks_a_running_tournament(session: AsyncSession) -> None:
    view = await make_tournament(session)
    entries = await list_tournaments(session, view.group_id)
    text, _ = screens.history_screen(entries)
    assert "идёт" in text


# --------------------------------------------------------------------------- draw


async def test_americano_draw_shows_every_round(session: AsyncSession) -> None:
    view = await make_tournament(session)
    text, markup = screens.draw_screen(view)
    for number in range(1, 8):
        assert f"Раунд {number}" in text
    assert any(press.action is Action.REROLL for press in actions(markup))


async def test_mexicano_draw_shows_only_the_first_round(session: AsyncSession) -> None:
    view = await make_tournament(session, fmt=Format.MEXICANO, rounds=3)
    text, _ = screens.draw_screen(view)
    assert "Раундов: 3" in text
    assert "Корт 1" in text


async def test_every_screen_uses_real_player_names(session: AsyncSession) -> None:
    """Ids must never leak into anything a person reads."""
    view = await make_tournament(session)
    roster = await list_players(session, view.group_id)
    view = await play_round(session, view, 1)

    rendered = [
        screens.round_screen(view),
        screens.table_screen(view),
        screens.chart_caption(view),
        screens.draw_screen(view),
        screens.roster_screen(roster, set(), (8,)),
    ]
    for text, _ in rendered:
        assert str(view.id) not in text
        assert "UUID" not in text


# --------------------------------------------------------------------------- the ending


async def test_no_screen_uses_a_code_block(session: AsyncSession) -> None:
    """``<pre>`` looked like a neat monospaced table and was neither.

    Telegram renders it as a code listing with a copy header bolted on — nobody wants their
    standings on the clipboard — and it wraps once a line passes the chat width, which
    folded every row of an eight-player table in half on a phone. Inline ``<code>`` is
    monospaced without any of that, which is why the table is built out of it.
    """
    view = await make_tournament(session)
    view = await play_round(session, view, 1)
    roster = await list_players(session, view.group_id)

    rendered = [
        screens.round_screen(view),
        screens.table_screen(view),
        screens.finish_screen(view),
        screens.draw_screen(view),
        screens.roster_screen(roster, set(), (8,)),
        screens.home("Вторничный падел", roster),
    ]

    for text, _ in rendered:
        assert "<pre>" not in text


async def test_the_ending_names_everybody_not_just_the_winner(session: AsyncSession) -> None:
    """Seven of the eight also turned up and played every round."""
    view = await make_tournament(session)
    view = await play_round(session, view, 1)

    text, _ = screens.finish_screen(view)

    for row in view.standings:
        assert row.name in text


async def test_the_ending_says_who_won_before_it_says_anything_else(
    session: AsyncSession,
) -> None:
    """A tournament that stops by greying out its buttons is an anticlimax."""
    view = await make_tournament(session)
    view = await play_round(session, view, 1)

    text, _ = screens.finish_screen(view)

    assert "Победитель" in text
    assert text.index(view.standings[0].name) < text.index(view.standings[-1].name)


# --------------------------------------------------------------------------- history


def test_history_names_the_podium_rather_than_only_the_winner() -> None:
    """A line about eight people used to be a line about one of them."""
    entry = TournamentSummary(
        id=uuid.uuid4(),
        group_id=uuid.uuid4(),
        format=Format.AMERICANO,
        finished=True,
        player_count=8,
        rounds_played=7,
        total_rounds=7,
        created_at=datetime(2026, 8, 9, tzinfo=UTC),
        finished_at=datetime(2026, 8, 9, tzinfo=UTC),
        winner_name="Корней",
        placings=("Корней", "Кеша", "Дима", "Артем", "Коля", "Рада", "Витя", "Кирилл"),
    )

    text, _ = screens.history_screen([entry])

    assert "Корней" in text
    assert "Кеша" in text
    assert "Дима" in text
    # The rest are counted rather than listed — eight names per line is a wall, and none
    # of them is left out of the count.
    assert "и ещё 5" in text


async def test_the_table_lines_up(session: AsyncSession) -> None:
    """A table whose numbers do not stack is a table you cannot read down.

    Every row is one monospaced span of the same width, so the columns land on the same
    character in each. The medal sits outside the span: an emoji is double-width, and one
    in the middle of a monospaced row throws every column after it out by a character.
    """
    view = await make_tournament(session)
    view = await play_round(session, view, 1)

    text, _ = screens.table_screen(view)

    rows = [line for line in text.splitlines() if line.startswith("<code>")]
    assert len(rows) == len(view.standings) + 1  # the header shares the grid
    widths = {len(line.partition("<code>")[2].partition("</code>")[0]) for line in rows}
    assert len(widths) == 1, f"columns do not line up: {widths}"


async def test_a_long_name_is_cut_rather_than_allowed_to_shove_the_columns(
    session: AsyncSession,
) -> None:
    """Otherwise one long name widens its row and nothing below it lines up again."""
    group = await create_group(session, "Клуб")
    long_name = "Александра-Валентина"
    players = [(await add_player(session, group.id, name)).id for name in (long_name, *NAMES[:3])]
    view = await start_tournament(
        session, group.id, players, TournamentConfig(Format.AMERICANO, points_per_match=24), seed=1
    )

    text, _ = screens.table_screen(view)

    rows = [line for line in text.splitlines() if line.startswith("<code>")]
    widths = {len(line.partition("<code>")[2].partition("</code>")[0]) for line in rows}
    assert len(widths) == 1
    assert long_name not in text
