"""URLs de la app en Render derivadas de la connection string del dueño (infra/render/db_urls.py)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "infra" / "render"))
from db_urls import urls, with_user  # noqa: E402

ENV = {"ADMIN_DATABASE_URL": "postgresql://owner:own-pw@dpg-abc.internal:5432/bank", "APP_DB_USER": "bank_app",
       "APP_DB_PASSWORD": "p@ss/w:rd", "CONSOLE_DB_USER": "bank_console", "CONSOLE_DB_PASSWORD": "c0nsole"}


def test_app_urls_use_their_own_users_and_the_sqlalchemy_driver():
    u = urls(ENV)
    assert u["ADMIN_DATABASE_URL"] == "postgresql+psycopg://owner:own-pw@dpg-abc.internal:5432/bank"
    assert u["DATABASE_URL"] == "postgresql+psycopg://bank_app:p%40ss%2Fw%3Ard@dpg-abc.internal:5432/bank"   # contraseña escapada
    assert u["CONSOLE_DATABASE_URL"] == "postgresql+psycopg://bank_console:c0nsole@dpg-abc.internal:5432/bank"
    assert "own-pw" not in u["DATABASE_URL"] + u["CONSOLE_DATABASE_URL"]


def test_postgres_scheme_and_missing_port_are_accepted_and_explicit_urls_win():
    u = urls({**ENV, "ADMIN_DATABASE_URL": "postgres://owner:x@host/bank", "DATABASE_URL": "postgresql+psycopg://a:b@h/d"})
    assert u["ADMIN_DATABASE_URL"] == "postgresql+psycopg://owner:x@host/bank" and u["DATABASE_URL"] == "postgresql+psycopg://a:b@h/d"
    assert with_user("postgresql+psycopg://o:x@host/bank", "u", "p") == "postgresql+psycopg://u:p@host/bank"


def test_a_non_postgres_url_is_rejected():
    with pytest.raises(SystemExit):
        urls({**ENV, "ADMIN_DATABASE_URL": "mysql://x"})
