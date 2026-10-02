"""Deja la base local lista para la demo: datos y usuarios. Lo llama scripts/dev_up.sh; se puede correr solo.

    .venv/bin/python scripts/dev_data.py [--database-url URL] [--synthetic]

1. Datos: si ref.transactions está vacía, carga el dataset del reto con el pipeline (si RAW_DATA_DIR tiene los CSV) o, si no
   están, el dataset SINTÉTICO de eval/synthetic (515 clientes ficticios), para que cualquiera pueda correr el proyecto sin
   descargar nada. `--synthetic` fuerza el sintético. Nunca recarga una base que ya tiene datos.
2. Usuarios demo: si no hay ninguno activo, corre scripts/seed_demo_users.py (contraseña: DEMO_PASSWORD de .env).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import psycopg
from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def main(argv: list[str] | None = None) -> int:
    load_dotenv(REPO / ".env")
    ap = argparse.ArgumentParser()
    ap.add_argument("--database-url", default=os.environ.get("ADMIN_DATABASE_URL"))
    ap.add_argument("--synthetic", action="store_true", help="usar el dataset sintético aunque exista el del reto")
    args = ap.parse_args(argv)
    if not args.database_url:
        raise SystemExit("falta ADMIN_DATABASE_URL (.env)")
    plain = args.database_url.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(plain) as c:
        n = c.execute("SELECT count(*) FROM ref.transactions").fetchone()[0]
    if n:
        print(f"   datos: ya hay {n:,} movimientos; no se recarga".replace(",", "."))
    else:
        from data_pipeline.config import DUCKDB_PATH, RAW_DATA_DIR
        from data_pipeline.etl import build_duckdb, load_postgres
        has_dataset = RAW_DATA_DIR.exists() and any(RAW_DATA_DIR.rglob("*.csv"))
        if has_dataset and not args.synthetic:
            print(f"   datos: cargando el dataset del reto desde {RAW_DATA_DIR} (≈ 2 minutos)")
            if not DUCKDB_PATH.exists():
                build_duckdb.build_full(RAW_DATA_DIR, DUCKDB_PATH)
            load_postgres.load_full(args.database_url, DUCKDB_PATH, RAW_DATA_DIR)
        else:
            from eval.synthetic.generate import Gen
            print("   datos: no está el dataset del reto → cargando el dataset SINTÉTICO (clientes ficticios SYN-)")
            with tempfile.TemporaryDirectory(prefix="synthetic_") as tmp:
                src = Gen().build().write(Path(tmp) / "src")
                db = Path(tmp) / "synthetic.duckdb"
                build_duckdb.build_full(src, db)
                load_postgres.load_full(args.database_url, db, src)
    with psycopg.connect(plain) as c:
        users = c.execute("SELECT count(*) FROM app.users WHERE is_active AND username LIKE 'demo\\_%'").fetchone()[0]
    if users:
        print(f"   usuarios demo: {users} activos")
        return 0
    if not os.environ.get("DEMO_PASSWORD"):
        print("   usuarios demo: falta DEMO_PASSWORD en .env; no se crean")
        return 0
    return subprocess.run([sys.executable, str(REPO / "scripts" / "seed_demo_users.py"), "--database-url", args.database_url], cwd=REPO).returncode


if __name__ == "__main__":
    sys.exit(main())
