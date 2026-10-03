"""Crea (si faltan) los roles de grupo app_rw / app_ro y los usuarios de login de la app en la base de Render.

Es el equivalente de infra/postgres/init/01-roles.sh para una base gestionada: se conecta con el dueño
(ADMIN_DATABASE_URL), es idempotente y actualiza la contraseña si cambió. Nunca imprime contraseñas ni URLs.
Si el dueño no puede crear roles (sin CREATEROLE), lo dice y termina con error: el despliegue no sigue.
"""
from __future__ import annotations

import os
import sys

import psycopg
from psycopg import sql

sys.path.insert(0, os.path.dirname(__file__))
from db_urls import urls  # noqa: E402


def main() -> int:
    env = dict(os.environ)
    admin = urls(env)["ADMIN_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
    logins = [(env["APP_DB_USER"], env["APP_DB_PASSWORD"], "app_rw"), (env["CONSOLE_DB_USER"], env["CONSOLE_DB_PASSWORD"], "app_ro")]
    with psycopg.connect(admin, autocommit=True) as c:
        can = c.execute("SELECT rolcreaterole OR rolsuper FROM pg_roles WHERE rolname = current_user").fetchone()
        if not (can and can[0]):
            print("el usuario dueño no puede crear roles (CREATEROLE); ver docs/deployment.md", file=sys.stderr)
            return 1
        for group in ("app_rw", "app_ro"):
            if not c.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (group,)).fetchone():
                c.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(group)))
        for user, password, group in logins:
            exists = c.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (user,)).fetchone()
            if exists:
                # en una base gestionada el dueño NO es superusuario: no puede mencionar SUPERUSER (ni para ponerlo en "no")
                # al modificar un rol. Al actualizar solo se tocan LOGIN y la contraseña; los demás atributos ya se fijaron al crearlo.
                c.execute(sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(sql.Identifier(user), sql.Literal(password)))
            else:
                c.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE").format(
                    sql.Identifier(user), sql.Literal(password)))
            c.execute(sql.SQL("GRANT {} TO {}").format(sql.Identifier(group), sql.Identifier(user)))
    print("roles listos: app_rw, app_ro y sus usuarios de login")
    return 0


if __name__ == "__main__":
    sys.exit(main())
