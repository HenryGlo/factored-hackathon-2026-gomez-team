"""Errores de la API con el formato de docs/api-contract.md: {"error": {code, message, retryable}}."""
from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse


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
