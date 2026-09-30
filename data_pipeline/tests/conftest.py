"""Configuración compartida de las pruebas del pipeline.

Reglas de aislamiento:
- Toda conexión de prueba pasa por `require_test_url`: si el nombre de la base no termina en
  `_test`, la sesión FALLA (no se salta). Ningún test puede tocar la base principal por error.
- Al iniciar la sesión, la base de pruebas se vacía y se migra. Además, cada test que usa
  `fixture_db` la vacía otra vez antes de empezar: nada se acumula entre tests ni entre corridas.
- Las pruebas de rendimiento usan otra base `_test` (PERF_TEST_DATABASE_URL, por defecto
  <servidor de TEST_DATABASE_URL>/bank_perf_test), que se carga con el dataset completo si hace falta.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from dotenv import dotenv_values

from data_pipeline.etl import build_duckdb, load_postgres
from data_pipeline.run import migrate

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "data_pipeline" / "fixtures" / "incremental"
_ENV = {**dotenv_values(REPO / ".env"), **os.environ}
TEST_URL = _ENV.get("TEST_DATABASE_URL")


def db_name(url: str) -> str:
    return urlsplit(url).path.lstrip("/")


def require_test_url(url: str | None) -> str:
    """Devuelve la URL solo si apunta a una base *_test; si no, hace fallar la prueba."""
    if not url:
        pytest.fail("falta TEST_DATABASE_URL (ver .env.example)", pytrace=False)
    if not db_name(url).endswith("_test"):
        pytest.fail(f"las pruebas solo pueden usar bases *_test; recibí '{db_name(url)}'", pytrace=False)
    return url


def with_db(url: str, name: str) -> str:
    p = urlsplit(url)
    return urlunsplit(p._replace(path=f"/{name}"))


def with_user(url: str, user: str, password: str) -> str:
    p = urlsplit(url)
    host = p.netloc.rsplit("@", 1)[-1]
    return urlunsplit(p._replace(netloc=f"{user}:{password}@{host}"))


PERF_URL = _ENV.get("PERF_TEST_DATABASE_URL") or (with_db(TEST_URL, "bank_perf_test") if TEST_URL else None)
# login del backend (grupo app_rw) contra la base de prueba, nunca contra la principal
APP_TEST_URL = (with_user(TEST_URL, _ENV["APP_DB_USER"], _ENV["APP_DB_PASSWORD"])
                if TEST_URL and _ENV.get("APP_DB_USER") and _ENV.get("APP_DB_PASSWORD") else None)


def pg(url: str | None = None):
    return psycopg.connect(load_postgres.pg_url(require_test_url(url or TEST_URL)), autocommit=True)


def overlay(src: Path, layer: str) -> None:
    shutil.copytree(FIXTURE / layer, src, dirs_exist_ok=True)


def reset_db(url: str) -> None:
    """Vacía los esquemas del proyecto de una base *_test y la deja migrada a head."""
    with pg(url) as c:
        c.execute("DROP SCHEMA IF EXISTS app, ops, ref CASCADE")
        c.execute("DROP TABLE IF EXISTS public.alembic_version")
    migrate(require_test_url(url))


@pytest.fixture(scope="session", autouse=True)
def clean_test_database():
    """Cada corrida de pytest empieza con la base de pruebas vacía y migrada."""
    for url in (TEST_URL, PERF_URL, APP_TEST_URL):
        if url:
            require_test_url(url)
    reset_db(TEST_URL)
    yield


@pytest.fixture()
def fixture_db(tmp_path):
    """Base de prueba vacía, migrada y con la carga completa del fixture base. Devuelve (carpeta fuente, DuckDB)."""
    reset_db(TEST_URL)
    src, db = tmp_path / "src", tmp_path / "fixture.duckdb"
    overlay(src, "base")
    build_duckdb.build_full(src, db)
    load_postgres.load_full(TEST_URL, db, src)
    return src, db
