"""Aplicación FastAPI.

    .venv/bin/uvicorn --factory backend.app.main:create_app --reload
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.app.auth.router import router as auth_router
from backend.app.config import Settings, get_settings
from backend.app.console.router import router as console_router
from backend.app.controller.engine import Controller
from backend.app.conversations import console as console_extra
from backend.app.conversations import router as conversations_router
from backend.app.db import Databases
from backend.app.errors import ApiError, api_error_handler
from backend.app.llm.config import load_llm_config
from backend.app.llm.factory import make_client
from backend.app.llm.nodes import Nodes
from backend.app.ml.registry import build_ml
from backend.app.policy.rules import load_policy_config
from backend.app.tools import Tools


def create_app(settings: Settings | None = None) -> FastAPI:
    s = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.dbs = Databases.from_settings(s)
        llm_cfg = load_llm_config()
        nodes = Nodes(make_client(llm_cfg), llm_cfg)
        app.state.controller = Controller(app.state.dbs.rw, Tools(app.state.dbs.rw), nodes, build_ml(nodes), load_policy_config(),
                                          reference_date=s.reference_date)
        yield
        await app.state.dbs.dispose()

    app = FastAPI(title="Disputas de cargos no reconocidos", version="0.1.0", lifespan=lifespan)
    app.state.settings = s
    app.state.faults = set()
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(auth_router)
    app.include_router(console_router)
    app.include_router(conversations_router)
    app.include_router(console_extra)

    @app.get("/api/health", tags=["salud"])
    async def health() -> dict:
        return {"status": "ok"}

    return app

