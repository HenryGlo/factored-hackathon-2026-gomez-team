"""Carga completa: idempotencia, contratos (bloqueo, cuarentena, advertencia) y convivencia con app.

Usa el fixture sintético (IDs FXT-*) sobre la base *_test de TEST_DATABASE_URL.
"""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from data_pipeline.etl import build_duckdb, load_postgres
from data_pipeline.tests.conftest import TEST_URL, pg

REF_TABLES = ("customers", "products", "transactions", "daily_exchange_rates", "rejected_rows", "demo_customers")
TX_FILE = "transactions/year=2026/month=07/day=01/transactions_20260701.csv"


def content() -> dict[str, list]:
    """Contenido de ref sin columnas de corrida (etl_run_id, rejected_id, rejected_at)."""
    out = {}
    with pg() as c:
        for t in REF_TABLES:
            cols = [r[0] for r in c.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_schema = 'ref' AND table_name = %s "
                "AND column_name NOT IN ('etl_run_id', 'rejected_id', 'rejected_at') ORDER BY ordinal_position", (t,))]
            out[t] = sorted(map(str, c.execute(f"SELECT {', '.join(cols)} FROM ref.{t}").fetchall()))
    return out


def last_run() -> dict:
    with pg() as c:
        cur = c.execute("SELECT * FROM ops.etl_runs ORDER BY run_id DESC LIMIT 1")
        return dict(zip([d.name for d in cur.description], cur.fetchone()))


def add_rows(src: Path, rows: list[dict]) -> None:
    """Agrega filas sintéticas al CSV del día 01 (copia de trabajo en tmp, nunca el fixture versionado)."""
    path = src / TX_FILE
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        header, base = reader.fieldnames, list(reader)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, header)
        w.writeheader()
        w.writerows(base + [{**base[0], **r} for r in rows])


def test_full_load_is_idempotent(fixture_db):
    src, db = fixture_db
    first, run1 = content(), last_run()
    load_postgres.load_full(TEST_URL, db, src)
    second, run2 = content(), last_run()
    assert first == second
    assert run1["counts"]["layers"] == run2["counts"]["layers"]
    assert run1["customer_list_sha256"] == run2["customer_list_sha256"] is not None
    assert run2["status"] == "success" and run2["app_orphans"] == {k: 0 for k in load_postgres.APP_ORPHAN_CHECKS}


def test_display_name_is_minimal(fixture_db):
    with pg() as c:
        cols = {r[0] for r in c.execute("SELECT column_name FROM information_schema.columns "
                                        "WHERE table_schema = 'ref' AND table_name = 'customers'")}
        names = dict(c.execute("SELECT customer_id, display_name FROM ref.customers").fetchall())
    assert not cols & {"first_name", "last_name", "document_number", "email", "mobile_phone", "address", "city"}
    assert {"segment", "country", "display_name"} <= cols
    assert names["FXT-C001"] == "Fixture U."


def test_invalid_row_aborts_or_goes_to_quarantine(fixture_db, monkeypatch):
    src, db = fixture_db
    add_rows(src, [
        {"transaction_id": "FXT-T0199", "currency": "XXX"},                       # dominio bloqueante
        {"transaction_id": "FXT-T0198", "latitude": "123.0", "longitude": "10"},  # rango de advertencia
    ])
    build_duckdb.build_full(src, db)
    before = content()
    # 1 rechazo de 11 filas (9 %) > 0,1 %: la carga se detiene y ref queda igual
    with pytest.raises(load_postgres.LoadAborted):
        load_postgres.load_full(TEST_URL, db, src)
    assert content() == before and last_run()["status"] == "failed"

    monkeypatch.setattr(load_postgres, "REJECT_THRESHOLD", 0.5)
    load_postgres.load_full(TEST_URL, db, src)
    with pg() as c:
        rej = c.execute("SELECT table_name, pk_value, reason FROM ref.rejected_rows").fetchall()
        loaded = {r[0] for r in c.execute("SELECT transaction_id FROM ref.transactions")}
    assert rej == [("transactions", "FXT-T0199", "transaction_currency_domain")]
    assert "FXT-T0199" not in loaded and "FXT-T0198" in loaded   # la advertencia no bloquea
    run = last_run()
    assert run["counts"]["contract_warnings"]["transactions"]["transaction_latitude_range"] == 1


