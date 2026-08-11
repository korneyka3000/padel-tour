"""Where database access is allowed to live.

Queries used to be spread through the service modules, mixed in with the rules they served,
and "I cannot find where the queries are" is a fair complaint about a layer that does not
exist. It exists now, and this is what keeps it existing: the next query written in a
handler is a failing test rather than a slow drift back.
"""

from __future__ import annotations

import ast
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "src" / "padel_tour"

#: Only these two touch the database. ``repositories`` is the layer; ``db`` is the models,
#: the engine, and the mapper that turns rows into engine state.
ALLOWED = ("repositories", "db")

#: What talking to a database looks like in this codebase.
QUERY_CALLS = frozenset({"select", "insert", "update", "delete"})
SESSION_METHODS = frozenset({"add", "get", "scalar", "scalars", "execute", "delete", "merge"})


def offenders(tree: ast.AST) -> list[str]:
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        called = node.func
        if isinstance(called, ast.Name) and called.id in QUERY_CALLS:
            found.append(called.id)
        if (
            isinstance(called, ast.Attribute)
            and called.attr in SESSION_METHODS
            and isinstance(called.value, ast.Name)
            and called.value.id == "session"
        ):
            found.append(f"session.{called.attr}")
    return found


def test_only_the_data_layer_talks_to_the_database() -> None:
    stray: dict[str, list[str]] = {}
    for path in sorted(SOURCE.rglob("*.py")):
        if path.relative_to(SOURCE).parts[0] in ALLOWED:
            continue
        calls = offenders(ast.parse(path.read_text(encoding="utf-8")))
        if calls:
            stray[str(path.relative_to(SOURCE))] = sorted(set(calls))

    assert stray == {}, f"queries outside the data layer: {stray}"


def test_the_check_can_actually_see_a_query() -> None:
    """A scan that matches nothing would pass this file forever."""
    written_in_a_handler = ast.parse(
        "async def handler(session):\n"
        "    return await session.scalar(select(Player).where(Player.id == 1))\n"
    )

    assert sorted(set(offenders(written_in_a_handler))) == ["select", "session.scalar"]
