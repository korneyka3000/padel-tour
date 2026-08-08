"""The FastAPI application.

Kept importable as ``padel_tour.api.app:app`` so that uvicorn, the tests and Vercel all
reach exactly the same object.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from padel_tour.engine import PadelEngineError
from padel_tour.services import ConflictError, NotFoundError, ServiceError

from .deps import dispose_engine
from .routes import API_PREFIX, router
from .telegram import router as telegram_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Padel Tour",
        description="Americano and Mexicano tournaments: standings, charts, history.",
        version="0.1.0",
        lifespan=lifespan,
        # Under /api on purpose. Everything outside /api is rewritten to the web app's
        # index.html in production, so docs at their default paths answer 200 with a React
        # page — reachable, wrong, and quiet about it.
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=f"{API_PREFIX}/redoc",
        openapi_url=f"{API_PREFIX}/openapi.json",
        # No OAuth anywhere in this API, so the route Swagger UI would bounce a login
        # through has nothing to do. None removes it rather than parking it somewhere.
        swagger_ui_oauth2_redirect_url=None,
    )

    # The web app is served from the same deployment, so same-origin covers production.
    # Development runs Vite on another port, which is what this is for.
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.exception_handler(NotFoundError)
    async def _not_found(_: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ConflictError)
    async def _conflict(_: Request, exc: ConflictError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(ServiceError)
    async def _service(_: Request, exc: ServiceError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(PadelEngineError)
    async def _engine(_: Request, exc: PadelEngineError) -> JSONResponse:
        # Engine messages name the round, the court, the score that was wrong. They are
        # written for a person and are safe to pass straight through.
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    app.include_router(router)
    app.include_router(telegram_router)
    return app


app = create_app()
