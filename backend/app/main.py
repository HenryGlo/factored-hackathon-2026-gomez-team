"""Aplicación FastAPI.

    .venv/bin/uvicorn --factory backend.app.main:create_app --reload
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.app.auth.router import router as auth_router
from backend.app.config import Settings, get_settings
from backend.app.console.router import router as console_router
from backend.app.db import Databases
from backend.app.errors import ApiError, api_error_handler


def create_app(settings: Settings | None = None) -> FastAPI:
    s = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.dbs = Databases.from_settings(s)
        yield
        await app.state.dbs.dispose()

    app = FastAPI(title="Disputas de cargos no reconocidos", version="0.1.0", lifespan=lifespan)
    app.state.settings = s
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(auth_router)
    app.include_router(console_router)

    @app.get("/api/health", tags=["salud"])
    async def health() -> dict:
        return {"status": "ok"}

    return app

