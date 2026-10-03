"""Flujos generados (eval/generated): el generador no cambia lo esperado, es determinista y la muestra cubre los estratos;
el esquema eval solo se escribe en una base local; el guardado y la lectura de un lote van y vuelven iguales."""
import os
import re
from collections import Counter
from pathlib import Path

import psycopg
import pytest

from eval.generated import generator as gen
from eval.generated import store

REPO = Path(__file__).resolve().parents[2]
MARK = re.compile(r"\{[a-z_]+\}")


@pytest.fixture(scope="module")
def batch():
    return gen.generate(1500, seed=7)


def test_generation_is_deterministic_unique_and_covers_every_seed(batch):
    assert [g.case for g in batch] == [g.case for g in gen.generate(1500, seed=7)]
    assert len({g.case.case_id for g in batch}) == len(batch) == 1500
    assert {g.seed_case_id for g in batch} == {c.case_id for c in gen.seeds()}        # ronda por semilla
    assert all(g.case.split == "generated" and 0 <= g.case.pick < gen.PICKS for g in batch)


def test_only_what_should_not_matter_changes(batch):
    seeds = {c.case_id: c for c in gen.seeds()}
    for g in batch:
        seed = seeds[g.seed_case_id]
        assert g.case.expected == seed.expected and g.case.selector == seed.selector and g.case.language == seed.language
        assert len(g.case.steps) == len(seed.steps)
        for a, b in zip(seed.steps, g.case.steps):
            assert (a.message is None) == (b.message is None)
            assert a.model_dump(exclude={"message"}) == b.model_dump(exclude={"message"})          # botones y fallos iguales
            if a.message is not None:
                assert sorted(MARK.findall(a.message)) == sorted(MARK.findall(b.message)), g.case.case_id


def test_greeting_cases_keep_their_exact_message(batch):
    for g in batch:
        if g.case.expected.fast_path is True:
            assert g.opener == "" and g.noise == "ninguno"
        if g.case.expected.fast_path is not None:
            assert g.opener == ""


def test_dimensions_are_all_used(batch):
    assert set(Counter(g.noise for g in batch)) == set(gen.NOISES)
    assert {g.opener for g in batch if g.case.language == "pt"} == set(gen.OPENERS["pt"])
    first = next(g for g in batch if g.opener == "Hola, ")
    assert next(s.message for s in first.case.steps if s.message).lower().startswith("hola, ")


def test_noise_never_touches_markers():
    import random
    msg = "No reconozco el cargo de {monto_es} {moneda_es} en {comercio} del {fecha_ddmm}"
    for noise in gen.NOISES:
        out = gen.apply_noise(msg, noise, random.Random(3))
        assert MARK.findall(out) == MARK.findall(msg)
    assert gen.apply_noise("Él NO pagó {comercio}", "minusculas", random.Random(1)) == "él no pagó {comercio}"


def test_stratified_sample_keeps_every_stratum_and_size(batch):
    sample = gen.stratified_sample(batch, 120, seed=1)
    assert len(sample) == 120 and len({g.case.case_id for g in sample}) == 120
    strata = {(g.case.language, g.case.category) for g in batch}
    assert {(g.case.language, g.case.category) for g in sample} == strata
    assert sample == gen.stratified_sample(batch, 120, seed=1)
    assert len(gen.stratified_sample(batch, 5, seed=1)) == 5


def test_store_refuses_a_remote_database(monkeypatch):
    monkeypatch.setenv("EVAL_STORE_URL", "postgresql+psycopg://u:p@dpg-abc.oregon-postgres.render.com:5432/bank")
    monkeypatch.delenv("EVAL_STORE_ALLOW_REMOTE", raising=False)
    with pytest.raises(SystemExit, match="base local"):
        store.store_url()
    monkeypatch.setenv("EVAL_STORE_URL", "postgresql+psycopg://u:p@127.0.0.1:5433/bank")
    assert store.store_url().endswith("/bank")


def test_run_summary_is_valid_json_even_with_empty_groups():
    assert store._json_safe({"latencia_saludo_ms": {"p50": float("nan"), "n": 0}, "x": (1, 2)}) == {"latencia_saludo_ms": {"p50": None, "n": 0}, "x": [1, 2]}


def test_preflight_skips_the_fake_llm(monkeypatch):
    from eval.generated.__main__ import preflight
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    assert preflight() is None


def test_schema_is_not_an_alembic_migration():
    migrations = "".join(p.read_text() for p in (REPO / "backend" / "migrations" / "versions").glob("*.py"))
    assert "eval." not in migrations                 # la base desplegada nunca crea el esquema eval


def test_rehearsal_script_is_free_by_default():
    sh = (REPO / "scripts" / "eval_generated.sh").read_text()
    assert 'MODE=fake' in sh and "RUN=(--variant sistema --set LLM_PROVIDER=fake)" in sh
    assert '[[ "${DBURL##*/}" == *_test* ]]' in sh


def _test_db() -> str | None:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        return None
    try:
        psycopg.connect(url.replace("postgresql+psycopg://", "postgresql://"), connect_timeout=3).close()
    except psycopg.OperationalError:
        return None
    return url


def test_batch_round_trip_and_report_from_the_database(monkeypatch):
    url = _test_db()
    if not url:
        pytest.skip("sin TEST_DATABASE_URL accesible")
    monkeypatch.setenv("EVAL_STORE_URL", url)
    items = gen.generate(40, seed=11)
    with store.connect() as conn:
        batch_id = store.save_batch(conn, items, 11, {"n": 40}, note="test")
        try:
            assert [g.case for g in store.load_batch(conn, batch_id)] == sorted((g.case for g in items), key=lambda c: c.case_id)
            run_id = conn.execute("""INSERT INTO eval.runs (batch_id, started_at, variant, llm_provider, sample_size, sample_seed, repeats,
                                     database, summary) VALUES (%s, now(), 'sistema+LLM_PROVIDER=fake', 'fake', 2, 1, 1, 'x_test', '{}')
                                     RETURNING run_id""", (batch_id,)).fetchone()["run_id"]
            for g, ok in zip(items[:2], (True, False)):
                conn.execute("""INSERT INTO eval.case_results (run_id, batch_id, case_id, repeat, outcome, all_pass, unsafe, expected_auto,
                                safe_auto, expected_escalated, escalated, failed_checks, root_cause, n_turns, latency_ms, llm_calls, checks)
                                VALUES (%s, %s, %s, 1, 'resolved_case', %s, false, true, %s, false, false, %s, %s, 2, 100, 0, '[]')""",
                             (run_id, batch_id, g.case.case_id, ok, ok, [] if ok else ["resultado_final"], None if ok else "aclaración"))
            conn.commit()
            text = store.report(conn, run_id)
            assert "| Pasan todos los checkers | 1/2 (50.0 %) |" in text and "| aclaración | 1 |" in text
            assert items[1].seed_case_id in text                              # semillas con más fallos
        finally:
            conn.execute("DELETE FROM eval.batches WHERE batch_id = %s", (batch_id,))
            conn.commit()

