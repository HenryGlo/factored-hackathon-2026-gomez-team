"""Punto de entrada único del pipeline: CSV → DuckDB → PostgreSQL.

    # carga completa (construye DuckDB desde los CSV, aplica migraciones y carga ref)
    python -m data_pipeline.run full

    # subconjunto determinista de clientes de demo (cubre todos los escenarios)
    python -m data_pipeline.run full --customers-sample 200

    # carga incremental: archivos nuevos o modificados → solo sus particiones (process_date)
    python -m data_pipeline.run incremental

    # conteos de huérfanos sin cargar nada
    python -m data_pipeline.run check

Rutas y conexión salen de .env (RAW_DATA_DIR, DUCKDB_PATH, ADMIN_DATABASE_URL); cada una se puede
sobrescribir por argumento.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import duckdb

from data_pipeline.config import DUCKDB_PATH, RAW_DATA_DIR, REPO, SEED
from data_pipeline.etl import build_duckdb, demo_customers, load_postgres


def migrate(url: str) -> None:
    """alembic upgrade head sobre `url` (la carga nunca corre contra un esquema viejo)."""
    subprocess.run([sys.executable, "-m", "alembic", "-c", str(REPO / "backend" / "alembic.ini"),
                    "-x", f"db_url={url}", "upgrade", "head"], check=True, cwd=REPO)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m data_pipeline.run", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["full", "incremental", "check"])
    ap.add_argument("--source", type=Path, default=RAW_DATA_DIR, help="carpeta de CSV (RAW_DATA_DIR)")
    ap.add_argument("--duckdb", type=Path, default=DUCKDB_PATH, help="base DuckDB (DUCKDB_PATH)")
    ap.add_argument("--database-url", default=os.environ.get("ADMIN_DATABASE_URL"), help="PostgreSQL con el dueño de los esquemas (ADMIN_DATABASE_URL)")
    ap.add_argument("--skip-build", action="store_true", help="full: reutiliza la base DuckDB existente")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--customers-sample", type=int, metavar="N", help="full: N clientes deterministas (semilla fija)")
    g.add_argument("--customers", type=Path, metavar="ARCHIVO", help="full: un customer_id por línea (no versionar)")
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args(argv)
    if args.mode != "check" and not args.database_url:
        ap.error("falta ADMIN_DATABASE_URL (ver .env.example) o --database-url")

    if args.mode == "check":
        con = duckdb.connect(str(args.duckdb), read_only=True)
        print(json.dumps(load_postgres.orphan_report(con, {}), indent=2))
        return 0

    migrate(args.database_url)
    if args.mode == "full":
        if not args.skip_build:
            build_duckdb.build_full(args.source, args.duckdb)
        customers, scope, rule, seed = None, "all", None, None
        if args.customers_sample:
            with duckdb.connect(str(args.duckdb), read_only=True) as con:
                customers, _, ref = demo_customers.sample_customers(con, args.customers_sample, args.seed)
            scope, seed = "sample", args.seed
            rule = demo_customers.rule_text(args.customers_sample, args.seed, ref)
        elif args.customers:
            customers = [line.strip() for line in args.customers.read_text().splitlines() if line.strip()]
            scope, rule = "list", f"list: archivo {args.customers.name} ({len(customers)} IDs)"
        run_id = load_postgres.load_full(args.database_url, args.duckdb, args.source, customers, scope,
                                         params={"customers_sample": args.customers_sample, "skip_build": args.skip_build},
                                         customer_rule=rule, seed=seed)
    else:
        build_duckdb.update(args.source, args.duckdb)
        run_id = load_postgres.load_incremental(args.database_url, args.duckdb, args.source)
    print(f"etl_run_id={run_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
