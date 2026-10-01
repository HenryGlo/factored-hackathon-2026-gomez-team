"""Cabeceras de seguridad en todas las respuestas de la API.

- La API devuelve JSON. La CSP del frontend la pone quien sirve los archivos estáticos (hosting o CDN): ver docs/security.md.
- Aquí la CSP es la más estricta (la API no sirve HTML), salvo en /docs y /redoc en desarrollo, que cargan scripts de un CDN.
  En producción esas rutas no existen.
- HSTS solo en producción (APP_ENV=production), detrás de HTTPS.
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
# CSP básica sugerida para el frontend estático (mismo origen que la API vía proxy o dominio propio); docs/security.md
FRONTEND_CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                "font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
HSTS = "max-age=31536000; includeSubDomains"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, production: bool):
        super().__init__(app)
        self.production = production

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        h = response.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
        if not request.url.path.startswith(("/docs", "/redoc", "/openapi.json")):
            h.setdefault("Content-Security-Policy", API_CSP)
        if request.url.path.startswith("/api/"):
            h.setdefault("Cache-Control", "no-store")         # respuestas con datos del cliente: no se cachean
        if self.production:
            h.setdefault("Strict-Transport-Security", HSTS)
        return response
