"""infra/render/roles.py con un dueño como el de Render: con CREATEROLE pero SIN superusuario, y corriendo dos veces
(cada despliegue vuelve a correrlo). El 2026-10-03 el segundo despliegue falló porque el ALTER ROLE mencionaba NOSUPERUSER."""
import sys
import uuid
from pathlib import Path

import psycopg
from psycopg import sql

from backend.tests.conftest import TEST_URL, admin

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "infra" / "render"))
import roles  # noqa: E402
from db_urls import with_user  # noqa: E402


def test_roles_script_is_idempotent_with_a_non_superuser_owner(test_db, monkeypatch):
    tag = uuid.uuid4().hex[:8]
    owner, app, console, pw = f"t_owner_{tag}", f"t_app_{tag}", f"t_console_{tag}", f"pw-{tag}"
    with admin() as c:
        c.execute(sql.SQL("CREATE ROLE {} LOGIN CREATEROLE NOSUPERUSER PASSWORD {}").format(sql.Identifier(owner), sql.Literal(pw)))
        # en Render el dueño creó app_rw / app_ro en el primer despliegue, así que tiene ADMIN sobre ellos
        c.execute(sql.SQL("GRANT app_rw, app_ro TO {} WITH ADMIN OPTION").format(sql.Identifier(owner)))
    try:
        owner_url = with_user(TEST_URL.replace("postgresql+psycopg://", "postgresql://"), owner, pw)
        for k, v in {"ADMIN_DATABASE_URL": owner_url, "APP_DB_USER": app, "APP_DB_PASSWORD": "a-" + tag,
                     "CONSOLE_DB_USER": console, "CONSOLE_DB_PASSWORD": "c-" + tag}.items():
            monkeypatch.setenv(k, v)
        assert roles.main() == 0                       # primer despliegue: crea
        monkeypatch.setenv("APP_DB_PASSWORD", "a2-" + tag)
        assert roles.main() == 0                       # siguiente despliegue: actualiza la contraseña sin tocar SUPERUSER
        with admin() as c:
            row = c.execute("SELECT rolsuper, rolcreaterole, rolcanlogin FROM pg_roles WHERE rolname = %s", (app,)).fetchone()
        assert row == (False, False, True)
        with psycopg.connect(with_user(TEST_URL.replace("postgresql+psycopg://", "postgresql://"), app, "a2-" + tag)) as c:
            assert c.execute("SELECT current_user").fetchone()[0] == app      # la contraseña nueva funciona
    finally:
        with admin() as c:
            for r in (app, console, owner):
                c.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(r)))
