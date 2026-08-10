"""Operations that apply to a tournament regardless of format.

Every function takes a state and returns a new one; nothing is mutated in place.
"""

from __future__ import annotations

from dataclasses import replace
from random import Random

from .americano import create_americano
from .errors import (
    InvalidConfigError,
    InvalidScoreError,
    RerollTooLateError,
    ResultAlreadyRecordedError,
    TournamentFinishedError,
    UnknownMatchError,
    WrongFormatError,
)
from .mexicano import create_mexicano
from .models import Format, Match, MatchResult, Round, TournamentState

_SEED_SPACE = 2**63


def _derive_seed(seed: int) -> int:
    """Next seed in a deterministic chain, so repeated rerolls stay reproducible."""
    return Random(seed).randrange(_SEED_SPACE)


def reroll(state: TournamentState, *, seed: int | None = None) -> TournamentState:
    """Redraw the tournament from scratch with the same players and settings.

    In an Americano this reseats everyone on the same whist design, producing entirely
    different pairs while keeping the schedule perfectly balanced. In a Mexicano it
    reshuffles the opening round.

    Only allowed before the first result: once a match has been scored, the draw is history.
    """
    if state.finished:
        raise TournamentFinishedError("the tournament is over — nothing left to redraw")
    if state.started:
        raise RerollTooLateError("results have been recorded — the draw can no longer be changed")

    new_seed = seed if seed is not None else _derive_seed(state.seed)
    if state.config.format is Format.AMERICANO:
        return create_americano(state.players, state.config, new_seed)
    return create_mexicano(state.players, state.config, new_seed)


def _validate_score(state: TournamentState, score_a: int, score_b: int) -> None:
    target = state.config.points_per_match
    if score_a < 0 or score_b < 0:
        raise InvalidScoreError(f"scores cannot be negative: {score_a}:{score_b}")
    if score_a + score_b != target:
        raise InvalidScoreError(
            f"the match runs to {target} points, so the scores must add up to {target} — "
            f"got {score_a}+{score_b}={score_a + score_b}"
        )


def _locate(state: TournamentState, round_no: int, court: int) -> tuple[Round, Match]:
    rnd = state.round_by_number(round_no)
    if rnd is None:
        raise UnknownMatchError(f"round {round_no} has not been drawn yet")
    for match in rnd.matches:
        if match.court == court:
            return rnd, match
    raise UnknownMatchError(f"round {round_no} has no court {court}")


def _with_result(
    state: TournamentState, round_no: int, court: int, result: MatchResult
) -> TournamentState:
    rnd, _ = _locate(state, round_no, court)
    updated = replace(
        rnd,
        matches=tuple(
            replace(match, result=result) if match.court == court else match
            for match in rnd.matches
        ),
    )
    rounds = tuple(updated if r.number == round_no else r for r in state.rounds)
    return replace(state, rounds=rounds)


def record_result(
    state: TournamentState, round_no: int, court: int, score_a: int, score_b: int
) -> TournamentState:
    """Score a match. Auto-finishes the tournament once the last round is complete."""
    if state.finished:
        raise TournamentFinishedError("the tournament is over — no more results accepted")

    _validate_score(state, score_a, score_b)
    _, match = _locate(state, round_no, court)
    if match.result is not None:
        raise ResultAlreadyRecordedError(
            f"round {round_no} court {court} already scored "
            f"({match.result.score_a}:{match.result.score_b}) — use amend_result"
        )

    updated = _with_result(state, round_no, court, MatchResult(score_a, score_b))
    return replace(updated, finished=True) if is_played_out(updated) else updated


def amend_result(
    state: TournamentState, round_no: int, court: int, score_a: int, score_b: int
) -> TournamentState:
    """Correct a score that was entered wrong.

    Standings and the progression chart recompute from the new score. Mexicano rounds that
    were already drawn are left alone — those matches were physically played, and a typo
    does not undo them.
    """
    _validate_score(state, score_a, score_b)
    _locate(state, round_no, court)
    return _with_result(state, round_no, court, MatchResult(score_a, score_b))


def is_played_out(state: TournamentState) -> bool:
    """True when the tournament has run its course and should end by itself.

    Only an Americano does. Its ``n - 1`` rounds are the format — every pair partners once,
    and there is no such thing as an extra round without repeating a partnership. A
    Mexicano's round count is the organiser's plan, not a rule, so reaching it means the
    plan is done, not the padel: they may well want one more, and a tournament that closed
    itself the instant the last score went in would have taken that decision away at exactly
    the wrong moment.
    """
    if state.config.format is not Format.AMERICANO:
        return False
    return len(state.rounds) >= state.total_rounds and all(rnd.complete for rnd in state.rounds)


def extend(state: TournamentState, by: int = 1) -> TournamentState:
    """Plan another round.

    Mexicano only, and not because of a missing feature: an Americano plays a whist design
    in which every pair partners exactly once over ``n - 1`` rounds. A twelfth round for
    eleven would have to repeat a partnership, which is the one thing the format promises
    not to do.
    """
    if state.config.format is not Format.MEXICANO:
        raise WrongFormatError("an Americano plays a fixed n-1 rounds; there is no extra one")
    if state.finished:
        raise TournamentFinishedError("the tournament is over — no more rounds")
    if by < 1:
        raise InvalidConfigError(f"a tournament grows by at least one round, got {by}")
    return replace(state, total_rounds=state.total_rounds + by)


def finish(state: TournamentState) -> TournamentState:
    """End the tournament, whatever round it is on.

    A full Americano on twelve players is eleven rounds — roughly two and a half hours — so
    stopping early has to be a normal thing to do, not a failure. The standing at that point
    is final.
    """
    return replace(state, finished=True)


def pending_matches(state: TournamentState) -> tuple[tuple[int, Match], ...]:
    """Every unscored match as ``(round number, match)``, in playing order."""
    return tuple(
        (rnd.number, match) for rnd in state.rounds for match in rnd.matches if not match.played
    )
