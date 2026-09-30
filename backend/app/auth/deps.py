"""Dependencias de FastAPI: sesión, rol y CSRF.

El customer_id de cualquier operación sale de `SessionContext` (la sesión autenticada). Ningún
endpoint lo recibe en el cuerpo ni en la URL.
"""
from __future__ import annotations

from fastapi import Depends, Request

from backend.app.auth.service import SessionContext, resolve_session
from backend.app.config import Settings
from backend.app.db import Databases
from backend.app.errors import ApiError, forbidden
from backend.app.security import same, sha256


def settings(request: Request) -> Settings:
    return request.app.state.settings


def databases(request: Request) -> Databases:
    return request.app.state.dbs


def client_ip(request: Request) -> str:
    s: Settings = request.app.state.settings
    if s.trust_proxy and (fwd := request.headers.get("x-forwarded-for")):
        return fwd.split(",")[0].strip()[:64]
    return (request.client.host if request.client else "unknown")[:64]


async def current_session(request: Request) -> SessionContext:
    s, dbs = settings(request), databases(request)
    async with dbs.rw.connect() as conn:
        try:
            ctx = await resolve_session(conn, s, request.cookies.get(s.session_cookie))
        finally:
            await conn.commit()
    request.state.session = ctx
    return ctx


def csrf_ok(request: Request, expected_hash: str | None) -> bool:
    """Doble envío: la cabecera debe ser igual a la cookie y, si hay sesión, al token ligado a ella."""
    s = settings(request)
    header, cookie = request.headers.get(s.csrf_header), request.cookies.get(s.csrf_cookie)
    if not same(header, cookie):
        return False
    return expected_hash is None or same(sha256(header), expected_hash)


def csrf_error() -> ApiError:
    return ApiError(403, "csrf_failed", "Falta o no coincide el token CSRF. Recarga la página e intenta de nuevo.")


async def session_with_csrf(request: Request, ctx: SessionContext = Depends(current_session)) -> SessionContext:
    """Para peticiones que cambian estado."""
    if not csrf_ok(request, ctx.csrf_token_hash):
        raise csrf_error()
    return ctx


def require_role(*roles: str):
    async def dep(ctx: SessionContext = Depends(current_session)) -> SessionContext:
        if ctx.role not in roles:
            raise forbidden()
        return ctx
    return dep


require_customer = require_role("customer")
require_analyst = require_role("analyst")
