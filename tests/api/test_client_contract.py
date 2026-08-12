"""Every call the web app makes, checked against the routes this API actually declares.

Two of them were wrong at once, and both the same way. ``web/src/lib/api.ts`` picks the verb
for you — ``body === undefined ? 'GET' : 'POST'`` — so a POST that happens to need no body
is silently sent as a GET. ``invite`` answered *Method Not Allowed* in the middle of the
roster screen, and ``signOut`` had never worked at all: the request 405'd, the client threw,
and the page cleared its own state anyway, so signing out looked fine and left the session
open. Both were invisible from either side alone. The client is self-consistent; the server
is self-consistent; only the pair is wrong.

The workaround was already in the file, which is the part worth noticing — ``reroll``,
``nextRound`` and ``finish`` all pass ``{}`` as a body they do not have, purely to make the
verb come out right. Somebody hit this before and patched the call instead of the rule.

So the check reads the client as text and asks this application which routes exist. No
fixture to regenerate, and no way for the two to drift apart quietly: add a call to a route
that is not there, or send it with the wrong verb, and this names it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from padel_tour.api.app import create_app

CLIENT = Path(__file__).resolve().parents[2] / "web" / "src" / "lib" / "api.ts"

#: The client prefixes every path with this; the server mounts every route under it.
PREFIX = "/api"

#: ``${playerId}`` on one side, ``{player_id}`` on the other. Same route, different spelling.
_HOLE = re.compile(r"\$\{[^}]*\}|\{[^}]*\}")


def canonical(path: str) -> str:
    return _HOLE.sub("{}", path)


def _arguments(source: str, start: int) -> list[str]:
    """The top-level arguments of the call whose ``(`` is at ``start``."""
    depth, current, found = 0, "", []
    for index in range(start, len(source)):
        char = source[index]
        if char in "([{":
            depth += 1
            if depth == 1:
                continue
        elif char in ")]}":
            depth -= 1
            if depth == 0:
                found.append(current.strip())
                return [argument for argument in found if argument]
        elif char == "," and depth == 1:
            found.append(current.strip())
            current = ""
            continue
        if depth >= 1:
            current += char
    raise AssertionError("unbalanced call in api.ts")


def calls() -> list[tuple[str, str, str]]:
    """``(name, method, path)`` for every request the client can make."""
    source = CLIENT.read_text()
    block = source[source.index("export const api = {") :]
    found: list[tuple[str, str, str]] = []

    for match in re.finditer(r"(\w+):\s*\([^)]*\)\s*=>", block):
        name = match.group(1)
        call = re.search(r"\b(?:required|request)<[^>]*>\s*\(", block[match.end() :])
        if call is None:  # pragma: no cover - every entry makes a request
            continue
        arguments = _arguments(block[match.end() :], call.end() - 1)
        path = arguments[0].strip("`'\"")
        explicit = next((a for a in arguments[1:] if a.startswith(("'", '"'))), None)
        if explicit is not None:
            method = explicit.strip("'\"")
        else:
            body = arguments[1] if len(arguments) > 1 else "undefined"
            method = "GET" if body == "undefined" else "POST"
        found.append((name, method.upper(), path))

    return found


def declared() -> set[tuple[str, str]]:
    """``(method, path)`` for every route this API serves."""
    paths = create_app().openapi()["paths"]
    return {
        (method.upper(), canonical(path))
        for path, operations in paths.items()
        for method in operations
    }


def test_the_client_was_read_at_all() -> None:
    """A parser that quietly finds nothing would make every test below pass."""
    found = calls()

    assert len(found) > 15
    assert ("invite", "POST", "/players/${playerId}/invite") in found
    assert ("signOut", "POST", "/auth/sign-out") in found


@pytest.mark.parametrize(("name", "method", "path"), calls(), ids=str)
def test_every_call_reaches_a_route_that_accepts_it(name: str, method: str, path: str) -> None:
    routes = declared()
    wanted = (method, canonical(f"{PREFIX}{path}"))

    if wanted in routes:
        return

    # A wrong verb and a wrong path are different mistakes, and only one of them is subtle.
    others = sorted(verb for verb, route in routes if route == wanted[1])
    assert others, f"api.{name} calls {wanted[1]}, which this API does not serve"
    raise AssertionError(
        f"api.{name} sends {method} to {wanted[1]}, which only accepts {', '.join(others)}"
    )
