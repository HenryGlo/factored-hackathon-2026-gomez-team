"""request_id por petición, contexto de log y una línea de acceso con ruta, estado y latencia.

- X-Request-ID: se acepta el del cliente o del proxy si es seguro (letras, números, guiones; ≤ 64); si no, se genera.
  Se devuelve en la respuesta para cruzar frontend, logs y trazas.
- La sesión se registra como hash de la cookie (16 hex), nunca la cookie.
- La ruta se registra como plantilla (/api/conversations/{conversation_id}/turns) y también el valor de conversation_id,
  que no es un dato del cliente.
"""
from __future__ import annotations

import logging
import re
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from backend.app.observability import logs
from backend.app.observability.metrics import EndpointMetrics
from backend.app.security import sha256

log = logging.getLogger("backend.access")
SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
HEADER = "X-Request-ID"


class RequestContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, metrics: EndpointMetrics, session_cookie: str):
        super().__init__(app)
        self.metrics, self.cookie = metrics, session_cookie

    async def dispatch(self, request: Request, call_next):
        incoming = request.headers.get(HEADER, "")
        rid = incoming if SAFE_ID.match(incoming) else uuid.uuid4().hex
        cookie = request.cookies.get(self.cookie)
        tokens = [logs.request_id.set(rid), logs.session_hash.set(sha256(cookie)[:16] if cookie else None),
                  logs.conversation_id.set(request.path_params.get("conversation_id") if hasattr(request, "path_params") else None),
                  logs.turn_id.set(None)]
        t0 = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers[HEADER] = rid
            return response
        finally:
            ms = round((time.perf_counter() - t0) * 1000, 1)
            route = getattr(request.scope.get("route"), "path", None) or "(sin ruta)"
            conv = request.scope.get("path_params", {}).get("conversation_id")
            if request.url.path.startswith("/api/"):
                self.metrics.record(request.method, route, status, ms)
                level = logging.WARNING if status >= 500 or status == 429 else logging.INFO
                log.log(level, "http_request", extra={"method": request.method, "route": route, "status": status, "latency_ms": ms,
                                                       **({"conversation_id": conv} if conv else {})})
            for var, tok in zip((logs.request_id, logs.session_hash, logs.conversation_id, logs.turn_id), tokens):
                var.reset(tok)
