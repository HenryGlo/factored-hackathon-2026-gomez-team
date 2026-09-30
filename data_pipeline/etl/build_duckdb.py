"""CSV del dataset → base DuckDB (capa raw + capa limpia).

Movido y adaptado desde dashboard/scripts/build_db.py para que la base sea reproducible
desde el repo. Por cada tabla descubierta en la carpeta fuente (archivo suelto o carpeta
particionada year=/month=/day=):

    raw_<tabla>  tal cual llega (todo VARCHAR) + source_file + partition_date + ingest_run
    <tabla>      limpia: nulos normalizados, tipos del diccionario, deduplicada por PK,
                 enriquecida (customer_country, customer_segment, fecha y, en transactions,
                 usd_rate, amount_usd_filled y hora)
    ingest_log   un registro por archivo leído: ruta, sha256, bytes, filas, partición

Dos modos:
    build_full(source, db)   reconstruye todo en un archivo temporal y lo renombra al final
    update(source, db)       carga solo archivos nuevos o con hash distinto de tablas
                             particionadas y reconstruye solo sus particiones

Los agregados del dashboard exploratorio (agg_*) no se construyen aquí: siguen en
dashboard/scripts/build_db.py, que es material de análisis local.
"""
from __future__ import annotations

import hashlib
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

from data_pipeline.config import COUNTRY_FIX, DICTIONARY, FACT_TABLES, NULL_TOKENS, TABLES

EXTS = (".csv", ".csv.gz", ".parquet", ".json", ".jsonl")
HIVE_RE = re.compile(r"year=(\d{4})/month=(\d{1,2})/day=(\d{1,2})")
FILE_DATE_RE = re.compile(r"(\d{4})(\d{2})(\d{2})")
T0 = time.time()


class NeedsFullReload(Exception):
    """Cambió un archivo de una tabla sin particiones: la carga incremental no aplica."""


def log(msg: str) -> None:
    print(f"[{time.time() - T0:7.1f}s] {msg}", flush=True)


