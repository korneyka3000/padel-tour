"""Vercel entry point.

Vercel looks for the app here; the code itself lives in the package, where tests and
linters can see it.
"""

from padel_tour.api import app

__all__ = ["app"]
