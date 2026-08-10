"""What a button press carries.

``callback_data`` encodes the whole action, so the server never has to remember which screen
a user is looking at. That matters in a group chat: several people press buttons on the same
message, and any of them may be working from a screen that has since been redrawn.

Telegram caps callback data at 64 bytes, which is why the prefixes are terse and player ids
travel as bare hex rather than dashed UUIDs.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum

#: Telegram's hard limit on callback_data.
MAX_CALLBACK_BYTES = 64

_SEPARATOR = ":"


class Screen(StrEnum):
    """A screen the user can navigate to. No side effects — just what to draw."""

    HOME = "home"
    #: The group's roster, where people are added and removed.
    SQUAD = "squad"
    #: Who plays in the tournament being assembled.
    ROSTER = "roster"
    SETUP = "setup"
    DRAW = "draw"
    ROUND = "round"
    TABLE = "table"
    CHART = "chart"
    HISTORY = "history"


class Action(StrEnum):
    """Everything a press can mean."""

    #: Go to a screen: ``scr:table``
    SHOW = "scr"
    #: Toggle a player in the roster being assembled: ``tog:<hex>``
    TOGGLE = "tog"
    #: Take somebody off the group's roster: ``del:<hex>``
    DROP = "del"
    #: Change a setup option: ``set:points:24``
    SETTING = "set"
    #: Redraw the schedule before play starts.
    REROLL = "rr"
    #: Confirm the draw and begin.
    BEGIN = "go"
    #: Enter a score for a court: ``crt:2``
    COURT = "crt"
    #: Which side won: ``won:a`` / ``won:b`` / ``won:draw``
    WINNER = "won"
    #: The winner's score: ``pts:17``
    POINTS = "pts"
    #: Draw the next Mexicano round.
    ADVANCE = "next"
    #: Plan one more round than was agreed at the start.
    EXTEND = "more"
    #: End the tournament where it stands.
    FINISH = "fin"
    #: Ask before something irreversible: ``ask:fin``
    CONFIRM = "ask"
    #: Back out of a partially entered score.
    CANCEL = "esc"


@dataclass(frozen=True, slots=True)
class Callback:
    """A parsed button press: an action and up to two arguments."""

    action: Action
    arg: str = ""
    extra: str = ""

    def pack(self) -> str:
        parts = [self.action.value]
        if self.arg or self.extra:
            parts.append(self.arg)
        if self.extra:
            parts.append(self.extra)
        packed = _SEPARATOR.join(parts)
        if len(packed.encode()) > MAX_CALLBACK_BYTES:
            raise ValueError(f"callback data too long for Telegram: {packed!r}")
        return packed

    @classmethod
    def parse(cls, raw: str) -> Callback | None:
        """Decode a press, or ``None`` if it is not ours.

        Unknown data is not an error worth raising: an old message from a previous version
        of the bot can still be sitting in a chat, and pressing it should do nothing rather
        than crash a handler.
        """
        head, _, rest = raw.partition(_SEPARATOR)
        try:
            action = Action(head)
        except ValueError:
            return None
        arg, _, extra = rest.partition(_SEPARATOR)
        return cls(action=action, arg=arg, extra=extra)


def show(screen: Screen) -> str:
    return Callback(Action.SHOW, screen.value).pack()


def toggle(player_id: uuid.UUID) -> str:
    return Callback(Action.TOGGLE, player_id.hex).pack()


def drop(player_id: uuid.UUID) -> str:
    return Callback(Action.DROP, player_id.hex).pack()


def setting(name: str, value: str) -> str:
    return Callback(Action.SETTING, name, value).pack()


def court(number: int) -> str:
    return Callback(Action.COURT, str(number)).pack()


def winner(side: str) -> str:
    return Callback(Action.WINNER, side).pack()


def points(value: int) -> str:
    return Callback(Action.POINTS, str(value)).pack()


def plain(action: Action) -> str:
    return Callback(action).pack()


def confirm(action: Action) -> str:
    """Ask before doing something that cannot be taken back."""
    return Callback(Action.CONFIRM, action.value).pack()


def parse_player_id(arg: str) -> uuid.UUID | None:
    """Read a player id back out of callback data."""
    try:
        return uuid.UUID(hex=arg)
    except ValueError:
        return None


def parse_number(arg: str) -> int | None:
    """Read a numeric argument back out of callback data.

    Same contract as :func:`parse_player_id`, and for the same reason. Every button that
    carries a number puts one there, so anything else did not come from a keyboard we drew.
    Bare ``int()`` would raise ``ValueError``, which no handler catches and nothing above
    them turns into a reply — under a webhook that is a 500 for a press that should simply
    do nothing.
    """
    try:
        return int(arg)
    except ValueError:
        return None
