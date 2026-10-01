"""Límites de peticiones por IP y por sesión, con ventana fija y almacenamiento en memoria.

- Un solo proceso: el contador vive en memoria. Con varias instancias detrás de un balanceador, cada una cuenta lo suyo; para
  un límite compartido hace falta un almacén común (Redis). La interfaz `Store` permite agregarlo sin tocar el middleware.
- La protección DDoS de red (volumen, SYN flood) es de la plataforma o del CDN, no de la aplicación (docs/security.md).
- La sesión se identifica por el SHA-256 de la cookie (no se guarda la cookie).
"""
from __future__ import annotations

import logging
import math
import re
import time
from dataclasses import dataclass

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from backend.app.protection.config import Limit, SecurityConfig
from backend.app.security import sha256

log = logging.getLogger("backend.protection")
EXEMPT = ("/api/health", "/api/ready")
TURNS = re.compile(r"^/api/conversations/[^/]+/turns$")


class MemoryStore:
    """Contadores por (regla, clave) en ventanas fijas; cada contador guarda cuándo vence y los vencidos se limpian."""

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.counts: dict[tuple[str, str, int], list] = {}      # (regla, clave, ventana) → [cuenta, vence]
        self._last_sweep = 0.0

    def hit(self, rule: str, key: str, lim: Limit) -> tuple[bool, int]:
        """Cuenta una petición. Devuelve (permitida, segundos hasta que se reinicia la ventana)."""
        now = self.clock()
        window = int(now // lim.window_seconds)
        ends = (window + 1) * lim.window_seconds
        entry = self.counts.setdefault((rule, key, window), [0, ends])
        entry[0] += 1
        if now - self._last_sweep > 60:
            self._last_sweep = now
            self.counts = {k: v for k, v in self.counts.items() if v[1] > now}
        return entry[0] <= lim.limit, max(1, math.ceil(ends - now))


@dataclass
class Rule:
    name: str
    scope: str            # ip | session


def rules_for(method: str, path: str) -> list[Rule]:
    rules = [Rule("ip_all", "ip"), Rule("session_all", "session")]
    if method == "POST" and path == "/api/auth/login":
        rules.append(Rule("login_ip", "ip"))
    elif method == "POST" and TURNS.match(path):
        rules += [Rule("turns_session", "session"), Rule("turns_ip", "ip")]
    elif method == "POST" and path == "/api/conversations":
        rules.append(Rule("conversations_session", "session"))
    return rules


def too_many(retry: int, rule: str) -> JSONResponse:
    return JSONResponse({"error": {"code": "rate_limited", "retryable": True, "details": {"rule": rule, "retry_after_seconds": retry},
                                   "message": f"Demasiadas solicitudes. Intenta de nuevo en {retry} segundos."}},
                        status_code=429, headers={"Retry-After": str(retry)})


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: SecurityConfig, ip_of, session_cookie: str, store: MemoryStore | None = None):
        super().__init__(app)
        self.config, self.ip_of, self.cookie = config, ip_of, session_cookie
        self.store = store or MemoryStore()

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if request.method == "OPTIONS" or path in EXEMPT or not path.startswith("/api/"):
            return await call_next(request)
        ip = self.ip_of(request)
        cookie = request.cookies.get(self.cookie)
        for rule in rules_for(request.method, path):
            key = ip if rule.scope == "ip" else (sha256(cookie)[:32] if cookie else None)
            if key is None:
                continue
            ok, retry = self.store.hit(rule.name, key, self.config.rate[rule.name])
            if not ok:
                log.warning("rate_limited", extra={"rule": rule.name, "scope": rule.scope, "path": path, "retry_after": retry})
                return too_many(retry, rule.name)
        return await call_next(request)
