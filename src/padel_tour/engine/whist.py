"""Whist tournament designs — the schedule behind an Americano.

An Americano played to completion is exactly a *whist tournament design* Wh(n): over n−1
rounds every pair of players partners exactly once and opposes exactly twice. Such designs
exist for every n divisible by four.

Rather than storing a table per player count, we store a single **starter** — the first
round, laid out over ``Z_{n-1} ∪ {∞}`` — and obtain the remaining n−2 rounds by adding one
modulo n−1 to every finite element, leaving ∞ in place.

A starter is valid exactly when:

1. it uses every element of ``Z_{n-1} ∪ {∞}`` once;
2. the differences of its finite *partner* pairs cover each difference class once;
3. the differences of its finite *opponent* pairs cover each difference class twice.

Pairs involving ∞ take care of themselves: ∞ partners ``a + j`` across all rounds (each pair
once) and opposes ``c + j`` and ``d + j`` (each pair twice).

The starters below were found by :func:`search_starter` and are re-validated by the test
suite for every supported player count, so a typo cannot ship.
"""

from __future__ import annotations

from collections import Counter
from itertools import combinations

from .errors import InvalidPlayerCountError, UnsupportedPlayerCountError
from .models import PLAYERS_PER_COURT

#: The two properties that define a whist design.
PARTNERSHIPS_PER_PAIR = 1
OPPOSITIONS_PER_PAIR = 2

#: A position in the design. Non-negative values are elements of ``Z_{n-1}``; ``INF`` is the
#: fixed point that does not rotate.
Slot = int

INF: Slot = -1

SlotPair = tuple[Slot, Slot]
SlotGame = tuple[SlotPair, SlotPair]
SlotRound = tuple[SlotGame, ...]
Starter = SlotRound
Design = tuple[SlotRound, ...]


STARTERS: dict[int, Starter] = {
    4: (((INF, 0), (1, 2)),),
    8: (((INF, 0), (1, 3)), ((2, 6), (4, 5))),
    12: (((INF, 0), (1, 3)), ((2, 9), (6, 7)), ((4, 10), (5, 8))),
    16: (
        ((INF, 0), (1, 2)),
        ((3, 6), (9, 11)),
        ((4, 13), (8, 12)),
        ((5, 10), (7, 14)),
    ),
    20: (
        ((INF, 0), (1, 2)),
        ((3, 5), (9, 15)),
        ((4, 14), (12, 17)),
        ((6, 18), (10, 13)),
        ((7, 11), (8, 16)),
    ),
    24: (
        ((INF, 0), (1, 2)),
        ((3, 14), (4, 7)),
        ((5, 20), (12, 17)),
        ((6, 15), (11, 21)),
        ((8, 10), (13, 19)),
        ((9, 16), (18, 22)),
    ),
}


def supported_player_counts() -> tuple[int, ...]:
    """Player counts the engine can build an Americano schedule for."""
    return tuple(sorted(STARTERS))


def require_supported_player_count(count: int) -> None:
    """Raise unless ``count`` is a player count we can schedule.

    Two distinct failures: a count that is not a multiple of four is a user mistake with an
    obvious fix, while a supported-shape-but-unknown count is an engine limitation.
    """
    options = ", ".join(str(value) for value in supported_player_counts())
    if count < PLAYERS_PER_COURT or count % PLAYERS_PER_COURT != 0:
        raise InvalidPlayerCountError(
            f"player count must be a multiple of {PLAYERS_PER_COURT} ({options}) — got {count}"
        )
    if count not in STARTERS:
        raise UnsupportedPlayerCountError(
            f"a schedule is known for {options} players — {count} is not supported yet"
        )


def slots_for(count: int) -> tuple[Slot, ...]:
    """Canonical slot order for ``count`` players: ∞ first, then ``0 .. count-2``."""
    return (INF, *range(count - 1))


def shift_slot(slot: Slot, by: int, modulus: int) -> Slot:
    """Rotate a slot by ``by``. ``INF`` is the fixed point."""
    return INF if slot == INF else (slot + by) % modulus


def generate_from_starter(starter: Starter, count: int) -> Design:
    """Expand a starter into the full ``count - 1`` round design."""
    modulus = count - 1
    return tuple(
        tuple(
            (
                (shift_slot(a, step, modulus), shift_slot(b, step, modulus)),
                (shift_slot(c, step, modulus), shift_slot(d, step, modulus)),
            )
            for (a, b), (c, d) in starter
        )
        for step in range(modulus)
    )


def whist_design(count: int) -> Design:
    """The full Americano schedule, in slots, for ``count`` players."""
    require_supported_player_count(count)
    return generate_from_starter(STARTERS[count], count)


def _tally_pairs(design: Design) -> tuple[Counter[frozenset[Slot]], Counter[frozenset[Slot]]]:
    """Count how often each pair of slots partners and how often it opposes."""
    partners: Counter[frozenset[Slot]] = Counter()
    opponents: Counter[frozenset[Slot]] = Counter()
    for rnd in design:
        for team_a, team_b in rnd:
            partners[frozenset(team_a)] += 1
            partners[frozenset(team_b)] += 1
            for left in team_a:
                for right in team_b:
                    opponents[frozenset((left, right))] += 1
    return partners, opponents


