"""URLs de la app derivadas de la del dueño de la base (Render solo entrega una connection string).

Render da `ADMIN_DATABASE_URL` (usuario dueño, `postgresql://…`). La app no usa al dueño: usa `APP_DB_USER` (grupo
app_rw) y `CONSOLE_DB_USER` (grupo app_ro) con sus contraseñas, generadas por Render (`generateValue`). Este módulo arma
las tres URLs con el driver de SQLAlchemy (`postgresql+psycopg://`) sin imprimirlas.

    python infra/render/db_urls.py --export   # líneas `export VAR=…` para `eval` en start.sh / predeploy.sh
"""
from __future__ import annotations

import os
import shlex
import sys
from urllib.parse import quote, urlsplit, urlunsplit


def _driver(url: str) -> str:
    for prefix in ("postgresql+psycopg://", "postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    raise SystemExit("ADMIN_DATABASE_URL no es una URL de PostgreSQL")


def with_user(url: str, user: str, password: str) -> str:
    p = urlsplit(url)
    host = p.hostname or ""
    netloc = f"{quote(user, safe='')}:{quote(password, safe='')}@{host}" + (f":{p.port}" if p.port else "")
    return urlunsplit(p._replace(netloc=netloc))


def urls(env: dict[str, str]) -> dict[str, str]:
    admin = _driver(env["ADMIN_DATABASE_URL"])
    return {"ADMIN_DATABASE_URL": admin,
            "DATABASE_URL": env.get("DATABASE_URL") or with_user(admin, env["APP_DB_USER"], env["APP_DB_PASSWORD"]),
            "CONSOLE_DATABASE_URL": env.get("CONSOLE_DATABASE_URL") or with_user(admin, env["CONSOLE_DB_USER"], env["CONSOLE_DB_PASSWORD"])}


if __name__ == "__main__":
    if sys.argv[1:] != ["--export"]:
        raise SystemExit(__doc__)
    for k, v in urls(dict(os.environ)).items():
        print(f"export {k}={shlex.quote(v)}")
