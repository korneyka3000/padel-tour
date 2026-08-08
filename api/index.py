"""Vercel entry point.

Vercel looks for the app here; the code itself lives in the package, where tests and linters
can see it.

``src`` is put on the path rather than installing the project, because Vercel's Python
builder does one or the other and not both: given a ``pyproject.toml`` it runs
``pip install .`` and ignores this directory's ``requirements.txt``, and given the
``requirements.txt`` it stops installing the project. The sources ship with the deployment
either way, so pointing at them is the one thing that always holds.
"""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
if SRC.is_dir() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from padel_tour.api import app  # noqa: E402  (path must be set up first)

__all__ = ["app"]
