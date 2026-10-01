"""Logs en JSON, una línea por evento, con el contexto de la petición.

- Contexto: request_id, session (hash), conversation_id, turn_id y trace_id. Se toma de contextvars, así cualquier log
  dentro de una petición lo lleva sin pasarlo a mano.
- **Nunca** se escriben contraseñas, tokens, cookies, cabeceras de autorización ni el texto del cliente. Los campos con
  esos nombres se reemplazan por "[oculto]". El texto completo ya queda en app.turns y app.traces, con su propio control
  de acceso.
- LOG_FORMAT=json (por defecto) o text (desarrollo); LOG_LEVEL=INFO.
"""
from __future__ import annotations

import contextvars
import json
import logging
import os
import sys
from datetime import datetime, timezone

request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
session_hash: contextvars.ContextVar[str | None] = contextvars.ContextVar("session_hash", default=None)
conversation_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("conversation_id", default=None)
turn_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("turn_id", default=None)

SENSITIVE = {"password", "contraseña", "token", "confirmation_token", "cookie", "cookies", "authorization", "set-cookie",
             "message", "mensaje", "text", "texto", "claim", "customer_statement", "api_key", "x-csrf-token", "csrf"}
STANDARD = set(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {"message", "asctime", "taskName"}


def redact(value):
    if isinstance(value, dict):
        return {k: "[oculto]" if str(k).lower() in SENSITIVE else redact(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    return value


def context() -> dict:
    ctx = {"request_id": request_id.get(), "session": session_hash.get(), "conversation_id": conversation_id.get(),
           "turn_id": turn_id.get()}
    if ctx["turn_id"]:
        ctx["trace_id"] = ctx["turn_id"]           # trace_id = turn_id (GET /api/traces/{turn_id})
    return {k: v for k, v in ctx.items() if v}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {"ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
               "level": record.levelname.lower(), "logger": record.name, "event": record.getMessage(), **context()}
        extra = {k: v for k, v in vars(record).items() if k not in STANDARD and not k.startswith("_")}
        out.update(redact(extra))
        if record.exc_info:
            out["error"] = self.formatException(record.exc_info).splitlines()[-1]       # solo la última línea, sin datos
        return json.dumps(out, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        extra = redact({k: v for k, v in vars(record).items() if k not in STANDARD and not k.startswith("_")})
        ctx = " ".join(f"{k}={v}" for k, v in {**context(), **extra}.items())
        return f"{datetime.now().strftime('%H:%M:%S')} {record.levelname:7s} {record.name} {record.getMessage()} {ctx}".rstrip()


def configure_logging(fmt: str | None = None, level: str | None = None) -> None:
    fmt = (fmt or os.environ.get("LOG_FORMAT") or "json").lower()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if fmt == "json" else TextFormatter())
    root = logging.getLogger("backend")
    root.handlers[:] = [handler]
    root.setLevel((level or os.environ.get("LOG_LEVEL") or "INFO").upper())
    root.propagate = False
    # el access log de uvicorn duplica el nuestro y no lleva request_id
    logging.getLogger("uvicorn.access").disabled = True
