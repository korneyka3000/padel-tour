"""The layers must not leak into each other.

Dependencies all live in one list now, so packaging no longer enforces this — these tests
do. Two of the failures they guard against have already happened for real: a serverless
function crashed on a CLI framework it never uses, because a package `__init__` re-exported
one, and the engine's purity is the thing the whole design rests on.

Each check runs in a fresh interpreter. Importing inside this process would see whatever
pytest and its plugins already loaded, which proves nothing.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap

#: The engine knows the rules of padel and nothing else. No database, no HTTP, no Telegram.
FORBIDDEN_FOR_ENGINE = ("sqlalchemy", "fastapi", "aiogram", "typer", "pydantic")

#: The service layer may reach the database, but not any interface.
FORBIDDEN_FOR_SERVICES = ("fastapi", "aiogram", "typer")

#: The webhook lives in the API, and a serverless function has no command line.
FORBIDDEN_FOR_API = ("typer",)


def imported_modules(module: str) -> set[str]:
    """Top-level packages loaded as a side effect of importing ``module``."""
    script = textwrap.dedent(f"""
        import sys
        import {module}
        print(" ".join(sorted({{name.split(".")[0] for name in sys.modules}})))
    """)
    result = subprocess.run(  # noqa: S603 - our own interpreter, our own script
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=True,
    )
    return set(result.stdout.split())


def test_the_engine_imports_nothing_but_the_standard_library() -> None:
    loaded = imported_modules("padel_tour.engine")
    leaked = loaded & set(FORBIDDEN_FOR_ENGINE)
    assert not leaked, (
        f"importing the engine pulled in {sorted(leaked)}; it is meant to know the rules of "
        f"padel and nothing else"
    )


def test_the_service_layer_stays_clear_of_interfaces() -> None:
    loaded = imported_modules("padel_tour.services")
    leaked = loaded & set(FORBIDDEN_FOR_SERVICES)
    assert not leaked, (
        f"the service layer pulled in {sorted(leaked)}; interfaces call it, never the "
        f"other way round"
    )


def test_the_api_does_not_drag_in_the_command_line() -> None:
    """This one broke a deploy: bot/__init__ re-exported the typer app."""
    loaded = imported_modules("padel_tour.api")
    leaked = loaded & set(FORBIDDEN_FOR_API)
    assert not leaked, (
        f"the API pulled in {sorted(leaked)}; a serverless function has no command line"
    )


def test_the_bot_package_does_not_import_its_command_line() -> None:
    loaded = imported_modules("padel_tour.bot")
    assert "typer" not in loaded, (
        "padel_tour.bot must not import its CLI module; anything reading the bot's config "
        "would then need typer"
    )
