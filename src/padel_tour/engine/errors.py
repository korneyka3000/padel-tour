"""Exception hierarchy for the tournament engine.

Every failure the engine can produce is a subclass of :class:`PadelEngineError`, so a
caller (bot, API, CLI) can catch that one type and show the message to a human.
"""

from __future__ import annotations


class PadelEngineError(Exception):
    """Base class for every error the engine raises."""


class InvalidConfig(PadelEngineError):
    """Tournament configuration is self-contradictory or out of range."""


class InvalidPlayerCount(PadelEngineError):
    """Player count is not a multiple of four."""


class UnsupportedPlayerCount(PadelEngineError):
    """Player count is a valid multiple of four but no schedule is known for it."""


class DuplicatePlayer(PadelEngineError):
    """The same player id appears twice in the roster."""


class UnknownMatch(PadelEngineError):
    """No match exists at the requested round/court."""


class InvalidScore(PadelEngineError):
    """Score does not add up to the configured points per match."""


class ResultAlreadyRecorded(PadelEngineError):
    """That match already has a result."""


class RoundIncomplete(PadelEngineError):
    """The current round still has matches without results."""


class CannotRerollAfterStart(PadelEngineError):
    """Rerolling is only allowed before the first result is recorded."""


class TournamentFinished(PadelEngineError):
    """The tournament is over and no longer accepts changes."""


class NoMoreRounds(PadelEngineError):
    """Every planned round has already been generated."""


class WrongFormat(PadelEngineError):
    """The operation does not apply to this tournament format."""
