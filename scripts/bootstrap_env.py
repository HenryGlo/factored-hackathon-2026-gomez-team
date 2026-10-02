"""Crea .env a partir de .env.example cuando no existe, con contraseñas generadas (solo para desarrollo local).

    python3 scripts/bootstrap_env.py [--env-file .env]

- Nunca sobrescribe un .env existente.
- Rellena los valores locales por defecto (PostgreSQL del contenedor en el puerto 5433) y genera contraseñas aleatorias para
  la base y para los usuarios demo. No imprime ninguna contraseña: quedan en el archivo, con permisos 600.
- Solo biblioteca estándar: corre antes de que exista el entorno virtual.
"""
from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def values() -> dict[str, str]:
    pw = {k: secrets.token_urlsafe(24) for k in ("POSTGRES_PASSWORD", "APP_DB_PASSWORD", "CONSOLE_DB_PASSWORD")}
    user, db, port, app, console = "bank", "bank", os.environ.get("POSTGRES_PORT", "5433"), "bank_app", "bank_console"
    url = lambda u, p, d: f"postgresql+psycopg://{u}:{p}@127.0.0.1:{port}/{d}"
    return {"POSTGRES_USER": user, "POSTGRES_DB": db, "POSTGRES_PORT": port, "APP_DB_USER": app, "CONSOLE_DB_USER": console, **pw,
            "DATABASE_URL": url(app, pw["APP_DB_PASSWORD"], db), "CONSOLE_DATABASE_URL": url(console, pw["CONSOLE_DB_PASSWORD"], db),
            "ADMIN_DATABASE_URL": url(user, pw["POSTGRES_PASSWORD"], db), "TEST_DATABASE_URL": url(user, pw["POSTGRES_PASSWORD"], "bank_test"),
            "DUCKDB_PATH": "data/bank.duckdb", "RAW_DATA_DIR": "dataset/data", "APP_ENV": "development",
            "DEMO_PASSWORD": secrets.token_urlsafe(12)}


def render(example: str, vals: dict[str, str]) -> str:
    """Rellena las claves conocidas y COMENTA las que quedan vacías: una variable vacía no es lo mismo que una ausente
    (el backend intentaría leer '' como número o fecha en vez de usar su valor por defecto)."""
    out = []
    for line in example.splitlines():
        key, sep, value = line.partition("=")
        if sep and not line.startswith("#") and not value.strip():
            line = f"{key}={vals[key]}" if key in vals else f"# {line}"
        out.append(line)
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env-file", type=Path, default=REPO / ".env")
    ap.add_argument("--example", type=Path, default=REPO / ".env.example")
    args = ap.parse_args(argv)
    if args.env_file.exists():
        print(f"{args.env_file.name} ya existe: no se toca")
        return 0
    args.env_file.write_text(render(args.example.read_text(encoding="utf-8"), values()), encoding="utf-8")
    args.env_file.chmod(0o600)
    print(f"creado {args.env_file.name} con contraseñas generadas (permisos 600). La contraseña de los usuarios demo es DEMO_PASSWORD de ese archivo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