def design_defects(design: Design, count: int) -> list[str]:
    """Every way ``design`` fails to be a whist design. Empty list means valid.

    Returning the reasons rather than a bare bool is what makes a failing test useful.
    """
    defects: list[str] = []
    expected_slots = sorted(slots_for(count))
    expected_courts = count // PLAYERS_PER_COURT

    if len(design) != count - 1:
        defects.append(f"{len(design)} rounds, expected {count - 1}")

    for index, rnd in enumerate(design, start=1):
        if len(rnd) != expected_courts:
            defects.append(f"round {index}: {len(rnd)} games, expected {expected_courts}")
        appearing = sorted(slot for game in rnd for pair in game for slot in pair)
        if appearing != expected_slots:
            defects.append(f"round {index}: every player must appear exactly once")

    partners, opponents = _tally_pairs(design)
    for left, right in combinations(expected_slots, 2):
        pair = frozenset((left, right))
        if partners[pair] != PARTNERSHIPS_PER_PAIR:
            defects.append(
                f"{left}&{right} partner {partners[pair]} times, expected {PARTNERSHIPS_PER_PAIR}"
            )
        if opponents[pair] != OPPOSITIONS_PER_PAIR:
            defects.append(
                f"{left}&{right} oppose {opponents[pair]} times, expected {OPPOSITIONS_PER_PAIR}"
            )

    return defects


def is_valid_whist_design(design: Design, count: int) -> bool:
    """True when every pair partners once and opposes twice across the design."""
    return not design_defects(design, count)


#: One applied difference: ``(is_partner, difference class)``. Enough to undo a placement.
_Applied = list[tuple[bool, int]]


class _DifferenceLedger:
    """Tracks how many times each difference class has been spent, and enforces the limits.

    A game can be placed only if it keeps every partner class at one use and every opponent
    class at two. Placement is all-or-nothing: on conflict the ledger rolls itself back.
    """

    def __init__(self, modulus: int) -> None:
        self._modulus = modulus
        classes = modulus // 2 + 1
        self._partner = [0] * classes
        self._opponent = [0] * classes

    def _class_of(self, left: Slot, right: Slot) -> int:
        delta = (left - right) % self._modulus
        return min(delta, self._modulus - delta)

    def place(self, game: SlotGame) -> _Applied | None:
        """Spend a game's differences, or roll back and return ``None`` on a conflict."""
        applied: _Applied = []
        for left, right in game:
            if INF in (left, right):
                continue
            cls = self._class_of(left, right)
            if self._partner[cls] >= PARTNERSHIPS_PER_PAIR:
                self.undo(applied)
                return None
            self._partner[cls] += 1
            applied.append((True, cls))
        for left in game[0]:
            for right in game[1]:
                if INF in (left, right):
                    continue
                cls = self._class_of(left, right)
                if self._opponent[cls] >= OPPOSITIONS_PER_PAIR:
                    self.undo(applied)
                    return None
                self._opponent[cls] += 1
                applied.append((False, cls))
        return applied

    def undo(self, applied: _Applied) -> None:
        for is_partner, cls in applied:
            if is_partner:
                self._partner[cls] -= 1
            else:
                self._opponent[cls] -= 1


def _extend_starter(
    remaining: tuple[Slot, ...], games: list[SlotGame], ledger: _DifferenceLedger
) -> Starter | None:
    """Fill the remaining slots into games, backtracking on conflict.

    Every game must contain the smallest still-unused slot, which removes permutations of
    otherwise identical partitions from the search.
    """
    if not remaining:
        return tuple(games)

    head, *rest = remaining
    pool = tuple(rest)
    for trio in combinations(pool, 3):
        for partner_index in range(3):
            partner = trio[partner_index]
            others = tuple(value for i, value in enumerate(trio) if i != partner_index)
            game: SlotGame = ((head, partner), (others[0], others[1]))
            applied = ledger.place(game)
            if applied is None:
                continue
            games.append(game)
            found = _extend_starter(tuple(v for v in pool if v not in trio), games, ledger)
            if found is not None:
                return found
            games.pop()
            ledger.undo(applied)
    return None


def search_starter(count: int) -> Starter | None:
    """Search for a Z-cyclic starter for ``count`` players.

    Used offline to populate :data:`STARTERS`; kept in the package so a starter can always be
    recomputed rather than trusted. Returns ``None`` if no Z-cyclic starter exists.

    The whole starter can be translated freely, so ∞'s partner is pinned to ``0``.

    Enforcing the per-class limits locally is enough to guarantee a valid design: the game
    count makes the number of finite partner pairs exactly equal to the number of difference
    classes, and the number of finite opponent pairs exactly twice that. Filling every game
    without exceeding a limit therefore means hitting every limit exactly.
    """
    if count < PLAYERS_PER_COURT or count % PLAYERS_PER_COURT != 0:
        return None

    modulus = count - 1
    ledger = _DifferenceLedger(modulus)

    for left, right in combinations(range(1, modulus), 2):
        opening: SlotGame = ((INF, 0), (left, right))
        applied = ledger.place(opening)
        if applied is None:
            continue
        rest = tuple(value for value in range(1, modulus) if value not in (left, right))
        found = _extend_starter(rest, [opening], ledger)
        if found is not None:
            return found
        ledger.undo(applied)

    return None
