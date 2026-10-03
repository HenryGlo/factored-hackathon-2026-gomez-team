"""Errores de la API con el formato de docs/api-contract.md: {"error": {code, message, retryable}}."""
from __future__ import annotations

import logging
import traceback
from pathlib import Path

from fastapi import Request
from fastapi.responses import JSONResponse

LOG = logging.getLogger("backend.errors")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, retryable: bool = False, headers: dict | None = None,
                 details: dict | None = None):
        self.status, self.code, self.message, self.retryable, self.headers = status, code, message, retryable, headers
        self.details = details


def unauthorized(message: str = "Inicia sesión para continuar.") -> ApiError:
    return ApiError(401, "unauthorized", message)


def session_expired() -> ApiError:
    return ApiError(401, "session_expired", "Tu sesión venció. Vuelve a iniciar sesión.")


def forbidden() -> ApiError:
    return ApiError(403, "forbidden", "No tienes permiso para esta operación.")


def not_found() -> ApiError:
    # mismo error si el recurso no existe o no pertenece a la sesión (no se revela existencia)
    return ApiError(404, "not_found", "No encontrado.")


async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    body = {"code": exc.code, "message": exc.message, "retryable": exc.retryable} | ({"details": exc.details} if exc.details else {})
    return JSONResponse({"error": body},
                        status_code=exc.status, headers=exc.headers)


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Error no previsto: el cliente recibe el formato del contrato (500, reintentable) y el log guarda el tipo, el lugar
    (archivo:línea del backend) y la ruta, para verlo en el panel de admin sin entrar a los logs del hosting. El mensaje
    de la excepción se recorta: puede citar datos, así que no se guarda entero."""
    frames = [f"{Path(f.filename).name}:{f.lineno} {f.name}" for f in traceback.extract_tb(exc.__traceback__) if "/backend/" in f.filename]
    LOG.error("unhandled_error", extra={"exc_type": type(exc).__name__, "where": frames[-4:], "path": request.url.path,
                                        "detail": str(exc)[:160]})
    return JSONResponse({"error": {"code": "internal_error", "message": "Algo falló de nuestro lado. Intenta de nuevo en un momento.",
                                   "retryable": True}}, status_code=500)
