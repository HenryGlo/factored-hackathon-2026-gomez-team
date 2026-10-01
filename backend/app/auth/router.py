"""Endpoints de autenticación: /api/auth/csrf, /login, /logout, /me."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from backend.app.auth import service
from backend.app.auth.deps import (client_ip, csrf_error, csrf_ok, current_session, databases, session_with_csrf,
                                   settings)
from backend.app.auth.service import SessionContext
from backend.app.errors import ApiError
from backend.app.security import new_token
from backend.persistence.models import app_users

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    model_config = {"extra": "forbid"}  # ni customer_id ni rol se aceptan del cliente
    username: str = Field(min_length=1, max_length=60)
    password: str = Field(min_length=1, max_length=200)
    language: str | None = Field(default=None, pattern="^(es|pt)$")


class SessionInfo(BaseModel):
    role: str
    display_name: str
    language: str | None
    expires_at: datetime
    idle_timeout_minutes: int


class LoginResponse(SessionInfo):
    csrf_token: str = Field(description="También va en la cookie csrf_token; enviarlo en la cabecera X-CSRF-Token.")


def _set_cookies(response: Response, request: Request, token: str | None, csrf: str) -> None:
    s = settings(request)
    if token is not None:
        response.set_cookie(s.session_cookie, token, httponly=True, secure=s.secure_cookies, samesite="lax", path="/")
    # legible por el frontend (lo copia en la cabecera); no da acceso sin la cookie de sesión
    response.set_cookie(s.csrf_cookie, csrf, httponly=False, secure=s.secure_cookies, samesite="lax", path="/")


@router.get("/csrf")
async def csrf(request: Request, response: Response) -> dict:
    """Token CSRF previo al login (doble envío). El login lo rota y lo liga a la sesión."""
    token = new_token()
    _set_cookies(response, request, None, token)
    return {"csrf_token": token}


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, request: Request, response: Response) -> LoginResponse:
    if not csrf_ok(request, None):
        raise csrf_error()
    s, dbs = settings(request), databases(request)
    async with dbs.rw.connect() as conn:
        try:
            res = await service.login(conn, s, body.username, body.password, client_ip(request),
                                      request.headers.get("user-agent"), body.language)
        except ApiError:
            await conn.commit()   # el evento de login fallido se registra igual
            raise
        await conn.commit()
    _set_cookies(response, request, res.token, res.csrf_token)
    return LoginResponse(role=res.context.role, display_name=res.display_name, language=res.context.language,
                         expires_at=res.context.expires_at, idle_timeout_minutes=s.session_idle_minutes,
                         csrf_token=res.csrf_token)


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, ctx: SessionContext = Depends(session_with_csrf)) -> Response:
    s, dbs = settings(request), databases(request)
    async with dbs.rw.begin() as conn:
        await service.logout(conn, ctx, client_ip(request), request.headers.get("user-agent"))
    response.status_code = 204
    response.delete_cookie(s.session_cookie, path="/")
    response.delete_cookie(s.csrf_cookie, path="/")
    return response


@router.get("/me", response_model=SessionInfo)
async def me(request: Request, ctx: SessionContext = Depends(current_session)) -> SessionInfo:
    s, dbs = settings(request), databases(request)
    async with dbs.rw.connect() as conn:
        fallback: str | None = (await conn.execute(select(app_users.c.display_name).where(app_users.c.user_id == ctx.user_id))).scalar_one()
        name = await service.display_name_for(conn, ctx.role, ctx.customer_id, fallback)
    return SessionInfo(role=ctx.role, display_name=name, language=ctx.language, expires_at=ctx.expires_at,
                       idle_timeout_minutes=s.session_idle_minutes)
