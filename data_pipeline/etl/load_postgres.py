"""DuckDB (capa limpia) → PostgreSQL (esquema ref), con contratos, cuarentena y linaje en ops.

Carga completa:    TRUNCATE de ref + COPY en una sola transacción. Los lectores ven los datos
                   anteriores hasta el COMMIT (bloqueados durante la carga, por el TRUNCATE).
Carga incremental: reemplaza en ref.transactions solo las particiones (process_date) de los
                   archivos que PostgreSQL todavía no tiene (ops.etl_files).

Antes de escribir, cada fila pasa los contratos de data_pipeline/contracts/. Las que incumplen
una regla bloqueante van a ref.rejected_rows con el id de la regla y no se cargan. Si una tabla
supera REJECT_THRESHOLD de rechazos, la corrida se detiene sin tocar ref. Al final de cada
corrida se cuentan las filas de app que apuntan a IDs inexistentes en ref; si hay, la corrida
queda como 'warning'.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path

import duckdb
import pandas as pd
import psycopg

from backend.persistence.models import (
    REF_LOAD_ORDER, ref_customers, ref_daily_exchange_rates, ref_products, ref_transactions,
)
from data_pipeline.config import REPO, WORK_DIR
from data_pipeline.contracts.engine import evaluate, export_select, load_contracts
from data_pipeline.etl import build_duckdb, demo_customers
from data_pipeline.etl.build_duckdb import log

REJECT_THRESHOLD = 0.001  # 0,1 % por tabla
REF_TABLES = {"customers": ref_customers, "products": ref_products, "transactions": ref_transactions,
              "daily_exchange_rates": ref_daily_exchange_rates}
SCOPED = ("customers", "products", "transactions")   # tablas que se filtran por el subconjunto de clientes
REJECTED_COLS = ["etl_run_id", "table_name", "pk_value", "partition_date", "reason", "detail", "row_data"]

# Filas de app que apuntan a algo que no existe en ref (app no tiene FK hacia ref a propósito)
APP_ORPHAN_CHECKS = {
    "dispute_cases_transaction": """SELECT count(*) FROM app.dispute_cases d WHERE NOT EXISTS (
        SELECT 1 FROM ref.transactions t WHERE t.transaction_id = d.transaction_id AND t.customer_id = d.customer_id)""",
    "handoffs_customer": """SELECT count(*) FROM app.handoffs h WHERE NOT EXISTS (
        SELECT 1 FROM ref.customers c WHERE c.customer_id = h.customer_id)""",
    "card_status_overrides_product": """SELECT count(*) FROM app.card_status_overrides o WHERE NOT EXISTS (
        SELECT 1 FROM ref.products p WHERE p.product_id = o.product_id AND p.customer_id = o.customer_id)""",
    # usuarios de login activos cuyo cliente ya no está en ref (p. ej. tras recargar otro subconjunto)
    "users_customer": """SELECT count(*) FROM app.users u WHERE u.role = 'customer' AND u.is_active AND NOT EXISTS (
        SELECT 1 FROM ref.customers c WHERE c.customer_id = u.customer_id)""",
}


class LoadAborted(Exception):
    """Rechazos por encima del umbral: no se escribe nada en ref."""


# ------------------------------------------------------------------ utilidades

def pg_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://")


def git_info() -> tuple[str | None, bool | None]:
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=REPO, text=True).strip())
        return commit, dirty
    except Exception:
        return None, None


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def list_sha256(ids) -> str:
    """Huella de un conjunto de customer_id: sha256 de los IDs ordenados y unidos por salto de línea."""
    return hashlib.sha256("\n".join(sorted(ids)).encode()).hexdigest()


def data_columns(table) -> list:
    return [c for c in table.columns if c.name != "etl_run_id"]


def copy_csv(cur, table: str, columns: list[str], path: Path) -> int:
    cols = ", ".join(f'"{c}"' for c in columns)
    with cur.copy(f"COPY {table} ({cols}) FROM STDIN WITH (FORMAT csv, HEADER true)") as cp:
        with open(path, "rb") as f:
            while chunk := f.read(1 << 22):
                cp.write(chunk)
    return cur.rowcount


def app_orphans(cur) -> dict[str, int]:
    return {k: int(cur.execute(q).fetchone()[0]) for k, q in APP_ORPHAN_CHECKS.items()}


@contextmanager
def run_record(url: str, mode: str, params: dict, source_dir: Path, duckdb_path: Path):
    """Registra la corrida en ops.etl_runs (en su propia transacción, para que un fallo quede registrado)."""
    commit, dirty = git_info()
    with psycopg.connect(pg_url(url), autocommit=True) as c:
        run_id = c.execute(
            "INSERT INTO ops.etl_runs (mode, status, git_commit, git_dirty, source_dir, duckdb_path, customer_scope, params) "
            "VALUES (%s, 'running', %s, %s, %s, %s, %s, %s) RETURNING run_id",
            (mode, commit, dirty, str(source_dir), str(duckdb_path), params.get("customer_scope", "all"),
             json.dumps(params, default=str))).fetchone()[0]
    rec = {"run_id": run_id, "status": "success"}
    try:
        yield rec
    except Exception as e:
        with psycopg.connect(pg_url(url), autocommit=True) as c:
            c.execute("UPDATE ops.etl_runs SET status = 'failed', finished_at = now(), error = %s, counts = %s WHERE run_id = %s",
                      (f"{type(e).__name__}: {e}", json.dumps(rec.get("counts", {}), default=str), run_id))
        raise
    with psycopg.connect(pg_url(url), autocommit=True) as c:
        # chequeo de consistencia de app al final de TODA corrida (también las noop)
        orphans = app_orphans(c.cursor())
        status = "warning" if rec["status"] == "success" and any(orphans.values()) else rec["status"]
        if status == "warning":
            log(f"ADVERTENCIA: filas de app que apuntan a IDs inexistentes en ref: {orphans}")
        mx = c.execute("SELECT max(process_date), max(transaction_date) FROM ref.transactions").fetchone()
        c.execute("""UPDATE ops.etl_runs SET status = %s, finished_at = now(), duckdb_sha256 = %s, data_as_of = %s,
                     max_transaction_date = %s, counts = %s, partitions_replaced = %s, app_orphans = %s,
                     customer_rule = %s, customer_seed = %s, customer_list_sha256 = %s WHERE run_id = %s""",
                  (status, rec.get("duckdb_sha256"), mx[0], mx[1], json.dumps(rec.get("counts", {}), default=str),
                   json.dumps(rec.get("partitions"), default=str) if rec.get("partitions") is not None else None,
                   json.dumps(orphans), rec.get("customer_rule"), rec.get("customer_seed"),
                   rec.get("customer_list_sha256"), run_id))
    rec["status"] = status


def check_threshold(rej: pd.DataFrame, totals: dict[str, int]) -> dict:
    by_table = rej.groupby("table_name").n.sum().to_dict() if len(rej) else {}
    out = {t: {"rejected": int(by_table.get(t, 0)), "total": int(n),
               "pct": round(by_table.get(t, 0) / n * 100, 4) if n else 0.0} for t, n in totals.items()}
    over = {t: v for t, v in out.items() if v["total"] and v["rejected"] / v["total"] > REJECT_THRESHOLD}
    if over:
        raise LoadAborted(f"rechazos sobre el umbral de {REJECT_THRESHOLD:.1%}: {over}. Detalle: {rej.to_dict('records')}")
    return out


def orphan_report(con, scope_where: dict[str, str]) -> dict:
    """(a) transacciones con producto inexistente, (b) productos sin cliente,
    (c) transacciones cuyo cliente no es el dueño del producto."""
    tw, pw = scope_where.get("transactions", "TRUE"), scope_where.get("products", "TRUE")
    a, c_, n_tx = con.execute(f"""
        SELECT count(*) FILTER (WHERE p.product_id IS NULL),
               count(*) FILTER (WHERE p.customer_id <> t.customer_id), count(*)
        FROM (SELECT * FROM transactions WHERE {tw}) t LEFT JOIN products p USING (product_id)""").fetchone()
    b, n_p = con.execute(f"""SELECT count(*) FILTER (WHERE c.customer_id IS NULL), count(*)
        FROM (SELECT * FROM products WHERE {pw}) p LEFT JOIN customers c USING (customer_id)""").fetchone()
    return {"a_tx_product_not_found": a, "b_product_customer_not_found": b,
            "c_tx_customer_product_mismatch": c_, "transactions": n_tx, "products": n_p}


# ------------------------------------------------------------------ export

def export_table(con, contracts, t: str, relation: str, run_dir: Path) -> tuple[Path, list[str]]:
    ct = contracts[t]
    cols = data_columns(REF_TABLES[t])
    path = run_dir / f"{t}.csv"
    sql = export_select(ct, cols, relation) + \
        f" WHERE {ct.pk_expr()} NOT IN (SELECT pk_value FROM _rejected WHERE table_name = '{t}')"
    con.execute(f"COPY ({sql}) TO '{path}' (HEADER, DELIMITER ',', QUOTE '\"', NULL '', "
                f"TIMESTAMPFORMAT '%Y-%m-%d %H:%M:%S.%f')")
    return path, [c.name for c in cols]


def export_rejected(con, run_dir: Path, run_id: int) -> Path:
    path = run_dir / "rejected_rows.csv"
    con.execute(f"""COPY (SELECT {run_id} AS etl_run_id, table_name, pk_value, partition_date, reason, detail,
                            CAST(row_data AS VARCHAR) AS row_data FROM _rejected)
                   TO '{path}' (HEADER, NULL '')""")
    return path


def secondary_objects(cur, tables: list[str]) -> tuple[list[tuple[str, str, str]], list[tuple[str, str]]]:
    """Definiciones de FK/UNIQUE e índices no-PK de las tablas de ref (para soltarlos y recrearlos igual)."""
    qual = [f"ref.{t}" for t in tables]
    cons = cur.execute("""
        SELECT conrelid::regclass::text, conname, pg_get_constraintdef(oid), contype
        FROM pg_constraint WHERE conrelid::regclass::text = ANY(%s) AND contype IN ('f', 'u')""", (qual,)).fetchall()
    idx = cur.execute("""
        SELECT i.indexrelid::regclass::text, pg_get_indexdef(i.indexrelid) FROM pg_index i
        WHERE i.indrelid::regclass::text = ANY(%s) AND NOT i.indisprimary
          AND NOT EXISTS (SELECT 1 FROM pg_constraint c WHERE c.conindid = i.indexrelid)""", (qual,)).fetchall()
    return [(r[0], r[1], r[2]) for r in sorted(cons, key=lambda r: r[3] != "u")], idx


def record_files(cur, run_id: int, files: pd.DataFrame, action: str | None = None) -> None:
    cols = ["run_id", "table_name", "source_file", "partition_date", "sha256", "size_bytes", "rows", "rejected_rows",
            "action", "error"]
    with cur.copy(f"COPY ops.etl_files ({', '.join(cols)}) FROM STDIN") as cp:
        for r in files.itertuples(index=False):
            pdt = r.partition_date if pd.notna(r.partition_date) else None
            cp.write_row((run_id, r.table_name, r.source_file, pdt, r.sha256, int(r.size_bytes), int(r.rows),
                          int(r.rejected_rows), action or r.action, r.error if isinstance(r.error, str) else None))


def counts_by_layer(con, cur, tables=REF_LOAD_ORDER) -> dict:
    out = {}
    for t in tables:
        out[t] = {
            "csv": int(con.execute(f"SELECT coalesce(sum(rows), 0) FROM ingest_log WHERE table_name = '{t}'").fetchone()[0]),
            "raw": int(con.execute(f"SELECT count(*) FROM raw_{t}").fetchone()[0]),
            "clean": int(con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]),
            "ref": int(cur.execute(f"SELECT count(*) FROM ref.{t}").fetchone()[0]),
        }
    return out


def scope_filters(con, customers: list[str] | None) -> dict[str, str]:
    if customers is None:
        return {}
    con.execute("CREATE OR REPLACE TEMP TABLE _scope (customer_id VARCHAR PRIMARY KEY)")
    con.executemany("INSERT INTO _scope VALUES (?)", [(c,) for c in customers])
    missing = con.execute("SELECT count(*) FROM _scope WHERE customer_id NOT IN (SELECT customer_id FROM customers)").fetchone()[0]
    if missing:
        raise ValueError(f"{missing} customer_id de la lista no existen en customers")
    return {t: "customer_id IN (SELECT customer_id FROM _scope)" for t in SCOPED}


def relation(t: str, where: str) -> str:
    return f"(SELECT * FROM {t} WHERE {where})"


# ------------------------------------------------------------------ modos

def load_full(url: str, duckdb_path: Path, source_dir: Path, customers: list[str] | None = None,
              customer_scope: str = "all", demo_per_scenario: int = 2, params: dict | None = None,
              customer_rule: str | None = None, seed: int | None = None) -> int:
    con = duckdb.connect(str(duckdb_path), read_only=True)
    con.execute("SET enable_progress_bar = false")
    contracts = load_contracts()
    params = {**(params or {}), "customer_scope": customer_scope, "n_customers": len(customers) if customers else None,
              "contract_versions": {t: c.version for t, c in contracts.items()}}
    with run_record(url, "full", params, source_dir, duckdb_path) as rec:
        run_id = rec["run_id"]
        rec["customer_rule"] = customer_rule or "all: todos los clientes de la capa limpia"
        rec["customer_seed"] = seed
        scope = scope_filters(con, customers)
        rels = {t: relation(t, scope.get(t, "TRUE")) for t in REF_LOAD_ORDER}
        orphans = orphan_report(con, scope)
        log(f"huérfanos antes de cargar: {orphans}")
        rej, warnings = evaluate(con, contracts, rels)
        totals = {t: con.execute(f"SELECT count(*) FROM {rels[t]}").fetchone()[0] for t in REF_LOAD_ORDER}
        rec["counts"] = {"orphans": orphans, "contract_warnings": warnings}
        rejected = check_threshold(rej, totals)
        demo, ref_date = demo_customers.select_demo(con, demo_per_scenario, strict=False)
        if customers is not None:
            demo = demo[demo.customer_id.isin(set(customers))]

        run_dir = WORK_DIR / f"run_{run_id}"
        run_dir.mkdir(parents=True, exist_ok=True)
        exports = {t: export_table(con, contracts, t, rels[t], run_dir) for t in REF_LOAD_ORDER}
        rej_path = export_rejected(con, run_dir, run_id)
        log(f"exportado a {run_dir} | advertencias de contrato: {warnings}")

        with psycopg.connect(pg_url(url)) as pg, pg.cursor() as cur:
            cons, idx = secondary_objects(cur, list(REF_LOAD_ORDER) + ["demo_customers"])
            for rel, name, _ in reversed(cons):
                cur.execute(f'ALTER TABLE {rel} DROP CONSTRAINT "{name}"')
            for name, _ in idx:
                cur.execute(f"DROP INDEX {name}")
            cur.execute("TRUNCATE ref.demo_customers, ref.transactions, ref.products, ref.customers, "
                        "ref.daily_exchange_rates, ref.rejected_rows")
            for t in REF_LOAD_ORDER:
                path, cols = exports[t]
                # etl_run_id no viene del CSV: DEFAULT temporal de la corrida
                cur.execute(f"ALTER TABLE ref.{t} ALTER COLUMN etl_run_id SET DEFAULT {run_id}")
                n = copy_csv(cur, f"ref.{t}", cols, path)
                cur.execute(f"ALTER TABLE ref.{t} ALTER COLUMN etl_run_id DROP DEFAULT")
                log(f"ref.{t}: COPY {n:,} filas")
            copy_csv(cur, "ref.rejected_rows", REJECTED_COLS, rej_path)
            for name, ddl in idx:
                cur.execute(ddl)
            for rel, name, ddl in cons:   # UNIQUE primero, luego FK (validación en bloque)
                cur.execute(f'ALTER TABLE {rel} ADD CONSTRAINT "{name}" {ddl}')
            log("índices y FK recreados y validados")
            with cur.copy("COPY ref.demo_customers (customer_id, scenario, scenario_rank, reference_date) FROM STDIN") as cp:
                for r in demo.itertuples(index=False):
                    cp.write_row((r.customer_id, r.scenario, r.scenario_rank, r.reference_date))
            # ops.etl_files se escribe en la MISMA transacción que los datos: si un archivo figura ahí,
            # sus filas están en ref (la incremental se apoya en eso para saber qué falta)
            record_files(cur, run_id, con.execute("SELECT * FROM ingest_log").df(), "loaded")
            pg.commit()
            pg.autocommit = True
            for t in REF_LOAD_ORDER:
                cur.execute(f"ANALYZE ref.{t}")
            loaded_ids = [r[0] for r in cur.execute("SELECT customer_id FROM ref.customers")]
            rec["customer_list_sha256"] = list_sha256(loaded_ids)
            rec["counts"].update({"layers": counts_by_layer(con, cur), "rejected": rejected,
                                  "rejected_by_reason": rej.to_dict("records"), "demo_customers": len(demo),
                                  "reference_date": str(ref_date)})
        rec["duckdb_sha256"] = file_sha256(duckdb_path)
        shutil.rmtree(run_dir, ignore_errors=True)
        log(f"carga completa (run {run_id}): {rec['counts']['layers']}")
    con.close()
    return run_id


def pending_files(con, cur) -> pd.DataFrame:
    """Archivos de DuckDB (ingest_log) que PostgreSQL todavía no tiene con ese hash (ops.etl_files).

    Se compara contra ops.etl_files y no contra lo que acaba de cambiar en DuckDB: si una carga a
    PostgreSQL falló después de actualizar DuckDB, la siguiente corrida retoma esas particiones.
    """
    loaded = pd.DataFrame(cur.execute("""
        SELECT DISTINCT ON (table_name, source_file) table_name, source_file, sha256
        FROM ops.etl_files ORDER BY table_name, source_file, file_id DESC""").fetchall(),
        columns=["table_name", "source_file", "pg_sha256"])
    files = con.execute("SELECT * FROM ingest_log").df().merge(loaded, on=["table_name", "source_file"], how="left")
    files["action"] = ["new" if pd.isna(p) else "changed" for p in files.pg_sha256]
    return files[files.pg_sha256.isna() | (files.pg_sha256 != files.sha256)].drop(columns="pg_sha256")


def load_incremental(url: str, duckdb_path: Path, source_dir: Path, params: dict | None = None) -> int:
    """Reemplaza en ref.transactions solo las particiones (process_date) de los archivos pendientes."""
    con = duckdb.connect(str(duckdb_path), read_only=True)
    con.execute("SET enable_progress_bar = false")
    contracts = load_contracts()
    with psycopg.connect(pg_url(url)) as c0:
        files = pending_files(con, c0.cursor())
        last = c0.execute("""SELECT customer_scope, customer_rule, customer_seed, customer_list_sha256 FROM ops.etl_runs
                             WHERE mode = 'full' AND status IN ('success', 'warning') ORDER BY run_id DESC LIMIT 1""").fetchone()
    if files.partition_date.isna().any():
        raise build_duckdb.NeedsFullReload(f"archivos sin partición pendientes: {files[files.partition_date.isna()].source_file.tolist()}")
    parts = sorted({d.date() if hasattr(d, "date") else d for d in files[files.table_name == "transactions"].partition_date})
    params = {**(params or {}), "partitions": [str(p) for p in parts],
              "customer_scope": last[0] if last else "all", "contract_versions": {t: c.version for t, c in contracts.items()}}
    with run_record(url, "incremental", params, source_dir, duckdb_path) as rec:
        run_id = rec["run_id"]
        if last:  # el alcance de clientes lo fija la última carga completa
            rec["customer_rule"], rec["customer_seed"], rec["customer_list_sha256"] = last[1], last[2], last[3]
        rec["duckdb_sha256"] = file_sha256(duckdb_path)
        with psycopg.connect(pg_url(url)) as pg, pg.cursor() as cur:
            if files.empty:
                rec["status"], rec["partitions"], rec["counts"] = "noop", [], {"files": 0}
                log("incremental: sin archivos pendientes")
                con.close()
                return run_id
            rec["counts"] = {"customer_scope": params["customer_scope"]}
            if parts:
                # Contratos contra lo que YA está en PostgreSQL: clientes en alcance y productos cargados
                con.register("_pg_products", pd.DataFrame(cur.execute("SELECT product_id, customer_id FROM ref.products").fetchall(),
                                                          columns=["product_id", "customer_id"]))
                con.register("_pg_customers", pd.DataFrame(cur.execute("SELECT customer_id FROM ref.customers").fetchall(),
                                                           columns=["customer_id"]))
                # con subconjunto, las transacciones de clientes fuera de él se omiten (no son rechazos);
                # con carga total, un cliente desconocido es un rechazo
                pw = f"process_date IN ({', '.join(repr(str(p)) for p in parts)})"
                where = pw + (" AND customer_id IN (SELECT customer_id FROM _pg_customers)" if params["customer_scope"] != "all" else "")
                rel = relation("transactions", where)
                rej, warnings = evaluate(con, contracts, {"transactions": rel},
                                         parent_override={"products": "_pg_products", "customers": "_pg_customers"})
                # PK que ya existe en OTRA partición de ref: no se pisa, va a cuarentena
                ids = con.execute(f"SELECT transaction_id FROM {rel}").df().transaction_id.tolist()
                clash = pd.DataFrame(cur.execute(
                    "SELECT transaction_id, process_date FROM ref.transactions WHERE transaction_id = ANY(%s) AND NOT process_date = ANY(%s)",
                    (ids, parts)).fetchall(), columns=["transaction_id", "other_partition"])
                if len(clash):
                    con.register("_clash", clash)
                    con.execute(f"""INSERT INTO _rejected SELECT 'transactions', t.transaction_id, t.process_date,
                                    'duplicate_pk_other_partition', 'ya cargada en ' || c.other_partition, to_json(t)
                                    FROM {rel} t JOIN _clash c USING (transaction_id)
                                    WHERE t.transaction_id NOT IN (SELECT pk_value FROM _rejected)""")
                    rej = con.execute("SELECT table_name, reason, count(*) AS n FROM _rejected GROUP BY ALL ORDER BY ALL").df()
                rejected = check_threshold(rej, {"transactions": len(ids)})
                run_dir = WORK_DIR / f"run_{run_id}"
                run_dir.mkdir(parents=True, exist_ok=True)
                path, cols = export_table(con, contracts, "transactions", rel, run_dir)
                rej_path = export_rejected(con, run_dir, run_id)
                deleted = cur.execute("DELETE FROM ref.transactions WHERE process_date = ANY(%s)", (parts,)).rowcount
                cur.execute("DELETE FROM ref.rejected_rows WHERE table_name = 'transactions' AND partition_date = ANY(%s)", (parts,))
                cur.execute(f"ALTER TABLE ref.transactions ALTER COLUMN etl_run_id SET DEFAULT {run_id}")
                inserted = copy_csv(cur, "ref.transactions", cols, path)
                cur.execute("ALTER TABLE ref.transactions ALTER COLUMN etl_run_id DROP DEFAULT")
                copy_csv(cur, "ref.rejected_rows", REJECTED_COLS, rej_path)
                shutil.rmtree(run_dir, ignore_errors=True)
                log(f"ref.transactions: particiones {', '.join(map(str, parts))}: -{deleted:,} +{inserted:,} filas")
                rec["counts"].update({"deleted": deleted, "inserted": inserted, "rejected": rejected,
                                      "rejected_by_reason": rej.to_dict("records"), "contract_warnings": warnings})
            else:
                rec["counts"].update({"deleted": 0, "inserted": 0, "note": "cambios solo en tablas que no se cargan a PostgreSQL"})
            record_files(cur, run_id, files)
            pg.commit()
            cur.execute("ANALYZE ref.transactions")
            rec["counts"]["files"] = len(files)
            rec["counts"]["layers"] = counts_by_layer(con, cur, ("transactions",))
            rec["partitions"] = [str(p) for p in parts]
    con.close()
    return run_id
