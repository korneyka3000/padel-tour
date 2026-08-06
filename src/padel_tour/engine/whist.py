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

from .errors import InvalidPlayerCount, UnsupportedPlayerCount

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
    if count < 4 or count % 4 != 0:
        raise InvalidPlayerCount(f"player count must be a multiple of 4 ({options}) — got {count}")
    if count not in STARTERS:
        raise UnsupportedPlayerCount(
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


def design_defects(design: Design, count: int) -> list[str]:
    """Every way ``design`` fails to be a whist design. Empty list means valid.

    Returning the reasons rather than a bare bool is what makes a failing test useful.
    """
    defects: list[str] = []
    expected_slots = set(slots_for(count))
    expected_courts = count // 4

    if len(design) != count - 1:
        defects.append(f"{len(design)} rounds, expected {count - 1}")

    partners: Counter[frozenset[Slot]] = Counter()
    opponents: Counter[frozenset[Slot]] = Counter()

    for index, rnd in enumerate(design, start=1):
        if len(rnd) != expected_courts:
            defects.append(f"round {index}: {len(rnd)} games, expected {expected_courts}")
        appearances: Counter[Slot] = Counter()
        for team_a, team_b in rnd:
            partners[frozenset(team_a)] += 1
            partners[frozenset(team_b)] += 1
            for left in team_a:
                for right in team_b:
                    opponents[frozenset((left, right))] += 1
            appearances.update(team_a)
            appearances.update(team_b)
        if set(appearances) != expected_slots or any(v != 1 for v in appearances.values()):
            defects.append(f"round {index}: every player must appear exactly once")

    for left, right in combinations(sorted(expected_slots), 2):
        pair = frozenset((left, right))
        if partners[pair] != 1:
            defects.append(f"{left}&{right} partner {partners[pair]} times, expected 1")
        if opponents[pair] != 2:
            defects.append(f"{left}&{right} oppose {opponents[pair]} times, expected 2")

    return defects


def is_valid_whist_design(design: Design, count: int) -> bool:
    """True when every pair partners once and opposes twice across the design."""
    return not design_defects(design, count)


def search_starter(count: int) -> Starter | None:
    """Search for a Z-cyclic starter for ``count`` players.

    Used offline to populate :data:`STARTERS`; kept in the package so a starter can always
    be recomputed rather than trusted. Returns ``None`` if no Z-cyclic starter exists.

    Backtracking over the difference conditions, with two reductions that make it fast:

    * the whole starter can be translated freely, so ∞'s partner is fixed to ``0``;
    * each subsequent game must contain the smallest still-unused element, which removes
      permutations of otherwise identical partitions.

    Local limits are sufficient: the game count makes the number of finite partner pairs
    exactly equal to the number of difference classes, and the number of finite opponent
    pairs exactly twice that. Filling every game without exceeding a limit therefore means
    hitting every limit exactly.
    """
    if count < 4 or count % 4 != 0:
        return None

    modulus = count - 1
    class_count = modulus // 2

    def difference_class(left: int, right: int) -> int:
        delta = (left - right) % modulus
        return min(delta, modulus - delta)

    partner_used = [False] * (class_count + 1)
    opponent_count = [0] * (class_count + 1)

    def undo(applied: list[tuple[str, int]]) -> None:
        for kind, cls in applied:
            if kind == "p":
                partner_used[cls] = False
            else:
                opponent_count[cls] -= 1

    def place(game: SlotGame) -> list[tuple[str, int]] | None:
        """Apply a game's differences, or undo and return None on a conflict."""
        applied: list[tuple[str, int]] = []
        for pair in game:
            left, right = pair
            if left == INF or right == INF:
                continue
            cls = difference_class(left, right)
            if partner_used[cls]:
                undo(applied)
                return None
            partner_used[cls] = True
            applied.append(("p", cls))
        for left in game[0]:
            for right in game[1]:
                if left == INF or right == INF:
                    continue
                cls = difference_class(left, right)
                if opponent_count[cls] >= 2:
                    undo(applied)
                    return None
                opponent_count[cls] += 1
                applied.append(("o", cls))
        return applied

    solution: Starter | None = None

    def extend(remaining: tuple[int, ...], games: list[SlotGame]) -> bool:
        nonlocal solution
        if not remaining:
            solution = tuple(games)
            return True
        head, *rest = remaining
        pool = tuple(rest)
        for trio in combinations(pool, 3):
            for partner_index in range(3):
                partner = trio[partner_index]
                others = tuple(v for i, v in enumerate(trio) if i != partner_index)
                game: SlotGame = ((head, partner), (others[0], others[1]))
                applied = place(game)
                if applied is None:
                    continue
                games.append(game)
                if extend(tuple(v for v in pool if v not in trio), games):
                    return True
                games.pop()
                undo(applied)
        return False

    for left, right in combinations(range(1, modulus), 2):
        first: SlotGame = ((INF, 0), (left, right))
        applied = place(first)
        if applied is None:
            continue
        rest = tuple(v for v in range(1, modulus) if v not in (left, right))
        if extend(rest, [first]):
            return solution
        undo(applied)

    return None
