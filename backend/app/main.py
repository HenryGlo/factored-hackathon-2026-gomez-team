"""Aplicación FastAPI.

    .venv/bin/uvicorn --factory backend.app.main:create_app --reload
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
from backend.app.auth.deps import client_ip
from backend.app.policy.rules import load_policy_config
from backend.app.protection.budget import LLMBudget
from backend.app.protection.config import load_security_config
from backend.app.protection.headers import SecurityHeadersMiddleware
from backend.app.protection.ratelimit import RateLimitMiddleware
from backend.app.tools import Tools


def create_app(settings: Settings | None = None) -> FastAPI:
    s = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.dbs = Databases.from_settings(s)
        llm_cfg = load_llm_config()
        nodes = Nodes(make_client(llm_cfg), llm_cfg)
        app.state.controller = Controller(app.state.dbs.rw, Tools(app.state.dbs.rw), nodes, build_ml(nodes), load_policy_config(),
                                          reference_date=s.reference_date, budget=LLMBudget(app.state.dbs.rw, security))
        yield
        await app.state.dbs.dispose()

    security = load_security_config()
    prod = s.app_env == "production"
    app = FastAPI(title="Disputas de cargos no reconocidos", version="0.1.0", lifespan=lifespan,
                  docs_url=None if prod else "/docs", redoc_url=None if prod else "/redoc", openapi_url=None if prod else "/openapi.json")
    app.state.settings = s
    app.state.security = security
    app.state.faults = set()
    # orden: la última que se agrega es la más externa → cabeceras en todo (incluido el 429), luego CORS, luego límites
    if security.rate_enabled:
        app.add_middleware(RateLimitMiddleware, config=security, ip_of=lambda r: client_ip(r), session_cookie=s.session_cookie)
    if s.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=s.cors_origins, allow_credentials=True, allow_methods=["GET", "POST"],
                           allow_headers=["Content-Type", s.csrf_header, "Idempotency-Key"], max_age=600)
    app.add_middleware(SecurityHeadersMiddleware, production=prod)
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(auth_router)
    app.include_router(console_router)
    app.include_router(conversations_router)
    app.include_router(console_extra)

    @app.get("/api/health", tags=["salud"])
    async def health() -> dict:
        return {"status": "ok"}

    return app

