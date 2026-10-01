"""Pruebas del backend sobre la base de pruebas *_test (mismo guardia que el pipeline).

La sesión de pytest carga el fixture sintético (IDs FXT-*) en bank_test y crea usuarios de prueba.
La app se conecta con los usuarios de login reales (APP_DB_USER → app_rw, CONSOLE_DB_USER →
app_ro) contra la base de pruebas, así los permisos de base de datos también quedan probados.
"""
from __future__ import annotations

import psycopg
import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.security import hash_password
from data_pipeline.etl import build_duckdb, load_postgres
from data_pipeline.tests.conftest import TEST_URL, _ENV, overlay, require_test_url, reset_db, with_user

PASSWORD = "clave-de-prueba-123"   # solo para la base *_test
USERS = [  # (user_id, username, role, customer_id, display_name)
    ("usr_c1", "cliente_uno", "customer", "FXT-C001", None),
    ("usr_c2", "cliente_dos", "customer", "FXT-C002", None),
    ("usr_a1", "analista_prueba", "analyst", None, "Analista de prueba"),
    ("usr_off", "cliente_inactivo", "customer", "FXT-C003", None),
]


def admin():
    return psycopg.connect(load_postgres.pg_url(require_test_url(TEST_URL)), autocommit=True)


@pytest.fixture(scope="session")
def test_db(tmp_path_factory):
    """bank_test migrada, con el fixture base cargado y los usuarios de prueba."""
    reset_db(TEST_URL)
    tmp = tmp_path_factory.mktemp("fx")
    src, db = tmp / "src", tmp / "fixture.duckdb"
    overlay(src, "base")
    build_duckdb.build_full(src, db)
    load_postgres.load_full(TEST_URL, db, src)
    h = hash_password(PASSWORD)
    with admin() as c:
        for uid, uname, role, cid, name in USERS:
            c.execute("INSERT INTO app.users (user_id, username, password_hash, role, customer_id, display_name, is_active) "
                      "VALUES (%s, %s, %s, %s, %s, %s, %s)", (uid, uname, h, role, cid, name, uid != "usr_off"))
    return TEST_URL


def make_settings(**over) -> Settings:
    app_url = with_user(TEST_URL, _ENV["APP_DB_USER"], _ENV["APP_DB_PASSWORD"])
    console_url = with_user(TEST_URL, _ENV["CONSOLE_DB_USER"], _ENV["CONSOLE_DB_PASSWORD"])
    return Settings(database_url=require_test_url(app_url), console_database_url=require_test_url(console_url),
                    _env_file=None, **over)


@pytest.fixture()
def clean_auth(test_db):
    """Cada test empieza sin sesiones ni eventos de login (el límite de intentos no se arrastra)."""
    with admin() as c:
        c.execute("TRUNCATE app.feedback, app.traces, app.handoffs, app.card_status_overrides, app.dispute_cases, app.idempotency_keys, "
                  "app.confirmation_tokens, app.turns, app.conversations, app.sessions, app.login_events")
        c.execute("UPDATE app.users SET is_active = (user_id <> 'usr_off'), last_login_at = NULL")


@pytest.fixture()
def client(clean_auth):
    with TestClient(create_app(make_settings())) as c:
        yield c


def login(c: TestClient, username: str, password: str = PASSWORD, **extra):
    c.get("/api/auth/csrf")
    return c.post("/api/auth/login", json={"username": username, "password": password, **extra},
                  headers={"X-CSRF-Token": c.cookies.get("csrf_token", "")})


def csrf_headers(c: TestClient) -> dict:
    return {"X-CSRF-Token": c.cookies.get("csrf_token", "")}
