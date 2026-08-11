"""Text-mode tournament runner.

Not the product — that is a Telegram bot and a web app. This exists so the whole stack can
be driven by hand, end to end, before either of those is built.

    uv run padel-tour play       # start a tournament and score it
    uv run padel-tour resume     # pick up where you left off
    uv run padel-tour history    # past tournaments
    uv run padel-tour demo       # play both formats out with random scores, no database

Everything except ``demo`` is stored. With no ``DATABASE_URL`` set that means a local
``padel.db`` file, which is what makes ``play`` then ``resume`` work on a fresh checkout.

Requires the ``cli`` and ``db`` extras; the engine itself has no dependencies.
"""

from __future__ import annotations

import asyncio
import secrets
from random import Random
from typing import TYPE_CHECKING, Annotated

import typer
from rich.console import Console
from rich.table import Table

from .db import create_engine, create_session_factory, database_url
from .db.session import session_scope
from .engine import (
    COMMON_POINT_TARGETS,
    Format,
    PadelEngineError,
    PairingPattern,
    Round,
    TournamentConfig,
    create_americano,
    create_mexicano,
    next_round,
    progression,
    record_result,
    standings,
    supported_player_counts,
)
from .engine.roster import validate_roster
from .engine.whist import require_supported_player_count
from .services import (
    MatchView,
    RoundView,
    ServiceError,
    TournamentView,
    active_tournament,
    add_player,
    advance_round,
    create_group,
    finish_tournament,
    list_groups,
    list_players,
    list_tournaments,
    record_score,
    reroll_tournament,
    start_tournament,
)

if TYPE_CHECKING:
    import uuid
    from collections.abc import Awaitable, Callable, Sequence

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

    from .engine import TournamentState

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


def show_round(rnd: RoundView, total_rounds: int) -> None:
    console.print(f"\n[bold]Round {rnd.number} of {total_rounds}[/bold]")
    for match in rnd.matches:
        left = " + ".join(match.team_a)
        right = " + ".join(match.team_b)
        score = ""
        if match.played:
            score = f"   [bold]{match.score_a}:{match.score_b}[/bold]"
        console.print(f"  court {match.court}: {left}  [dim]vs[/dim]  {right}{score}")


def show_schedule(view: TournamentView) -> None:
    for rnd in view.rounds:
        show_round(rnd, view.total_rounds)


def show_table(view: TournamentView) -> None:
    table = Table(title="Standings", title_justify="left", header_style="bold")
    table.add_column("#", justify="right")
    table.add_column("player")
    for heading in ("played", "W", "D", "L", "points", "diff"):
        table.add_column(heading, justify="right")

    for row in view.standings:
        table.add_row(
            str(row.rank),
            row.name,
            str(row.played),
            str(row.wins),
            str(row.draws),
            str(row.losses),
            f"[bold]{row.points_for}[/bold]",
            f"{row.diff:+}",
        )
    console.print()
    console.print(table)


def show_progress(view: TournamentView) -> None:
    """Cumulative points round by round, plus how each player moved through the ranks."""
    series = view.progression
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

    for row in view.standings:
        points = series[row.player_id]
        table.add_row(
            row.name,
            *(str(point.cumulative_points) for point in points),
            "[dim]→[/dim]".join(str(point.rank) for point in points),
        )
    console.print()
    console.print(table)


def show_summary(view: TournamentView) -> None:
    show_table(view)
    show_progress(view)


# --------------------------------------------------------------------------- input


def parse_score(raw: str, target: int) -> tuple[int, int]:
    """Accept ``14 10``, ``14:10``, ``14-10`` or just ``14`` — one number implies the other."""
    digits = "".join(char if char.isdigit() else " " for char in raw).split()
    match digits:
        case [only]:
            scored = int(only)
            if scored > target:
                raise ValueError(f"the match runs to {target} points, {scored} is too many")
            return scored, target - scored
        case [left, right]:
            return int(left), int(right)
        case _:
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


