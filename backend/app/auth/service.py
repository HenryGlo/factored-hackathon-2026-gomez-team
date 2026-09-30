"""Lógica de autenticación: login con límite de intentos, sesiones con vencimiento por inactividad."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from backend.app.config import Settings
from backend.app.errors import ApiError, session_expired, unauthorized
from backend.app.security import hash_password, needs_rehash, new_id, new_token, sha256, verify_password
from backend.persistence.models import app_login_events as events
from backend.persistence.models import app_sessions as sessions
from backend.persistence.models import app_users as users
from backend.persistence.models import ref_customers


def now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class SessionContext:
    """Identidad de la petición. El customer_id del backend sale SIEMPRE de aquí."""
    session_id: str
    user_id: str
    role: str
    customer_id: str | None
    language: str | None
    csrf_token_hash: str | None
    expires_at: datetime


@dataclass(frozen=True)
class LoginResult:
    token: str
    csrf_token: str
    context: SessionContext
    display_name: str


def rate_limited() -> ApiError:
    return ApiError(429, "rate_limited", "Demasiados intentos. Espera unos minutos y vuelve a intentar.",
                    retryable=True, headers={"Retry-After": "900"})


async def _recent_failures(conn: AsyncConnection, s: Settings, *, username: str | None = None, ip: str | None = None) -> int:
    """Fallos en la ventana; por usuario se cuentan solo los posteriores a su último login correcto."""
    since = now() - timedelta(minutes=s.login_window_minutes)
    cond = [events.c.success.is_(False), events.c.created_at > since]
    if username is not None:
        last_ok = select(func.max(events.c.created_at)).where(and_(events.c.username == username, events.c.success.is_(True)))
        cond += [events.c.username == username, events.c.created_at > func.coalesce(last_ok.scalar_subquery(), since)]
    if ip is not None:
        cond.append(events.c.ip == ip)
    return (await conn.execute(select(func.count()).select_from(events).where(and_(*cond)))).scalar_one()


async def _log(conn: AsyncConnection, username: str, ip: str, ua: str | None, success: bool, reason: str,
               user_id: str | None = None) -> None:
    await conn.execute(insert(events).values(username=username, user_id=user_id, ip=ip, user_agent=ua,
                                             success=success, reason=reason))


async def display_name_for(conn: AsyncConnection, role: str, customer_id: str | None, fallback: str | None) -> str:
    if role == "customer" and customer_id:
        name = (await conn.execute(select(ref_customers.c.display_name)
                                   .where(ref_customers.c.customer_id == customer_id))).scalar_one_or_none()
        return name or "Cliente"
    return fallback or "Analista"


async def login(conn: AsyncConnection, s: Settings, username: str, password: str, ip: str, ua: str | None,
                language: str | None) -> LoginResult:
    """Valida credenciales y crea la sesión. Errores genéricos: no revela si el usuario existe."""
    uname = username.strip().lower()
    # 1) límite de intentos ANTES de mirar la contraseña (por IP y por usuario)
    if await _recent_failures(conn, s, ip=ip) >= s.login_max_failures_ip:
        await _log(conn, uname, ip, ua, False, "locked_ip")
        raise rate_limited()
    if await _recent_failures(conn, s, username=uname) >= s.login_max_failures_user:
        await _log(conn, uname, ip, ua, False, "locked_user")
        raise rate_limited()
    # 2) credenciales (verifica contra un hash de relleno si el usuario no existe: mismo tiempo)
    row = (await conn.execute(select(users).where(func.lower(users.c.username) == uname))).mappings().first()
    ok = verify_password(password, row["password_hash"] if row else None)
    if not ok:
        await _log(conn, uname, ip, ua, False, "bad_credentials", row["user_id"] if row else None)
        raise ApiError(401, "invalid_credentials", "Usuario o contraseña incorrectos.")
    if not row["is_active"]:
        await _log(conn, uname, ip, ua, False, "inactive", row["user_id"])
        raise ApiError(401, "invalid_credentials", "Usuario o contraseña incorrectos.")
    if needs_rehash(row["password_hash"]):
        await conn.execute(update(users).where(users.c.user_id == row["user_id"]).values(password_hash=hash_password(password)))
    # 3) sesión nueva (token y CSRF solo como hash en la base)
    token, csrf = new_token(), new_token()
    t = now()
    ctx = SessionContext(session_id=new_id("ses"), user_id=row["user_id"], role=row["role"], customer_id=row["customer_id"],
                         language=language if language in ("es", "pt") else None, csrf_token_hash=sha256(csrf),
                         expires_at=t + timedelta(minutes=s.session_idle_minutes))
    await conn.execute(insert(sessions).values(
        session_id=ctx.session_id, token_hash=sha256(token), user_id=ctx.user_id, role=ctx.role,
        customer_id=ctx.customer_id, language=ctx.language, csrf_token_hash=ctx.csrf_token_hash, ip=ip,
        user_agent=ua, last_seen_at=t, expires_at=ctx.expires_at))
    await conn.execute(update(users).where(users.c.user_id == row["user_id"]).values(last_login_at=t))
    await _log(conn, uname, ip, ua, True, "ok", row["user_id"])
    name = await display_name_for(conn, row["role"], row["customer_id"], row["display_name"])
    return LoginResult(token=token, csrf_token=csrf, context=ctx, display_name=name)


async def resolve_session(conn: AsyncConnection, s: Settings, token: str | None) -> SessionContext:
    """Sesión de la cookie: válida, no revocada, no vencida por inactividad y de un usuario activo.

    Cada petición válida desliza el vencimiento (last_seen_at + SESSION_IDLE_MINUTES), sin pasar
    de SESSION_MAX_HOURS desde el login.
    """
    if not token:
        raise unauthorized()
    row = (await conn.execute(
        select(sessions, users.c.is_active).join(users, users.c.user_id == sessions.c.user_id)
        .where(sessions.c.token_hash == sha256(token)))).mappings().first()
    if row is None:
        raise unauthorized()
    t = now()
    if row["revoked_at"] is not None or not row["is_active"]:
        raise unauthorized("Tu sesión fue cerrada. Vuelve a iniciar sesión.")
    if row["expires_at"] <= t:
        raise session_expired()
    new_exp = min(t + timedelta(minutes=s.session_idle_minutes), row["created_at"] + timedelta(hours=s.session_max_hours))
    await conn.execute(update(sessions).where(sessions.c.session_id == row["session_id"])
                       .values(last_seen_at=t, expires_at=new_exp))
    return SessionContext(session_id=row["session_id"], user_id=row["user_id"], role=row["role"],
                          customer_id=row["customer_id"], language=row["language"],
                          csrf_token_hash=row["csrf_token_hash"], expires_at=new_exp)


async def logout(conn: AsyncConnection, ctx: SessionContext, ip: str, ua: str | None) -> None:
    await conn.execute(update(sessions).where(sessions.c.session_id == ctx.session_id).values(revoked_at=now()))
    uname = (await conn.execute(select(users.c.username).where(users.c.user_id == ctx.user_id))).scalar_one()
    await _log(conn, uname.lower(), ip, ua, True, "logout", ctx.user_id)