def qi(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def lit(v) -> str:
    return "'" + str(v).replace("'", "''") + "'"


# ------------------------------------------------------------------ descubrimiento y hashes

def discover(source: Path) -> dict[str, list[Path]]:
    tables = {}
    for entry in sorted(source.iterdir()):
        name = entry.name.lower()
        for ext in EXTS:
            if name.endswith(ext):
                name = name[: -len(ext)]
                break
        else:
            if not entry.is_dir():
                continue
        name = re.sub(r"[^a-z0-9_]", "_", name)
        files = [entry] if entry.is_file() else sorted(p for p in entry.rglob("*")
                                                       if p.is_file() and p.name.lower().endswith(EXTS))
        if files:
            tables[name] = files
    return tables


def partition_date(rel: str) -> date | None:
    m = HIVE_RE.search(rel) or FILE_DATE_RE.search(Path(rel).name)
    if not m:
        return None
    try:
        return date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return None


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def file_meta(files: list[Path], source: Path) -> pd.DataFrame:
    with ThreadPoolExecutor(max_workers=8) as ex:
        hashes = list(ex.map(sha256, files))
    rel = [f.relative_to(source).as_posix() for f in files]
    return pd.DataFrame({"path": [str(f) for f in files], "source_file": rel,
                         "partition_date": [partition_date(r) for r in rel], "sha256": hashes,
                         "size_bytes": [f.stat().st_size for f in files]})


def signature(path: Path) -> str:
    if path.name.lower().endswith((".csv", ".csv.gz")):
        opener = __import__("gzip").open if path.name.endswith(".gz") else open
        with opener(path, "rt", encoding="utf-8-sig", errors="replace") as f:
            return "csv:" + f.readline().strip()
    return path.suffix.lower()


# ------------------------------------------------------------------ raw

def read_raw(con, table: str, meta: pd.DataFrame, ingest_run: int) -> tuple[str, pd.DataFrame]:
    """Lee los archivos de `meta` (agrupados por cabecera) a una tabla temporal con linaje.

    Devuelve el nombre de la tabla temporal y el log por archivo (filas, rechazos, errores).
    """
    meta = meta.copy()
    meta["signature"] = [signature(Path(p)) for p in meta.path]
    meta["error"] = None
    sig_ids = {s: i for i, s in enumerate(meta.signature.unique())}
    meta["schema_id"] = meta.signature.map(sig_ids)

    parts, rejects = [], []
    for sig, grp in meta.groupby("signature", sort=False):
        gid = sig_ids[sig]
        paths = grp.path.tolist()
        tmp = f"_raw_{table}_{gid}"

        def reader(ps, suffix):
            plist = "[" + ",".join(lit(p) for p in ps) + "]"
            if sig.startswith("csv:"):
                return (f"read_csv({plist}, all_varchar=true, header=true, filename=true, hive_partitioning=false, "
                        f"store_rejects=true, rejects_table='_rej_{table}_{suffix}', "
                        f"rejects_scan='_rejscan_{table}_{suffix}')")
            if sig == ".parquet":
                return f"read_parquet({plist}, filename=true, union_by_name=true, hive_partitioning=false)"
            return f"read_json_auto({plist}, filename=true, union_by_name=true)"

        try:
            con.execute(f"CREATE OR REPLACE TEMP TABLE {tmp} AS SELECT * FROM {reader(paths, gid)}")
            parts.append(tmp)
            if sig.startswith("csv:"):
                rejects.append(f"_rej_{table}_{gid}")
        except Exception as e:  # un archivo roto no tumba el grupo: reintento archivo a archivo
            log(f"  {table}: grupo {gid} falló ({str(e)[:120]}); reintento por archivo")
            for j, p in enumerate(paths):
                sub = f"{tmp}_{j}"
                try:
                    con.execute(f"CREATE OR REPLACE TEMP TABLE {sub} AS SELECT * FROM {reader([p], f'{gid}_{j}')}")
                    parts.append(sub)
                    if sig.startswith("csv:"):
                        rejects.append(f"_rej_{table}_{gid}_{j}")
                except Exception as e2:
                    meta.loc[meta.path == p, "error"] = f"{type(e2).__name__}: {str(e2)[:300]}"

    con.register("_files", meta[["path", "source_file", "partition_date"]])
    union = " UNION ALL BY NAME ".join(f"SELECT * FROM {p}" for p in parts)
    out = f"_new_raw_{table}"
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE {out} AS
        SELECT u.* EXCLUDE (filename), f.source_file, CAST(f.partition_date AS DATE) AS partition_date,
               {ingest_run}::INTEGER AS ingest_run
        FROM ({union}) u JOIN _files f ON f.path = u.filename""")
    con.unregister("_files")

    frames = []
    for r in rejects:
        scan = r.replace("_rej_", "_rejscan_")
        try:
            frames.append(con.execute(f"""
                SELECT s.file_path AS path, COUNT(*) AS rejected_rows, ANY_VALUE(r.error_message) AS reject_example
                FROM {r} r JOIN {scan} s USING (scan_id, file_id) GROUP BY 1""").df())
        except Exception:
            pass
    rej = pd.concat(frames) if frames else pd.DataFrame(columns=["path", "rejected_rows", "reject_example"])
    counts = con.execute(f"SELECT source_file, COUNT(*) AS rows FROM {out} GROUP BY 1").df()
    log_df = (meta.merge(counts, on="source_file", how="left").merge(rej, on="path", how="left")
              .assign(table_name=table, ingest_run=ingest_run, loaded_at=pd.Timestamp.now(tz="UTC"),
                      rows=lambda d: d.rows.fillna(0).astype("int64"),
                      rejected_rows=lambda d: d.rejected_rows.fillna(0).astype("int64")))
    for p in parts:
        con.execute(f"DROP TABLE IF EXISTS {p}")
    return out, log_df[INGEST_LOG_COLS]


INGEST_LOG_COLS = ["table_name", "source_file", "partition_date", "sha256", "size_bytes", "schema_id", "signature",
                   "rows", "rejected_rows", "reject_example", "error", "ingest_run", "loaded_at"]


# ------------------------------------------------------------------ limpieza

def sniff_types(con, files: list[str]) -> dict[str, str]:
    """Tipos que DuckDB infiere sobre una muestra de archivos (para columnas fuera del diccionario)."""
    sample = files[:: max(1, len(files) // 15)][:15]
    plist = "[" + ",".join(lit(p) for p in sample) + "]"
    try:
        if sample[0].endswith(".parquet"):
            src = f"read_parquet({plist}, union_by_name=true)"
        elif sample[0].endswith((".json", ".jsonl")):
            src = f"read_json_auto({plist}, union_by_name=true)"
        else:
            src = f"read_csv({plist}, union_by_name=true, sample_size=50000, hive_partitioning=false)"
        return {r[0]: r[1] for r in con.execute(f"DESCRIBE SELECT * FROM {src}").fetchall()}
    except Exception:
        return {}


def col_expr(col: str, typ: str, country_col: bool) -> str:
    s = f"CAST({qi(col)} AS VARCHAR)"
    norm = f"CASE WHEN lower(trim({s})) IN ({','.join(lit(t) for t in NULL_TOKENS)}) THEN NULL ELSE trim({s}) END"
    typ = typ.upper()
    if typ in ("VARCHAR", "TEXT"):
        if country_col:
            cases = " ".join(f"WHEN {lit(k)} THEN {lit(v)}" for k, v in COUNTRY_FIX.items())
            return f"CASE ({norm}) {cases} ELSE ({norm}) END"
        return norm
    if typ in ("INTEGER", "BIGINT"):
        return f"CAST(round(TRY_CAST({norm} AS DOUBLE)) AS BIGINT)"
    if typ in ("DOUBLE", "FLOAT") or typ.startswith("DECIMAL"):
        return f"TRY_CAST({norm} AS DOUBLE)"
    return f"TRY_CAST({norm} AS {typ})"


def clean_types(con, table: str, files: list[str]) -> dict[str, str]:
    raw_cols = [r[0] for r in con.execute(f"DESCRIBE raw_{table}").fetchall()
                if r[0] not in ("source_file", "partition_date", "ingest_run")]
    sniffed = sniff_types(con, files)
    dic = DICTIONARY.get(table, {})
    return {c: dic.get(c) or sniffed.get(c, "VARCHAR") for c in raw_cols}


def clean_select(con, table: str, types: dict[str, str], where: str = "TRUE") -> str:
    """SELECT que produce las filas limpias de `table` a partir de raw_<tabla> filtrado por `where`."""
    cfg = TABLES.get(table, {})
    cols = list(types)
    exprs = [f"{col_expr(c, t, 'country' in c)} AS {qi(c)}" for c, t in types.items()]
    pk = [c for c in (cfg.get("pk") or []) if c in cols]
    order = cfg.get("order")
    order_sql = ", ".join(([f"{qi(order)} DESC NULLS LAST"] if order in cols else [])
                          + ["ingest_run DESC", "partition_date DESC NULLS LAST", "source_file DESC"])
    dedup = (f"QUALIFY ROW_NUMBER() OVER (PARTITION BY {', '.join(qi(c) for c in pk)} ORDER BY {order_sql}) = 1"
             if pk else "")
    dcol = cfg.get("date")
    fecha = f", CAST({qi(dcol)} AS DATE) AS fecha" if dcol in cols else ""
    typed = f"""SELECT *{fecha} FROM (
        SELECT {', '.join(exprs)}, partition_date, ingest_run, source_file
        FROM raw_{table} WHERE {where} {dedup}) x"""

    have = {r[0] for r in con.execute("SELECT table_name FROM duckdb_tables()").fetchall()}
    joins, extra = "", ""
    if table != "customers" and "customer_id" in cols and "customers" in have:
        joins += (" LEFT JOIN (SELECT customer_id AS _cid, country AS customer_country, segment AS customer_segment"
                  " FROM customers) cu ON cu._cid = t.customer_id")
        extra += ", cu.customer_country, cu.customer_segment"
    if table == "transactions" and "daily_exchange_rates" in have and {"amount", "currency"} <= set(cols):
        joins += """ ASOF LEFT JOIN (SELECT date AS _rdate, source_currency AS _rcur, exchange_rate AS _rate
                     FROM daily_exchange_rates WHERE target_currency = 'USD') r
                     ON r._rcur = t.currency AND t.fecha >= r._rdate"""
        extra += """, r._rate AS usd_rate,
                    CASE WHEN t.currency = 'USD' THEN t.amount
                         ELSE COALESCE(t.amount_usd, t.amount * r._rate) END AS amount_usd_filled"""
    if table == "transactions" and "transaction_date" in cols:
        extra += ", hour(t.transaction_date) AS hora"
    return f"SELECT t.* {extra} FROM ({typed}) t {joins}"


def cast_failures(con, table: str, types: dict[str, str]) -> list[dict]:
    """Valores presentes que no se pudieron tipar (quedan NULL en la tabla limpia)."""
    checks = [c for c, t in types.items() if t.upper() not in ("VARCHAR", "TEXT")]
    if not checks:
        return []
    sel = ", ".join(f"COUNT(*) FILTER (WHERE n_{i} IS NOT NULL AND t_{i} IS NULL), "
                    f"ANY_VALUE(n_{i}) FILTER (WHERE n_{i} IS NOT NULL AND t_{i} IS NULL)" for i, _ in enumerate(checks))
    inner = ", ".join(f"{col_expr(c, 'VARCHAR', False)} AS n_{i}, {col_expr(c, types[c], False)} AS t_{i}"
                      for i, c in enumerate(checks))
    row = con.execute(f"SELECT {sel} FROM (SELECT {inner} FROM raw_{table})").fetchone()
    return [dict(table_name=table, column_name=c, target_type=types[c], n_failed=int(row[2 * i]),
                 example=row[2 * i + 1]) for i, c in enumerate(checks)]


def build_order(tables) -> list[str]:
    # dimensiones primero: customers y tasas alimentan el enriquecimiento de los hechos
    return sorted(tables, key=lambda t: (t != "customers", t != "daily_exchange_rates", t in FACT_TABLES, t))


# ------------------------------------------------------------------ modos

def build_full(source: Path, db: Path, threads: int | None = None) -> dict:
    """Reconstruye la base completa desde los CSV. Atómico: escribe en temporal y renombra."""
    source, db = Path(source).resolve(), Path(db).resolve()
    db.parent.mkdir(parents=True, exist_ok=True)
    tmp = db.with_suffix(".building.duckdb")
    for p in (tmp, Path(str(tmp) + ".wal")):
        p.unlink(missing_ok=True)

    found = discover(source)
    log(f"Origen: {source} | tablas: {', '.join(f'{t} ({len(f)})' for t, f in found.items())}")
    con = duckdb.connect(str(tmp))
    con.execute(f"PRAGMA threads={threads or os.cpu_count() or 4}")
    con.execute("SET preserve_insertion_order = false")
    con.execute("SET enable_progress_bar = false")

    logs, fails, type_rows = [], [], []
    for t, files in found.items():
        meta = file_meta(files, source)
        new, lg = read_raw(con, t, meta, ingest_run=1)
        con.execute(f"CREATE OR REPLACE TABLE raw_{t} AS SELECT * FROM {new}")
        con.execute(f"DROP TABLE {new}")
        logs.append(lg)
        log(f"raw_{t}: {con.execute(f'SELECT COUNT(*) FROM raw_{t}').fetchone()[0]:,} filas")
    con.register("_log", pd.concat(logs, ignore_index=True))
    con.execute("CREATE OR REPLACE TABLE ingest_log AS SELECT * FROM _log")
    con.unregister("_log")

    for t in build_order(found):
        types = clean_types(con, t, [str(f) for f in found[t]])
        con.execute(f"CREATE OR REPLACE TABLE {t} AS {clean_select(con, t, types)}")
        fails += cast_failures(con, t, types)
        type_rows += [dict(table_name=t, column_name=c, type=ty) for c, ty in types.items()]
        log(f"{t}: {con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]:,} filas limpias")
    con.register("_cf", pd.DataFrame(fails, columns=["table_name", "column_name", "target_type", "n_failed", "example"]))
    con.execute("CREATE OR REPLACE TABLE cast_failures AS SELECT * FROM _cf")
    con.register("_ty", pd.DataFrame(type_rows))
    con.execute("CREATE OR REPLACE TABLE clean_types AS SELECT * FROM _ty")
    con.execute(f"CREATE OR REPLACE TABLE build_info AS SELECT now() AS built_at, {lit(source)} AS source_dir, "
                f"{time.time() - T0:.1f} AS seconds, 1 AS last_ingest_run")
    con.execute("CHECKPOINT")
    con.close()
    os.replace(tmp, db)
    log(f"Listo: {db} ({db.stat().st_size / 1e9:.2f} GB)")
    return {t: {"files": len(f)} for t, f in found.items()}


def update(source: Path, db: Path) -> dict:
    """Carga incremental: archivos nuevos o modificados de tablas particionadas.

    Devuelve {tabla: {"files": DataFrame de ingest_log, "partitions": [fechas afectadas]}}.
    Correr dos veces sobre la misma carpeta no cambia nada (no hay archivos nuevos).
    """
    source, db = Path(source).resolve(), Path(db).resolve()
    found = discover(source)
    con = duckdb.connect(str(db))
    con.execute("SET enable_progress_bar = false")
    known = con.execute("SELECT table_name, source_file, sha256, partition_date FROM ingest_log").df()
    run = con.execute("SELECT last_ingest_run FROM build_info").fetchone()[0] + 1
    changes = {}
    for t, files in found.items():
        meta = file_meta(files, source)
        k = known[known.table_name == t][["source_file", "sha256"]].rename(columns={"sha256": "old_sha"})
        m = meta.merge(k, on="source_file", how="left")
        m["action"] = ["new" if pd.isna(o) else ("changed" if o != s else "unchanged") for o, s in zip(m.old_sha, m.sha256)]
        todo = m[m.action != "unchanged"]
        if todo.empty:
            continue
        if todo.partition_date.isna().any():
            raise NeedsFullReload(f"{t}: cambió un archivo sin partición ({todo.source_file.iloc[0]}); correr carga completa")
        changes[t] = todo
    if not changes:
        con.close()
        log("sin archivos nuevos ni modificados: nada que hacer")
        return {}

    types_all = con.execute("SELECT * FROM clean_types").df()
    out = {}
    con.execute("BEGIN TRANSACTION")
    try:
        for t in build_order(changes):
            todo = changes[t]
            parts = sorted(set(todo.partition_date))
            plist = ", ".join(f"DATE {lit(p)}" for p in parts)
            flist = ", ".join(lit(f) for f in todo.source_file)
            new, lg = read_raw(con, t, todo.drop(columns=["old_sha", "action"]), ingest_run=run)
            con.execute(f"DELETE FROM raw_{t} WHERE source_file IN ({flist})")
            con.execute(f"INSERT INTO raw_{t} BY NAME SELECT * FROM {new}")
            con.execute(f"DROP TABLE {new}")
            con.execute(f"DELETE FROM ingest_log WHERE table_name = {lit(t)} AND source_file IN ({flist})")
            con.register("_lg", lg)
            con.execute("INSERT INTO ingest_log BY NAME SELECT * FROM _lg")
            con.unregister("_lg")
            types = dict(types_all[types_all.table_name == t][["column_name", "type"]].values)
            con.execute(f"DELETE FROM {t} WHERE partition_date IN ({plist})")
            con.execute(f"INSERT INTO {t} BY NAME {clean_select(con, t, types, f'partition_date IN ({plist})')}")
            lg["action"] = todo.set_index("source_file").loc[lg.source_file, "action"].values
            out[t] = {"files": lg, "partitions": parts}
            log(f"{t}: {len(todo)} archivos ({', '.join(todo.action)}) → particiones {', '.join(map(str, parts))}")
        con.execute(f"UPDATE build_info SET last_ingest_run = {run}")
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()
    return out
