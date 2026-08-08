"""HTTP API — a thin transport over the service layer.

No business logic lives here. Endpoints load a view, turn it into a wire schema, and answer.
Anything that decides something belongs in :mod:`padel_tour.services`.

Requires the ``api`` and ``db`` extras.
"""

from .app import app, create_app

__all__ = ["app", "create_app"]
