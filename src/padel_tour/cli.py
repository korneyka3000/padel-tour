"""Text-mode tournament runner.

Not the product — that is a Telegram bot and a web app. This exists so the engine can be
driven end to end by hand before any of that is built.

    uv run padel-tour play      # run a tournament interactively
    uv run padel-tour demo      # play both formats out with random scores

Requires the optional ``cli`` extra; the engine itself has no dependencies.
"""

from __future__ import annotations

import secrets
from collections.abc import Sequence
from random import Random
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from .engine import (
    COMMON_POINT_TARGETS,
    Format,
    PadelEngineError,
    PairingPattern,
    PlayerId,
    Round,
    TournamentConfig,
    TournamentState,
    create_americano,
    create_mexicano,
    finish,
    next_round,
    pending_matches,
    progression,
    record_result,
    reroll,
    standings,
    supported_player_counts,
)
from .engine.roster import validate_roster
from .engine.whist import require_supported_player_count

app = typer.Typer(
    name="padel-tour",
    help="Run padel tournaments: Americano and Mexicano.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()

FORMAT_HELP = {
    Format.AMERICANO: "schedule known up front, everyone partners everyone",
    Format.MEXICANO: "pairs drawn from the standing after every round",
}
PATTERN_HELP = {
    PairingPattern.CROSSOVER: "1+4 vs 2+3 (crossover, the standard)",
    PairingPattern.SPLIT: "1+3 vs 2+4 (split)",
    PairingPattern.TOP_HEAVY: "1+2 vs 3+4 (top-heavy)",
}

DEMO_PLAYERS = ("Ann", "Ben", "Cara", "Dan", "Eve", "Finn", "Gina", "Hugo")


# --------------------------------------------------------------------------- rendering


def show_round(state: TournamentState, rnd: Round) -> None:
    console.print(f"\n[bold]Round {rnd.number} of {state.total_rounds}[/bold]")
    for match in rnd.matches:
        left = f"{match.team_a.a} + {match.team_a.b}"
        right = f"{match.team_b.a} + {match.team_b.b}"
        score = ""
        if match.result is not None:
            score = f"   [bold]{match.result.score_a}:{match.result.score_b}[/bold]"
        console.print(f"  court {match.court}: {left}  [dim]vs[/dim]  {right}{score}")


def show_schedule(state: TournamentState) -> None:
    for rnd in state.rounds:
        show_round(state, rnd)


def show_table(state: TournamentState) -> None:
    table = Table(title="Standings", title_justify="left", header_style="bold")
    table.add_column("#", justify="right")
    table.add_column("player")
    for heading in ("played", "W", "D", "L", "points", "diff"):
        table.add_column(heading, justify="right")

    for row in standings(state):
        table.add_row(
            str(row.rank),
            row.player,
            str(row.played),
            str(row.wins),
            str(row.draws),
            str(row.losses),
            f"[bold]{row.points_for}[/bold]",
            f"{row.diff:+}",
        )
    console.print()
    console.print(table)


def show_progress(state: TournamentState) -> None:
    """Cumulative points round by round, plus how each player moved through the ranks."""
    series = progression(state)
    played_rounds = [point.round_no for point in next(iter(series.values()), ())]
    if not played_rounds:
        return

    table = Table(
        title="Round by round — cumulative points",
        title_justify="left",
        header_style="bold",
    )
    table.add_column("player")
    for number in played_rounds:
        table.add_column(f"R{number}", justify="right")
    table.add_column("rank path")

    for row in standings(state):
        points = series[row.player]
        table.add_row(
            row.player,
            *(str(point.cumulative_points) for point in points),
            "[dim]→[/dim]".join(str(point.rank) for point in points),
        )
    console.print()
    console.print(table)


# --------------------------------------------------------------------------- input


def parse_score(raw: str, target: int) -> tuple[int, int]:
    """Accept ``14 10``, ``14:10``, ``14-10`` or just ``14`` — one number implies the other."""
    digits = "".join(char if char.isdigit() else " " for char in raw).split()
    if len(digits) == 1:
        scored = int(digits[0])
        if scored > target:
            raise ValueError(f"the match runs to {target} points, {scored} is too many")
        return scored, target - scored
    if len(digits) == 2:
        return int(digits[0]), int(digits[1])
    raise ValueError("enter a score like '14 10', or just '14'")


def choose[T](prompt: str, options: Sequence[tuple[T, str]], default: int = 1) -> T:
    console.print(f"\n[bold]{prompt}[/bold]")
    for index, (_, label) in enumerate(options, start=1):
        console.print(f"  {index}. {label}")
    picked = typer.prompt("Choice", default=default, type=int)
    while not 1 <= picked <= len(options):
        console.print("[red]Pick a number from the list.[/red]")
        picked = typer.prompt("Choice", default=default, type=int)
    return options[picked - 1][0]


def ask_players(fmt: Format) -> tuple[PlayerId, ...]:
    """Ask until the roster is one the chosen format can actually schedule."""
    counts = ", ".join(str(count) for count in supported_player_counts())
    console.print(f"\n[bold]Players[/bold], comma separated. Americano supports {counts}.")
    console.print("[dim]A bare number generates 'Player 1', 'Player 2', …[/dim]")
    while True:
        raw = typer.prompt("Players", default="8")
        if raw.strip().isdigit():
            names = tuple(f"Player {index}" for index in range(1, int(raw) + 1))
        else:
            names = tuple(name.strip() for name in raw.split(",") if name.strip())
        if not names:
            console.print("[red]Empty — try again.[/red]")
            continue
        try:
            validate_roster(names)
            if fmt is Format.AMERICANO:
                require_supported_player_count(len(names))
        except PadelEngineError as exc:
            console.print(f"[red]{exc}[/red]")
            continue
        return names


# --------------------------------------------------------------------------- flow


def build(seed: int) -> TournamentState:
    fmt = choose(
        "Tournament format",
        [(value, f"{value.value.title()} — {FORMAT_HELP[value]}") for value in Format],
    )
    players = ask_players(fmt)
    points = choose(
        "How many points does a match run to?",
        [(value, f"{value} points") for value in COMMON_POINT_TARGETS],
        default=COMMON_POINT_TARGETS.index(24) + 1,
    )

    if fmt is Format.AMERICANO:
        return create_americano(players, TournamentConfig(fmt, points_per_match=points), seed)

    pattern = choose(
        "How should each court's four be split?",
        [(value, PATTERN_HELP[value]) for value in PairingPattern],
    )
    rounds = typer.prompt("\nHow many rounds?", default=len(players) - 1, type=int)
    config = TournamentConfig(
        fmt, points_per_match=points, pairing_pattern=pattern, rounds=max(1, rounds)
    )
    return create_mexicano(players, config, seed)


def confirm_draw(state: TournamentState) -> TournamentState:
    while True:
        if state.config.format is Format.AMERICANO:
            console.print(
                f"\n[bold]Draw for {len(state.players)} players, {state.total_rounds} rounds[/bold]"
            )
            show_schedule(state)
        else:
            current = state.current_round
            assert current is not None
            show_round(state, current)

        if not typer.confirm("\nRedraw?", default=False):
            return state
        state = reroll(state)


def run(state: TournamentState) -> None:
    target = state.config.points_per_match
    console.print(
        f"\n[dim]Enter scores as '14 10' or just '14' (match to {target}). "
        f"Type 'q' to end the tournament.[/dim]"
    )

    while not state.finished:
        pending = pending_matches(state)
        if not pending:
            if state.config.format is Format.MEXICANO and len(state.rounds) < state.total_rounds:
                state = next_round(state)
                continue
            state = finish(state)
            break

        round_no = pending[0][0]
        rnd = state.round_by_number(round_no)
        assert rnd is not None
        show_round(state, rnd)

        for match in rnd.matches:
            if match.played:
                continue
            label = f"{match.team_a.a}+{match.team_a.b} vs {match.team_b.a}+{match.team_b.b}"
            while True:
                raw = typer.prompt(f"  court {match.court}  {label}")
                if raw.strip().lower() == "q":
                    state = finish(state)
                    break
                try:
                    score_a, score_b = parse_score(raw, target)
                    state = record_result(state, round_no, match.court, score_a, score_b)
                except (ValueError, PadelEngineError) as exc:
                    console.print(f"    [red]{exc}[/red]")
                    continue
                break
            if state.finished:
                break

        if not state.finished:
            show_table(state)
            show_progress(state)

    console.rule("[bold]Final[/bold]")
    show_table(state)
    show_progress(state)


# --------------------------------------------------------------------------- commands

SeedOption = Annotated[
    int | None, typer.Option("--seed", help="Fix the draw so it can be reproduced.")
]


@app.command()
def play(seed: SeedOption = None) -> None:
    """Run a tournament interactively."""
    try:
        run(confirm_draw(build(seed if seed is not None else secrets.randbits(32))))
    except EOFError, KeyboardInterrupt, typer.Abort:
        console.print("\n[dim]Aborted.[/dim]")
        raise typer.Exit(130) from None
    except PadelEngineError as exc:
        console.print(f"\n[red]Error:[/red] {exc}")
        raise typer.Exit(1) from None


@app.command()
def demo(seed: SeedOption = None) -> None:
    """Play both formats out with random scores — a quick end-to-end check."""
    seed = seed if seed is not None else secrets.randbits(32)
    rng = Random(seed)
    target = 24

    console.rule("[bold]Americano — 8 players, full cycle[/bold]")
    state = create_americano(DEMO_PLAYERS, TournamentConfig(Format.AMERICANO), seed)
    show_schedule(state)
    for rnd in state.rounds:
        for match in rnd.matches:
            scored = rng.randrange(target + 1)
            state = record_result(state, rnd.number, match.court, scored, target - scored)
    show_table(state)
    show_progress(state)

    console.rule("[bold]Mexicano — 8 players, 5 rounds, crossover[/bold]")
    state = create_mexicano(DEMO_PLAYERS, TournamentConfig(Format.MEXICANO, rounds=5), seed)
    for number in range(1, 6):
        if number > 1:
            state = next_round(state)
        current = state.current_round
        assert current is not None
        show_round(state, current)
        for match in current.matches:
            scored = rng.randrange(target + 1)
            state = record_result(state, number, match.court, scored, target - scored)
    show_table(state)
    show_progress(state)


if __name__ == "__main__":
    app()
