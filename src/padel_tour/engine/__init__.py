"""Padel tournament engine.

A pure library: no database, no HTTP, no global randomness. Every operation takes a
:class:`TournamentState` and returns a new one, and every random choice comes from the seed
stored on the state — so a tournament can always be replayed exactly.

Typical Americano::

    config = TournamentConfig(Format.AMERICANO, points_per_match=24)
    state = create_americano(players, config, seed=42)
    state = record_result(state, round_no=1, court=1, score_a=14, score_b=10)
    table = standings(state)

Typical Mexicano — same, but rounds arrive one at a time::

    config = TournamentConfig(Format.MEXICANO, points_per_match=24, rounds=7)
    state = create_mexicano(players, config, seed=42)
    ...record every court of round 1...
    state = next_round(state)
"""

from .americano import create_americano
from .errors import (
    DuplicatePlayerError,
    InvalidConfigError,
    InvalidPlayerCountError,
    InvalidScoreError,
    NoMoreRoundsError,
    PadelEngineError,
    RerollTooLateError,
    ResultAlreadyRecordedError,
    RoundIncompleteError,
    TournamentFinishedError,
    UnknownMatchError,
    UnsupportedPlayerCountError,
    WrongFormatError,
)
from .mexicano import create_mexicano, next_round
from .models import (
    COMMON_POINT_TARGETS,
    Format,
    Match,
    MatchResult,
    PairingPattern,
    PlayerId,
    ProgressPoint,
    Round,
    StandingRow,
    Team,
    TournamentConfig,
    TournamentState,
)
from .standings import progression, ranked_players, standings
from .tournament import (
    amend_result,
    finish,
    is_played_out,
    pending_matches,
    record_result,
    reroll,
)
from .whist import supported_player_counts

__all__ = [
    "COMMON_POINT_TARGETS",
    "DuplicatePlayerError",
    "Format",
    "InvalidConfigError",
    "InvalidPlayerCountError",
    "InvalidScoreError",
    "Match",
    "MatchResult",
    "NoMoreRoundsError",
    "PadelEngineError",
    "PairingPattern",
    "PlayerId",
    "ProgressPoint",
    "RerollTooLateError",
    "ResultAlreadyRecordedError",
    "Round",
    "RoundIncompleteError",
    "StandingRow",
    "Team",
    "TournamentConfig",
    "TournamentFinishedError",
    "TournamentState",
    "UnknownMatchError",
    "UnsupportedPlayerCountError",
    "WrongFormatError",
    "amend_result",
    "create_americano",
    "create_mexicano",
    "finish",
    "is_played_out",
    "next_round",
    "pending_matches",
    "progression",
    "ranked_players",
    "record_result",
    "reroll",
    "standings",
    "supported_player_counts",
]
