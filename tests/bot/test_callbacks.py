"""Callback data is the bot's whole protocol, and Telegram gives it 64 bytes."""

from __future__ import annotations

import uuid

import pytest

from padel_tour.bot.callbacks import (
    MAX_CALLBACK_BYTES,
    Action,
    Callback,
    Screen,
    confirm,
    court,
    parse_player_id,
    plain,
    points,
    setting,
    show,
    toggle,
    winner,
)


@pytest.mark.parametrize(
    "original",
    [
        Callback(Action.SHOW, "table"),
        Callback(Action.COURT, "3"),
        Callback(Action.SETTING, "pts", "24"),
        Callback(Action.REROLL),
        Callback(Action.WINNER, "draw"),
    ],
)
def test_pack_then_parse_round_trips(original: Callback) -> None:
    assert Callback.parse(original.pack()) == original


def test_unknown_data_is_ignored_not_raised() -> None:
    """Old messages from a previous version are still sitting in chats."""
    assert Callback.parse("whatever:1") is None
    assert Callback.parse("") is None


def test_every_builder_fits_telegrams_limit() -> None:
    longest = [
        show(Screen.HISTORY),
        toggle(uuid.uuid7()),
        setting("pat", "top_heavy"),
        court(99),
        winner("draw"),
        points(32),
        plain(Action.ADVANCE),
        confirm(Action.FINISH),
    ]
    for data in longest:
        assert len(data.encode()) <= MAX_CALLBACK_BYTES, data


def test_over_long_data_is_refused_at_build_time() -> None:
    """Better to fail here than to have Telegram silently drop the button."""
    with pytest.raises(ValueError, match="too long"):
        Callback(Action.SHOW, "x" * MAX_CALLBACK_BYTES).pack()


def test_player_ids_survive_the_trip() -> None:
    player_id = uuid.uuid7()
    parsed = Callback.parse(toggle(player_id))
    assert parsed is not None
    assert parse_player_id(parsed.arg) == player_id


def test_a_mangled_player_id_is_none_not_an_exception() -> None:
    assert parse_player_id("nonsense") is None


def test_screen_names_are_stable() -> None:
    """These strings live inside messages in real chats; renaming one breaks old buttons."""
    assert {screen.value for screen in Screen} == {
        "home",
        "roster",
        "setup",
        "draw",
        "round",
        "table",
        "chart",
        "history",
    }
