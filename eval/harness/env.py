"""Base de evaluación aislada (nombre con "_test"), carga del dataset y limpieza por caso."""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
from dotenv import dotenv_values

REPO = Path(__file__).resolve().parents[2]
ENV = {**dotenv_values(REPO / ".env"), **os.environ}
APP_TABLES = ("voice_usage", "ticket_events", "feedback", "traces", "handoffs", "card_status_overrides", "dispute_cases", "idempotency_keys", "confirmation_tokens",
              "turns", "conversations", "sessions", "login_events", "users")


def _with(url: str, *, db: str | None = None, user: str | None = None, password: str | None = None) -> str:
    p = urlsplit(url)
    netloc = p.netloc if user is None else f"{user}:{password}@{p.netloc.rsplit('@', 1)[-1]}"
    return urlunsplit(p._replace(netloc=netloc, path=f"/{db}" if db else p.path))


def plain(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://")


def eval_urls() -> dict[str, str]:
    """admin (dueño), app (app_rw) y console (app_ro) de la base de evaluación."""
    base = ENV.get("EVAL_DATABASE_URL") or (_with(ENV["TEST_DATABASE_URL"], db="bank_eval_test") if ENV.get("TEST_DATABASE_URL") else None)
    if not base:
        raise SystemExit("falta EVAL_DATABASE_URL o TEST_DATABASE_URL (.env)")
    name = urlsplit(base).path.lstrip("/")
    if "_test" not in name:
        raise SystemExit(f"el harness solo corre contra bases cuyo nombre contiene '_test'; recibí '{name}'")
    return {"admin": base, "app": _with(base, user=ENV["APP_DB_USER"], password=ENV["APP_DB_PASSWORD"]),
            "console": _with(base, user=ENV["CONSOLE_DB_USER"], password=ENV["CONSOLE_DB_PASSWORD"]), "name": name}


def ensure_eval_db(urls: dict[str, str]) -> None:
    """Crea la base si falta, la migra y carga el dataset completo desde la DuckDB del pipeline si está vacía.
    Con EVAL_DATASET=synthetic carga el dataset sintético (CI) si la base está vacía."""
    from data_pipeline.config import DUCKDB_PATH, RAW_DATA_DIR
    from data_pipeline.etl import load_postgres
    from data_pipeline.run import migrate

    server = plain(_with(urls["admin"], db="postgres"))
    with psycopg.connect(server, autocommit=True) as c:
        if not c.execute("SELECT 1 FROM pg_database WHERE datname = %s", (urls["name"],)).fetchone():
            c.execute(f'CREATE DATABASE "{urls["name"]}"')
    migrate(urls["admin"])
    with psycopg.connect(plain(urls["admin"])) as c:
        n = c.execute("SELECT count(*) FROM ref.transactions").fetchone()[0]
    if ENV.get("EVAL_DATASET") == "synthetic":      # CI: dataset sintético (eval/synthetic/generate.py), nunca el real
        if n == 0:
            import tempfile
            from eval.synthetic.generate import load
            with tempfile.TemporaryDirectory(prefix="synthetic_") as tmp:
                load(urls["admin"], Path(tmp))
        return
    if n < 1_000_000:
        if not DUCKDB_PATH.exists():
            raise SystemExit(f"{urls['name']} no tiene el dataset y no existe {DUCKDB_PATH}: correr el pipeline primero")
        load_postgres.load_full(urls["admin"], DUCKDB_PATH, RAW_DATA_DIR)


def reset_app(conn) -> None:
    """Cada caso empieza con el esquema app vacío (aislamiento entre casos)."""
    conn.execute("TRUNCATE " + ", ".join(f"app.{t}" for t in APP_TABLES) + " RESTART IDENTITY CASCADE")