def ask_names(fmt: Format) -> list[str]:
    """Ask until the roster is one the chosen format can actually schedule."""
    counts = ", ".join(str(count) for count in supported_player_counts())
    console.print(f"\n[bold]Players[/bold], comma separated. Americano supports {counts}.")
    console.print("[dim]A bare number generates 'Player 1', 'Player 2', …[/dim]")
    while True:
        raw = typer.prompt("Players", default="8")
        if raw.strip().isdigit():
            names = [f"Player {index}" for index in range(1, int(raw) + 1)]
        else:
            names = [name.strip() for name in raw.split(",") if name.strip()]
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


def ask_format() -> Format:
    """Asked before the roster, because it decides which player counts are legal."""
    return choose(
        "Tournament format",
        [(value, f"{value.value.title()} — {FORMAT_HELP[value]}") for value in Format],
    )


def ask_config(fmt: Format, player_count: int) -> TournamentConfig:
    points = choose(
        "How many points does a match run to?",
        [(value, f"{value} points") for value in COMMON_POINT_TARGETS],
        default=COMMON_POINT_TARGETS.index(24) + 1,
    )
    if fmt is Format.AMERICANO:
        return TournamentConfig(fmt, points_per_match=points)

    pattern = choose(
        "How should each court's four be split?",
        [(value, PATTERN_HELP[value]) for value in PairingPattern],
    )
    rounds = typer.prompt("\nHow many rounds?", default=player_count - 1, type=int)
    return TournamentConfig(
        fmt, points_per_match=points, pairing_pattern=pattern, rounds=max(1, rounds)
    )


# --------------------------------------------------------------------------- storage


async def _open_database() -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """Engine and session factory, with the schema in place for a local SQLite file.

    Creating tables on the fly is fine for SQLite because that file *is* the local dev
    database. Anything else is expected to have had migrations run against it.
    """
    engine = create_engine(database_url())
    return engine, create_session_factory(engine)


def run_stored[T](work: Callable[[AsyncSession], Awaitable[T]]) -> T:
    """Run one unit of work against the database, committing it and tidying up.

    Errors are turned into a message and a non-zero exit rather than a traceback: everything
    the service and engine layers raise is already written for a person to read.
    """

    async def main() -> T:
        engine, factory = await _open_database()
        try:
            async with session_scope(factory) as session:
                return await work(session)
        finally:
            await engine.dispose()

    try:
        return asyncio.run(main())
    except EOFError, KeyboardInterrupt:
        console.print("\n[dim]Stopped. Progress up to the last score is saved.[/dim]")
        raise typer.Exit(130) from None
    except (PadelEngineError, ServiceError) as exc:
        console.print(f"\n[red]Error:[/red] {exc}")
        raise typer.Exit(1) from None


async def _pick_group(session: AsyncSession) -> uuid.UUID:
    """Choose an existing group, or make the first one."""
    groups = await list_groups(session)
    if not groups:
        name = typer.prompt("\nName this group", default="My padel group")
        return (await create_group(session, name)).id
    if len(groups) == 1:
        return groups[0].id
    return choose(
        "Which group?",
        [(group.id, f"{group.name} ({group.player_count} players)") for group in groups],
    )


async def _resolve_players(
    session: AsyncSession, group_id: uuid.UUID, names: Sequence[str]
) -> list[uuid.UUID]:
    """Map names to players, adding anyone the group has not seen before."""
    known = {player.name: player.id for player in await list_players(session, group_id)}
    resolved = []
    for name in names:
        if name not in known:
            known[name] = (await add_player(session, group_id, name)).id
            console.print(f"[dim]added {name} to the group[/dim]")
        resolved.append(known[name])
    return resolved


# --------------------------------------------------------------------------- play loop


