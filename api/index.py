"""Vercel entry point.

Three lines on purpose: the application lives in the package, where tests and linters see
it. Vercel finds a function at this path by convention and serves ``/api/*`` from it.

No `sys.path` juggling here — Vercel installs the project with `uv sync`, which puts
`padel_tour` on the path along with everything it needs.
"""

from padel_tour.api import app

__all__ = ["app"]