def insert_app_rows(c, transaction_id: str = "FXT-T0101", customer_id: str = "FXT-C001", suffix: str = "1") -> None:
    c.execute(f"""
        INSERT INTO app.sessions (session_id, token_hash, role, customer_id, expires_at)
            VALUES ('ses_{suffix}', md5('t{suffix}') || md5('u{suffix}'), 'customer', '{customer_id}', now() + interval '1 hour');
        INSERT INTO app.conversations (conversation_id, session_id, customer_id, state)
            VALUES ('conv_{suffix}', 'ses_{suffix}', '{customer_id}', 'ejecutando');
        INSERT INTO app.turns (turn_id, conversation_id, seq, role, message)
            VALUES ('turn_{suffix}', 'conv_{suffix}', 1, 'customer', 'Tengo un cobro que no reconozco');
        INSERT INTO app.idempotency_keys (session_id, idempotency_key, request_hash, status_code, response, expires_at)
            VALUES ('ses_{suffix}', 'idem-{suffix}', md5('r'), 200, '{{}}', now() + interval '1 day');
        INSERT INTO app.confirmation_tokens (token_id, token_hash, session_id, conversation_id, action, params, params_hash, expires_at, consumed_at)
            VALUES ('ct_{suffix}', md5('c{suffix}'), 'ses_{suffix}', 'conv_{suffix}', 'create_dispute_case',
                    '{{"transaction_id": "{transaction_id}"}}', md5('p'), now() + interval '5 min', now());
        INSERT INTO app.dispute_cases (case_id, customer_id, transaction_id, conversation_id, turn_id, confirmation_token_id,
                                       idempotency_key, reason_code, confirmed_at)
            VALUES ('case_{suffix}', '{customer_id}', '{transaction_id}', 'conv_{suffix}', 'turn_{suffix}', 'ct_{suffix}',
                    'idem-{suffix}', 'no_reconocido', now());
        INSERT INTO app.card_status_overrides (customer_id, product_id, status, conversation_id)
            VALUES ('{customer_id}', 'FXT-P001', 'Blocked', 'conv_{suffix}');
        INSERT INTO app.handoffs (handoff_id, conversation_id, customer_id, language, reason_code, priority, payload)
            VALUES ('hof_{suffix}', 'conv_{suffix}', '{customer_id}', 'es', 'riesgo_alto', 'alta', '{{}}');
        INSERT INTO app.traces (turn_id, conversation_id, step_seq, node, kind) VALUES ('turn_{suffix}', 'conv_{suffix}', 1, 'intencion', 'llm');
    """)


APP_TABLES = ("sessions", "conversations", "turns", "idempotency_keys", "confirmation_tokens", "dispute_cases",
              "card_status_overrides", "handoffs", "traces")


def app_counts(c) -> dict[str, int]:
    return {t: c.execute(f"SELECT count(*) FROM app.{t}").fetchone()[0] for t in APP_TABLES}


def test_reload_never_touches_app(fixture_db):
    src, db = fixture_db
    with pg() as c:
        insert_app_rows(c)
        before = app_counts(c)
        effective = c.execute("SELECT status FROM app.card_status_effective WHERE product_id = 'FXT-P001'").fetchone()[0]
    assert effective == "Blocked" and all(v == 1 for v in before.values())

    load_postgres.load_full(TEST_URL, db, src)                    # recarga completa de ref
    with pg() as c:
        assert app_counts(c) == before
        # el bloqueo de la app sigue mandando sobre ref.products (Active)
        assert c.execute("SELECT status, ref_status FROM app.card_status_effective WHERE product_id = 'FXT-P001'").fetchone() \
            == ("Blocked", "Active")
    run = last_run()
    assert run["status"] == "success" and not any(run["app_orphans"].values())


def test_app_rows_pointing_to_missing_ref_ids_give_warning(fixture_db):
    src, db = fixture_db
    with pg() as c:
        insert_app_rows(c, transaction_id="FXT-T9999", suffix="x")   # transacción que no existe en ref
        c.execute("INSERT INTO app.handoffs (handoff_id, conversation_id, customer_id, language, reason_code, priority, payload) "
                  "VALUES ('hof_y', 'conv_x', 'FXT-C999', 'es', 'pide_humano', 'media', '{}')")
    load_postgres.load_full(TEST_URL, db, src)
    run = last_run()
    assert run["status"] == "warning"
    assert run["app_orphans"] == {"dispute_cases_transaction": 1, "handoffs_customer": 1, "card_status_overrides_product": 0}


def test_open_dispute_is_unique_but_closed_ones_do_not_block(fixture_db):
    import psycopg
    with pg() as c:
        insert_app_rows(c)
        with pytest.raises(psycopg.errors.UniqueViolation):   # segundo reclamo abierto sobre la misma transacción
            c.execute("INSERT INTO app.dispute_cases (case_id, customer_id, transaction_id, reason_code, confirmed_at) "
                      "VALUES ('case_2', 'FXT-C001', 'FXT-T0101', 'no_reconocido', now())")
        c.execute("UPDATE app.dispute_cases SET status = 'resuelto', closed_at = now() WHERE case_id = 'case_1'")
        c.execute("INSERT INTO app.dispute_cases (case_id, customer_id, transaction_id, reason_code, confirmed_at) "
                  "VALUES ('case_3', 'FXT-C001', 'FXT-T0101', 'no_reconocido', now())")
        with pytest.raises(psycopg.errors.UniqueViolation):   # misma Idempotency-Key → no hay segundo reclamo
            c.execute("INSERT INTO app.dispute_cases (case_id, customer_id, transaction_id, reason_code, confirmed_at, idempotency_key) "
                      "VALUES ('case_4', 'FXT-C001', 'FXT-T0102', 'no_reconocido', now(), 'idem-1')")
