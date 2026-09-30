"""Roles de base de datos: app_rw (backend) y app_ro (consola). Ninguno es superusuario.

Se prueban los privilegios de cada grupo con SET ROLE desde el dueño, sobre la base *_test ya
migrada y cargada con el fixture. Además se entra con el usuario de login del backend
(APP_DB_USER) a la base de prueba y se comprueba que no es superusuario ni dueño de los esquemas.
"""
from __future__ import annotations

import psycopg
import pytest

from data_pipeline.tests.conftest import APP_TEST_URL, pg, require_test_url


def as_role(role: str, sql: str) -> None:
    with pg() as c:
        c.execute(f"SET ROLE {role}")
        c.execute(sql)


@pytest.mark.parametrize("role", ["app_rw", "app_ro"])
def test_both_roles_read_ref_and_app(fixture_db, role):
    as_role(role, "SELECT count(*) FROM ref.transactions")
    as_role(role, "SELECT count(*) FROM app.dispute_cases")
    as_role(role, "SELECT max(max_transaction_date) FROM ops.etl_runs")   # aviso de frescura


@pytest.mark.parametrize("role, sql", [
    ("app_rw", "INSERT INTO ref.customers (customer_id, display_name, country, segment, customer_status, source_file, etl_run_id) "
               "VALUES ('X', 'X', 'México', 'Basic', 'Active', 'x', 0)"),
    ("app_rw", "UPDATE ref.transactions SET amount = 0"),
    ("app_rw", "TRUNCATE ref.transactions"),
    ("app_rw", "DELETE FROM ops.etl_runs"),
    ("app_rw", "CREATE TABLE app.nueva (x int)"),
    ("app_ro", "INSERT INTO app.sessions (session_id, token_hash, role, customer_id, expires_at) "
               "VALUES ('s', 'h', 'customer', 'FXT-C001', now())"),
    ("app_ro", "UPDATE app.dispute_cases SET status = 'anulado'"),
])
def test_forbidden_writes(fixture_db, role, sql):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        as_role(role, sql)


def test_app_rw_writes_app(fixture_db):
    as_role("app_rw", "INSERT INTO app.users (user_id, username, password_hash, role, customer_id) "
                      "VALUES ('usr_rw', 'usuario_rw', 'argon2-no-usado', 'customer', 'FXT-C001')")
    as_role("app_rw", "INSERT INTO app.sessions (session_id, token_hash, user_id, role, customer_id, expires_at) "
                      "VALUES ('ses_rw', 'hash_rw', 'usr_rw', 'customer', 'FXT-C001', now() + interval '1 hour')")
    as_role("app_rw", "INSERT INTO app.card_status_overrides (customer_id, product_id, status) VALUES ('FXT-C001', 'FXT-P001', 'Blocked')")


def test_backend_login_is_not_superuser(fixture_db):
    if not APP_TEST_URL:
        pytest.skip("sin APP_DB_USER / APP_DB_PASSWORD")
    with psycopg.connect(require_test_url(APP_TEST_URL).replace("postgresql+psycopg://", "postgresql://")) as c:
        user, is_super = c.execute("SELECT current_user, rolsuper FROM pg_roles WHERE rolname = current_user").fetchone()
        owns = c.execute("SELECT count(*) FROM pg_namespace WHERE nspname IN ('ref', 'app', 'ops') "
                         "AND nspowner = (SELECT oid FROM pg_roles WHERE rolname = current_user)").fetchone()[0]
        member_rw = c.execute("SELECT pg_has_role(current_user, 'app_rw', 'MEMBER')").fetchone()[0]
    assert not is_super and owns == 0 and member_rw, user