async def ask_result(
    session: AsyncSession, view: TournamentView, rnd: RoundView, match: MatchView
) -> TournamentView:
    """Prompt until this court has a legal score, or the organiser ends the tournament."""
    target = view.points_per_match
    label = f"{'+'.join(match.team_a)} vs {'+'.join(match.team_b)}"
    while True:
        raw = typer.prompt(f"  court {match.court}  {label}")
        if raw.strip().lower() == "q":
            ended = await finish_tournament(session, view.id)
            await session.commit()
            return ended
        try:
            score_a, score_b = parse_score(raw, target)
            updated = await record_score(
                session,
                view.id,
                round_no=rnd.number,
                court=match.court,
                score_a=score_a,
                score_b=score_b,
            )
        except (ValueError, PadelEngineError) as exc:
            console.print(f"    [red]{exc}[/red]")
            continue
        # One entered score is one unit of work here. Committing straight away is what makes
        # walking away mid-tournament safe: an interrupt rolls back the transaction, and
        # anything still open would be lost.
        await session.commit()
        return updated


async def score_round(
    session: AsyncSession, view: TournamentView, rnd: RoundView
) -> TournamentView:
    """Collect every outstanding score in one round."""
    show_round(rnd, view.total_rounds)
    for match in rnd.matches:
        if match.played:
            continue
        view = await ask_result(session, view, rnd, match)
        if view.finished:
            break
    return view


async def play_loop(session: AsyncSession, view: TournamentView) -> TournamentView:
    """Score rounds until the tournament ends or the organiser stops."""
    console.print(
        f"\n[dim]Enter scores as '14 10' or just '14' (match to {view.points_per_match}). "
        f"Type 'q' to end the tournament. Ctrl-C is safe — progress is saved.[/dim]"
    )

    while not view.finished:
        rnd = view.next_unfinished_round
        if rnd is None:
            if view.format is Format.MEXICANO and len(view.rounds) < view.total_rounds:
                view = await advance_round(session, view.id)
                await session.commit()
                continue
            view = await finish_tournament(session, view.id)
            await session.commit()
            break

        view = await score_round(session, view, rnd)
        if not view.finished:
            show_summary(view)

    console.rule("[bold]Final[/bold]")
    show_summary(view)
    return view


# --------------------------------------------------------------------------- commands

SeedOption = Annotated[
    int | None, typer.Option("--seed", help="Fix the draw so it can be reproduced.")
]


@app.command()
def play(seed: SeedOption = None) -> None:
    """Start a tournament and score it. Progress is saved as you go."""

    async def work(session: AsyncSession) -> None:
        group_id = await _pick_group(session)

        if await active_tournament(session, group_id) is not None:
            console.print(
                "\n[yellow]This group already has a tournament in progress.[/yellow]\n"
                "Run [bold]padel-tour resume[/bold] to continue it."
            )
            raise typer.Exit(1)

        fmt = ask_format()
        names = ask_names(fmt)
        config = ask_config(fmt, len(names))
        player_ids = await _resolve_players(session, group_id, names)

        view = await start_tournament(session, group_id, player_ids, config, seed=seed)
        await session.commit()

        while True:
            if view.format is Format.AMERICANO:
                console.print(
                    f"\n[bold]Draw for {len(names)} players, {view.total_rounds} rounds[/bold]"
                )
                show_schedule(view)
            else:
                current = view.current_round
                if current is not None:
                    show_round(current, view.total_rounds)
            if not typer.confirm("\nRedraw?", default=False):
                break
            view = await reroll_tournament(session, view.id)
            await session.commit()

        await play_loop(session, view)

    run_stored(work)


@app.command()
def resume() -> None:
    """Continue the tournament in progress."""

    async def work(session: AsyncSession) -> None:
        group_id = await _pick_group(session)
        view = await active_tournament(session, group_id)
        if view is None:
            console.print(
                "\n[yellow]No tournament in progress.[/yellow] "
                "Start one with [bold]padel-tour play[/bold]."
            )
            raise typer.Exit(1)

        # An Americano draws every round up front, so len(rounds) is the schedule length,
        # not where play has got to. The first unfinished round is the honest answer.
        pending = view.next_unfinished_round
        at = pending.number if pending else view.total_rounds
        console.print(
            f"\n[bold]Resuming[/bold] — {view.format.value.title()}, "
            f"round {at} of {view.total_rounds}"
        )
        show_summary(view)
        await play_loop(session, view)

    run_stored(work)


