"""Prueba de la carga incremental con el fixture sintético data_pipeline/fixtures/incremental/.

Requiere un PostgreSQL con una base dedicada en TEST_DATABASE_URL (su nombre debe terminar en
_test: el test borra y recrea los esquemas ref, ops y app).

    .venv/bin/pytest data_pipeline/tests -v

Escenario (todas las filas son sintéticas, IDs FXT-*):
    base      3 clientes, 4 productos, días 2026-07-01, 02 y 03
    update    02: llegada tardía (archivo nuevo, 2 filas)
              03: re-entrega del mismo archivo con una fila corregida (Pending → Approved, 45.10 → 45.01)
              04: día nuevo (2 filas)
    bad_owner 05: una transacción de FXT-C002 con un producto de FXT-C001 (rompe el aislamiento)

Qué demuestra:
    1. Solo se reemplazan las particiones afectadas (02, 03 y 04): las filas de 01 no se reescriben
       (mismo xmin en PostgreSQL).
    2. Correr la incremental otra vez no cambia nada (0 archivos, status noop, mismos xmin).
    3. La fila con el producto de otro cliente va a ref.rejected_rows, nunca a ref.transactions,
       y si los rechazos superan el umbral la corrida se detiene sin tocar ref.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from data_pipeline.etl import build_duckdb, load_postgres
from data_pipeline.tests.conftest import TEST_URL as URL, overlay, pg

D = date.fromisoformat


def snapshot() -> dict[str, tuple]:
    """transaction_id → (process_date, xmin, amount, status). xmin cambia si la fila se reescribe."""
    with pg() as c:
        rows = c.execute("SELECT transaction_id, process_date, xmin::text, amount, transaction_status "
                         "FROM ref.transactions").fetchall()
    return {r[0]: r[1:] for r in rows}


@pytest.fixture()
def env(fixture_db):
    return fixture_db


def incremental(src: Path, db: Path) -> int:
    build_duckdb.update(src, db)
    return load_postgres.load_incremental(URL, db, src)


def test_base_load(env):
    snap = snapshot()
    assert len(snap) == 9
    with pg() as c:
        assert c.execute("SELECT count(*) FROM ref.customers").fetchone()[0] == 3
        assert c.execute("SELECT count(*) FROM ref.rejected_rows").fetchone()[0] == 0
        run = c.execute("SELECT status, data_as_of, counts->'layers'->'transactions' FROM ops.etl_runs "
                        "ORDER BY run_id DESC LIMIT 1").fetchone()
        n_files = c.execute("SELECT count(*) FROM ops.etl_files").fetchone()[0]
    assert run[0] == "success" and run[1] == D("2026-07-03")
    assert run[2] == {"csv": 9, "raw": 9, "clean": 9, "ref": 9}
    assert n_files == 6  # customers, products, rates y 3 particiones


def test_incremental_replaces_only_affected_partitions(env):
    src, db = env
    before = snapshot()
    overlay(src, "update")
    run_id = incremental(src, db)
    after = snapshot()

    # día 01 intacto: mismas filas y mismo xmin (no se reescribieron)
    day1 = {k: v for k, v in before.items() if v[0] == D("2026-07-01")}
    assert day1 and all(after[k] == v for k, v in day1.items())
    # día 02: base + llegada tardía
    assert sorted(k for k, v in after.items() if v[0] == D("2026-07-02")) == \
        ["FXT-T0201", "FXT-T0202", "FXT-T0203", "FXT-T0204", "FXT-T0205"]
    # día 03: fila corregida
    assert after["FXT-T0303"][2:] == (Decimal("45.01"), "Approved")
    assert before["FXT-T0303"][2:] == (Decimal("45.10"), "Pending")
    # día 04: nuevo
    assert {"FXT-T0401", "FXT-T0402"} <= after.keys()
    assert len(after) == 9 + 2 + 2
    # filas reemplazadas: todas las de 02, 03 y 04 tienen xmin nuevo
    touched = {k for k, v in after.items() if k not in before or before[k][1] != v[1]}
    assert touched == {k for k, v in after.items() if v[0] >= D("2026-07-02")}

    with pg() as c:
        run = c.execute("SELECT mode, status, partitions_replaced, data_as_of, counts FROM ops.etl_runs WHERE run_id = %s",
                        (run_id,)).fetchone()
        files = c.execute("SELECT source_file, action, rows FROM ops.etl_files WHERE run_id = %s ORDER BY 1",
                          (run_id,)).fetchall()
    assert run[:2] == ("incremental", "success")
    assert run[2] == ["2026-07-02", "2026-07-03", "2026-07-04"]
    assert run[3] == D("2026-07-04")
    assert run[4]["deleted"] == 6 and run[4]["inserted"] == 10
    assert [(f[0].rsplit("/", 1)[-1], f[1], f[2]) for f in files] == [
        ("transactions_20260702_late.csv", "new", 2),
        ("transactions_20260703.csv", "changed", 3),
        ("transactions_20260704.csv", "new", 2)]


def test_incremental_is_idempotent(env):
    src, db = env
    overlay(src, "update")
    incremental(src, db)
    first = snapshot()
    with pg() as c:
        n_files = c.execute("SELECT count(*) FROM ops.etl_files").fetchone()[0]
    run_id = incremental(src, db)
    assert snapshot() == first  # mismas filas, mismos valores, mismos xmin
    with pg() as c:
        status, parts = c.execute("SELECT status, partitions_replaced FROM ops.etl_runs WHERE run_id = %s",
                                  (run_id,)).fetchone()
        assert c.execute("SELECT count(*) FROM ops.etl_files").fetchone()[0] == n_files
    assert status == "noop" and parts == []


def test_foreign_owner_goes_to_quarantine(env, monkeypatch):
    src, db = env
    overlay(src, "bad_owner")
    # 1 de 3 filas rechazadas (33 %) supera el 0,1 %: la corrida se detiene y ref no cambia
    before = snapshot()
    with pytest.raises(load_postgres.LoadAborted):
        incremental(src, db)
    assert snapshot() == before
    with pg() as c:
        assert c.execute("SELECT status FROM ops.etl_runs ORDER BY run_id DESC LIMIT 1").fetchone()[0] == "failed"

    # DuckDB ya tiene el archivo, pero PostgreSQL no (ops.etl_files): la siguiente corrida lo retoma.
    # Con un umbral permisivo, la fila va a cuarentena con su motivo y las otras dos se cargan.
    monkeypatch.setattr(load_postgres, "REJECT_THRESHOLD", 0.5)
    incremental(src, db)
    after = snapshot()
    assert "FXT-T0502" not in after and {"FXT-T0501", "FXT-T0503"} <= after.keys()
    assert all(after[k] == v for k, v in before.items())
    with pg() as c:
        rej = c.execute("SELECT pk_value, reason, partition_date, row_data->>'customer_id' FROM ref.rejected_rows").fetchall()
    assert rej == [("FXT-T0502", "transaction_customer_product_mismatch", D("2026-07-05"), "FXT-C002")]
