"""api/requirements.txt must cover what the deployed function actually imports.

Vercel installs from this file, not from pyproject.toml, and the two drifting apart is
invisible until a request comes in and the import fails. That already happened twice: once
because pip read `.[api,db,bot]` as a bare `.`, and once because the file sat at the
repository root where Vercel never looked at it.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Extras the serverless function needs. `cli` is not among them — Vercel does not run it.
DEPLOYED_EXTRAS = ("api", "db", "bot")

#: Declared in an extra but deliberately not bundled into the function, with the reason.
NOT_BUNDLED = {
    "uvicorn": "Vercel provides the server",
    "alembic": "migrations are run against the database, never from a request",
    "typer": "only padel-tour-bot's command line uses it, and that does not run here",
}


def distribution_name(requirement: str) -> str:
    """`sqlalchemy[asyncio]>=2.0.36` -> `sqlalchemy`."""
    return re.split(r"[\[<>=!~; ]", requirement.strip(), maxsplit=1)[0].lower()


def read_requirements() -> set[str]:
    lines = (ROOT / "api" / "requirements.txt").read_text().splitlines()
    return {
        distribution_name(line)
        for line in lines
        if line.strip() and not line.startswith("#") and line.strip() != "."
    }


def read_extras() -> set[str]:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    extras = pyproject["project"]["optional-dependencies"]
    return {
        distribution_name(requirement) for extra in DEPLOYED_EXTRAS for requirement in extras[extra]
    }


def test_requirements_cover_every_deployed_extra() -> None:
    missing = read_extras() - read_requirements() - set(NOT_BUNDLED)
    assert not missing, (
        f"requirements.txt is missing {sorted(missing)} — the deployed function would "
        f"import them and crash"
    )


def test_requirements_hold_nothing_extra() -> None:
    """A stale line here ships weight the function never imports."""
    stray = read_requirements() - read_extras()
    assert not stray, f"requirements.txt lists {sorted(stray)}, which no extra asks for"


def test_the_file_sits_next_to_the_function() -> None:
    """At the repository root Vercel silently ignores it and the function ships broken."""
    assert (ROOT / "api" / "requirements.txt").exists()
    assert not (ROOT / "requirements.txt").exists()


def test_importing_the_api_does_not_drag_in_the_command_line() -> None:
    """The webhook lives in the API, and a serverless function has no command line.

    This broke a deploy: `api/telegram.py` imports `bot.config`, whose package `__init__`
    re-exported the typer app, so the function crashed on a missing typer it never used.
    """
    source = (ROOT / "src" / "padel_tour" / "bot" / "__init__.py").read_text()
    assert "from .app import" not in source, (
        "padel_tour.bot.__init__ must not import the CLI module; anything importing the "
        "bot's config would then need typer"
    )
