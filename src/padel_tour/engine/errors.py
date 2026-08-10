"""Exception hierarchy for the tournament engine.

Every failure the engine can produce is a subclass of :class:`PadelEngineError`, so a
caller (bot, API, CLI) can catch that one type and show the message to a human.
"""

from __future__ import annotations

from padel_tour.faults import CodedError


class PadelEngineError(CodedError):
    """Base class for every error the engine raises.

    :class:`~padel_tour.faults.CodedError` is a plain helper with no dependencies of its own, so
    the engine stays what it is: rules and nothing else.
    """


class InvalidConfigError(PadelEngineError):
    """Tournament configuration is self-contradictory or out of range."""


class InvalidPlayerCountError(PadelEngineError):
    """Player count is not a multiple of four."""


class UnsupportedPlayerCountError(PadelEngineError):
    """Player count is a valid multiple of four but no schedule is known for it."""


class DuplicatePlayerError(PadelEngineError):
    """The same player id appears twice in the roster."""


class UnknownMatchError(PadelEngineError):
    """No match exists at the requested round/court."""


class InvalidScoreError(PadelEngineError):
    """Score does not add up to the configured points per match."""


class ResultAlreadyRecordedError(PadelEngineError):
    """That match already has a result."""


class RoundIncompleteError(PadelEngineError):
    """The current round still has matches without results."""


class RerollTooLateError(PadelEngineError):
    """Rerolling is only allowed before the first result is recorded."""


class TournamentFinishedError(PadelEngineError):
    """The tournament is over and no longer accepts changes."""


class NoMoreRoundsError(PadelEngineError):
    """Every planned round has already been generated."""


class WrongFormatError(PadelEngineError):
    """The operation does not apply to this tournament format."""