@app.command()
def history(
    limit: Annotated[int, typer.Option(help="How many tournaments to show.")] = 20,
) -> None:
    """List past tournaments."""

    async def work(session: AsyncSession) -> None:
        group_id = await _pick_group(session)
        entries = await list_tournaments(session, group_id, limit=limit)
        if not entries:
            console.print("\n[dim]No tournaments yet.[/dim]")
            return

        table = Table(title="Tournaments", title_justify="left", header_style="bold")
        for heading in ("date", "format", "players", "rounds", "winner", "status"):
            table.add_column(heading)
        for entry in entries:
            table.add_row(
                entry.created_at.strftime("%Y-%m-%d %H:%M"),
                entry.format.value.title(),
                str(entry.player_count),
                f"{entry.rounds_played}/{entry.total_rounds}",
                entry.winner_name or "[dim]—[/dim]",
                "finished" if entry.finished else "[yellow]in progress[/yellow]",
            )
        console.print()
        console.print(table)

    run_stored(work)


@app.command()
def players() -> None:
    """Show the group's roster."""

    async def work(session: AsyncSession) -> None:
        group_id = await _pick_group(session)
        roster = await list_players(session, group_id)
        if not roster:
            console.print("\n[dim]No players yet — 'play' adds them as you type names.[/dim]")
            return
        console.print()
        for player in roster:
            console.print(f"  {player.name}")

    run_stored(work)


@app.command()
def demo(seed: SeedOption = None) -> None:
    """Play both formats out with random scores. Touches no database."""
    seed = seed if seed is not None else secrets.randbits(32)
    rng = Random(seed)
    target = 24

    console.rule("[bold]Americano — 8 players, full cycle[/bold]")
    state = create_americano(DEMO_PLAYERS, TournamentConfig(Format.AMERICANO), seed)
    for rnd in state.rounds:
        _show_engine_round(rnd, state.total_rounds)
        for match in rnd.matches:
            scored = rng.randrange(target + 1)
            state = record_result(state, rnd.number, match.court, scored, target - scored)
    _show_engine_summary(state)

    console.rule("[bold]Mexicano — 8 players, 5 rounds, crossover[/bold]")
    state = create_mexicano(DEMO_PLAYERS, TournamentConfig(Format.MEXICANO, rounds=5), seed)
    for number in range(1, 6):
        if number > 1:
            state = next_round(state)
        current = state.rounds[-1]
        _show_engine_round(current, state.total_rounds)
        for match in current.matches:
            scored = rng.randrange(target + 1)
            state = record_result(state, number, match.court, scored, target - scored)
    _show_engine_summary(state)


def _show_engine_round(rnd: Round, total_rounds: int) -> None:
    """Render straight from engine state — demo has no database and so no names."""
    console.print(f"\n[bold]Round {rnd.number} of {total_rounds}[/bold]")
    for match in rnd.matches:
        left = f"{match.team_a.a} + {match.team_a.b}"
        right = f"{match.team_b.a} + {match.team_b.b}"
        console.print(f"  court {match.court}: {left}  [dim]vs[/dim]  {right}")


def _show_engine_summary(state: TournamentState) -> None:
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

    series = progression(state)
    played_rounds = [point.round_no for point in next(iter(series.values()), ())]
    if not played_rounds:
        return
    chart = Table(
        title="Round by round — cumulative points",
        title_justify="left",
        header_style="bold",
    )
    chart.add_column("player")
    for number in played_rounds:
        chart.add_column(f"R{number}", justify="right")
    chart.add_column("rank path")
    for row in standings(state):
        points = series[row.player]
        chart.add_row(
            row.player,
            *(str(point.cumulative_points) for point in points),
            "[dim]→[/dim]".join(str(point.rank) for point in points),
        )
    console.print()
    console.print(chart)


if __name__ == "__main__":
    app()
