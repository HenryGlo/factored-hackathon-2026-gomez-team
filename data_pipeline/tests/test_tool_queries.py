"""Tiempos de las consultas de las tools sobre el volumen real, con los privilegios del backend.

Corre contra una base de prueba propia (PERF_TEST_DATABASE_URL, por defecto bank_perf_test), nunca
contra la principal. Si esa base no tiene el dataset completo, la carga desde la base DuckDB del
pipeline (DUCKDB_PATH, ~40 s); si la DuckDB no existe, la prueba se salta. Las consultas corren
con SET ROLE app_rw (los mismos privilegios que el usuario del backend). Mide 200 clientes elegidos
de forma determinista (md5 del customer_id), con caché caliente, y exige p95 < 25 ms por consulta
(latencia vista desde el cliente). Imprime p50/p95/máx para docs/data/postgres.md.

    .venv/bin/pytest data_pipeline/tests/test_tool_queries.py -s
"""
from __future__ import annotations

import time

import numpy as np
import pytest

from data_pipeline.config import DUCKDB_PATH, RAW_DATA_DIR
from data_pipeline.etl import load_postgres
from data_pipeline.run import migrate
from data_pipeline.tests.conftest import PERF_URL, TEST_URL, db_name, pg, require_test_url

P95_MS = 25.0
N_CUSTOMERS = 200

QUERIES = {
    "search_transactions (ventana 90 d)": """
        SELECT transaction_id, transaction_date, amount, currency, merchant_name, channel, transaction_type,
               transaction_status, product_id
        FROM ref.transactions WHERE customer_id = %(cid)s
          AND transaction_date >= %(to)s::timestamp - interval '90 days' AND transaction_date < %(to)s::timestamp
        ORDER BY transaction_date DESC LIMIT 50""",
    "search_transactions (monto ±10 %)": """
        SELECT transaction_id, transaction_date, amount, currency FROM ref.transactions
        WHERE customer_id = %(cid)s AND amount BETWEEN %(amt)s * 0.9 AND %(amt)s * 1.1
          AND transaction_date >= %(to)s::timestamp - interval '120 days'
        ORDER BY transaction_date DESC LIMIT 20""",
    "get_transaction": """
        SELECT transaction_id, transaction_date, process_date, amount, currency, merchant_name, channel,
               transaction_type, transaction_status, product_id
        FROM ref.transactions WHERE transaction_id = %(tid)s AND customer_id = %(cid)s""",
    "fraud_risk (fraud_score)": """
        SELECT fraud_score FROM ref.transactions WHERE transaction_id = %(tid)s AND customer_id = %(cid)s""",
    "get_existing_case": """
        SELECT case_id, status, created_at FROM app.dispute_cases
        WHERE customer_id = %(cid)s AND transaction_id = %(tid)s AND status IN ('registrado', 'en_revision')""",
    "tarjetas del cliente": """
        SELECT product_id, product_type, product_status FROM ref.products
        WHERE customer_id = %(cid)s AND product_type IN ('Tarjeta Crédito', 'Tarjeta Débito')""",
    "get_card_status (vista efectiva)": """
        SELECT product_id, product_type, status FROM app.card_status_effective
        WHERE product_id = %(pid)s AND customer_id = %(cid)s""",
    "historial de la tarjeta": """
        SELECT transaction_id, transaction_date, amount FROM ref.transactions
        WHERE product_id = %(pid)s AND customer_id = %(cid)s ORDER BY transaction_date DESC LIMIT 20""",
}


@pytest.fixture(scope="module")
def conn():
    url = require_test_url(PERF_URL)
    with pg(TEST_URL) as c:  # crear la base de rendimiento si no existe
        if not c.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name(url),)).fetchone():
            c.execute(f'CREATE DATABASE "{db_name(url)}"')
    migrate(url)
    c = pg(url)
    if c.execute("SELECT count(*) FROM ref.transactions").fetchone()[0] < 1_000_000:
        if not DUCKDB_PATH.exists():
            pytest.skip(f"sin dataset completo en {db_name(url)} y sin {DUCKDB_PATH} para cargarlo")
        load_postgres.load_full(url, DUCKDB_PATH, RAW_DATA_DIR)
    c.execute("SET ROLE app_rw")
    yield c
    c.close()


def test_tool_queries_latency(conn):
    samples = conn.execute(f"""
        SELECT DISTINCT ON (t.customer_id) t.customer_id, t.transaction_id, t.product_id, t.amount,
               max(t.transaction_date) OVER (PARTITION BY t.customer_id)
        FROM ref.transactions t
        WHERE t.customer_id IN (SELECT customer_id FROM ref.customers ORDER BY md5(customer_id) LIMIT {N_CUSTOMERS})
        ORDER BY t.customer_id, t.transaction_date DESC""").fetchall()
    assert len(samples) >= N_CUSTOMERS * 0.9
    report = {}
    for name, sql in QUERIES.items():
        times = []
        for cid, tid, pid, amt, to in samples:
            params = {"cid": cid, "tid": tid, "pid": pid, "amt": amt, "to": to}
            conn.execute(sql, params).fetchall()          # calentamiento
            t0 = time.perf_counter()
            conn.execute(sql, params).fetchall()
            times.append((time.perf_counter() - t0) * 1000)
        p50, p95, mx = np.percentile(times, 50), np.percentile(times, 95), max(times)
        report[name] = (p50, p95, mx)
        print(f"{name:38s} p50 {p50:6.2f} ms  p95 {p95:6.2f} ms  máx {mx:6.2f} ms  (n={len(times)})")
    slow = {k: round(v[1], 2) for k, v in report.items() if v[1] > P95_MS}
    assert not slow, f"p95 sobre {P95_MS} ms: {slow}"
