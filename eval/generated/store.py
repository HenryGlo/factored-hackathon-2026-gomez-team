"""Esquema eval en la base local: guardar lotes de flujos generados, leerlos, guardar resultados y resumirlos.

La base es EVAL_STORE_URL o, por defecto, ADMIN_DATABASE_URL (.env): la base local del proyecto. Se niega a escribir en un
servidor que no sea local (localhost, 127.0.0.1, ::1 o el nombre de un contenedor de docker compose) salvo con
EVAL_STORE_ALLOW_REMOTE=1: el esquema eval no va a la base desplegada.
"""
from __future__ import annotations

import json
import math
import os
import subprocess
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlsplit

import psycopg
from dotenv import dotenv_values
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from eval.cases.schema import Case
from eval.generated.generator import GENERATOR_VERSION, Generated

REPO = Path(__file__).resolve().parents[2]
SCHEMA = Path(__file__).with_name("schema.sql")
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "postgres", "db"}


def store_url() -> str:
    env = {**dotenv_values(REPO / ".env"), **os.environ}
    url = env.get("EVAL_STORE_URL") or env.get("ADMIN_DATABASE_URL")
    if not url:
        raise SystemExit("falta EVAL_STORE_URL o ADMIN_DATABASE_URL (.env): la base local donde vive el esquema eval")
    host = urlsplit(url.replace("postgresql+psycopg://", "postgresql://")).hostname or "localhost"
    if host not in LOCAL_HOSTS and env.get("EVAL_STORE_ALLOW_REMOTE") != "1":
        raise SystemExit(f"el esquema eval vive en la base local; {host} no lo es (EVAL_STORE_ALLOW_REMOTE=1 para forzarlo)")
    return url


def connect(url: str | None = None) -> psycopg.Connection:
    conn = psycopg.connect((url or store_url()).replace("postgresql+psycopg://", "postgresql://"), row_factory=dict_row)
    conn.execute(SCHEMA.read_text(encoding="utf-8"))
    conn.commit()
    return conn


def _commit() -> str | None:
    out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=REPO)
    return out.stdout.strip() or None


def save_batch(conn, items: list[Generated], seed: int, params: dict, note: str | None = None) -> int:
    batch_id = conn.execute("""INSERT INTO eval.batches (generator_version, seed, params, n_cases, git_commit, note)
                               VALUES (%s, %s, %s, %s, %s, %s) RETURNING batch_id""",
                            (GENERATOR_VERSION, seed, Jsonb(params), len(items), _commit(), note)).fetchone()["batch_id"]
    with conn.cursor() as cur:
        cur.executemany("""INSERT INTO eval.generated_cases (batch_id, case_id, language, category, selector, seed_case_id, seed_split,
                                                             origin, pick, opener, noise, expected_outcomes, definition)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                        [(batch_id, g.case.case_id, g.case.language, g.case.category, g.case.selector, g.seed_case_id, g.seed_split,
                          g.origin, g.pick, g.opener, g.noise, g.case.outcomes, Jsonb(g.case.model_dump(mode="json", exclude_none=True)))
                         for g in items])
    conn.commit()
    return batch_id


def latest_batch(conn) -> int | None:
    row = conn.execute("SELECT max(batch_id) AS b FROM eval.batches").fetchone()
    return row["b"]


def load_batch(conn, batch_id: int) -> list[Generated]:
    rows = conn.execute("""SELECT definition, seed_case_id, seed_split, origin, pick, opener, noise FROM eval.generated_cases
                           WHERE batch_id = %s ORDER BY case_id COLLATE "C"
                        """, (batch_id,)).fetchall()   # orden por bytes, igual en cualquier locale: la muestra es reproducible
    return [Generated(Case.model_validate(r["definition"]), r["seed_case_id"], r["seed_split"], r["origin"], r["pick"], r["opener"], r["noise"])
            for r in rows]


def clamp_picks(urls: dict, ref_date: date, cases: list[Case]) -> list[Case]:
    """El pick de un flujo generado va de 0 a 39; si el selector tiene menos filas en esta base (otro dataset), se toma
    pick módulo filas, para que el caso corra igual sobre otro cliente del mismo escenario. Sin filas, queda como está
    (el caso falla con el error del selector y se ve en el reporte)."""
    from sqlalchemy import create_engine, text

    from eval.cases.selectors import SELECTORS

    counts: dict[tuple[str, date], int] = {}
    eng = create_engine(urls["admin"])
    try:
        with eng.connect() as c:
            for case in cases:
                key = (case.selector, case.session_date or ref_date)
                if key not in counts and case.selector in SELECTORS:
                    counts[key] = c.execute(text(f"SELECT count(*) FROM ({SELECTORS[case.selector]}) s"), {"r": key[1]}).scalar_one()
    finally:
        eng.dispose()
    out = []
    for case in cases:
        n = counts.get((case.selector, case.session_date or ref_date), 0)
        out.append(case.model_copy(update={"pick": case.pick % n}) if n and case.pick >= n else case)
    return out


def _json_safe(obj):
    """El resumen trae NaN cuando un grupo está vacío (p. ej. sin casos de saludo en la muestra); JSON no lo admite."""
    if isinstance(obj, float) and math.isnan(obj):
        return None
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return json.loads(json.dumps(obj, default=str)) if not isinstance(obj, (str, int, float, bool, type(None))) else obj


def save_run(conn, batch_id: int, started_at: datetime, config: dict, runs_by_repeat: list, sample_size: int, sample_seed: int,
             report_path: str | None) -> int:
    from eval.harness.metrics import root_cause, summarize

    scored = [s for rep in runs_by_repeat for s in rep]
    run_id = conn.execute("""INSERT INTO eval.runs (batch_id, started_at, variant, llm_provider, sample_size, sample_seed, repeats,
                                                    database, git_commit, git_dirty, summary, report_path)
                             VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING run_id""",
                          (batch_id, started_at, config["variant"], config["versions"]["llm_provider"], sample_size, sample_seed,
                           config["repeats"], config["database"], config["git_commit"], config["git_dirty"],
                           Jsonb(_json_safe(summarize(scored))), report_path)).fetchone()["run_id"]
    rows = []
    for s in scored:
        checks = [vars(c) for c in s.checks]
        lat = s.turn_latencies
        rows.append((run_id, batch_id, s.run.case.case_id, s.run.repeat, s.outcome, s.all_pass, s.unsafe, s.expected_auto, s.safe_auto,
                     s.expected_escalated, s.escalated, [c.name for c in s.checks if not c.passed],
                     root_cause(checks, s.outcome, s.run.case.outcomes, s.run.artifacts.get("traces", [])), s.cost, len(lat),
                     round(sum(lat), 1), round(max(lat), 1) if lat else None, sum(x["llamadas_llm"] for x in s.latency_split),
                     s.run.error, Jsonb(checks)))
    with conn.cursor() as cur:
        cur.executemany("""INSERT INTO eval.case_results (run_id, batch_id, case_id, repeat, outcome, all_pass, unsafe, expected_auto,
                                                          safe_auto, expected_escalated, escalated, failed_checks, root_cause, cost_usd,
                                                          n_turns, latency_ms, turn_latency_max_ms, llm_calls, error, checks)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""", rows)
    conn.commit()
    return run_id


def cost_per_case(conn, variant: str) -> float | None:
    """Costo medio por caso de las corridas anteriores de esa variante (para estimar antes de correr)."""
    row = conn.execute("""SELECT avg(cost_usd) AS c FROM eval.v_results WHERE variant = %s AND cost_usd > 0""", (variant,)).fetchone()
    return float(row["c"]) if row and row["c"] is not None else None


def _frac(n: int, d: int) -> str:
    return f"{n}/{d} ({n / d * 100:.1f} %)" if d else "—"


GROUPS = {"idioma × categoría": "language || ' · ' || category", "ruido": "noise",
          "saludo al inicio": "CASE WHEN with_opener THEN 'con saludo' ELSE 'sin saludo' END", "origen": "origin || ' (' || seed_split || ')'"}


def report(conn, run_id: int) -> str:
    run = conn.execute("SELECT * FROM eval.runs WHERE run_id = %s", (run_id,)).fetchone()
    if not run:
        raise SystemExit(f"no existe la corrida {run_id}")
    t = conn.execute("""SELECT count(*) n, count(*) FILTER (WHERE all_pass) ok, count(*) FILTER (WHERE unsafe) unsafe,
                               count(*) FILTER (WHERE expected_auto) auto, count(*) FILTER (WHERE safe_auto) safe_auto,
                               count(*) FILTER (WHERE expected_escalated) exp_esc,
                               count(*) FILTER (WHERE expected_escalated AND escalated) esc_ok,
                               count(*) FILTER (WHERE escalated AND NOT expected_escalated) esc_extra,
                               count(*) FILTER (WHERE error IS NOT NULL) errors,
                               sum(cost_usd) cost, sum(n_turns) turns,
                               percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_ms / greatest(n_turns, 1)) p50,
                               percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms / greatest(n_turns, 1)) p95
                        FROM eval.case_results WHERE run_id = %s""", (run_id,)).fetchone()
    L = [f"# Corrida {run_id} · lote {run['batch_id']} · `{run['variant']}` ({run['llm_provider']}) · {run['started_at'].astimezone():%Y-%m-%d %H:%M}", "",
         f"Muestra de {run['sample_size']} flujos (semilla {run['sample_seed']}) × {run['repeats']} rep. en `{run['database']}`, "
         f"commit `{(run['git_commit'] or '')[:7]}`{' con cambios sin commit' if run['git_dirty'] else ''}.", "",
         "| Métrica | Valor |", "|---|---|",
         f"| Pasan todos los checkers | {_frac(t['ok'], t['n'])} |",
         f"| Resultados inseguros | {_frac(t['unsafe'], t['n'])} |",
         f"| Resolución automática segura | {_frac(t['safe_auto'], t['auto'])} |",
         f"| Escalamientos correctos | {_frac(t['esc_ok'], t['exp_esc'])} |",
         f"| Escalamientos innecesarios | {t['esc_extra']} |",
         f"| Casos con error del harness | {t['errors']} |",
         f"| Latencia media por turno p50 / p95 (por caso) | {t['p50'] or 0:.0f} ms / {t['p95'] or 0:.0f} ms |",
         f"| Costo total / por caso | ${float(t['cost'] or 0):.4f} / ${float(t['cost'] or 0) / max(t['n'], 1):.4f} |"]
    failed, calls = (run["summary"].get("llamadas_llm_fallidas") or [0, 0])
    if calls and failed / calls > 0.05:
        L[2:2] = [f"> **⚠ Corrida no válida: fallaron {failed} de {calls} llamadas al LLM.** Mide las reglas de respaldo, no el modelo; "
                  "no usar estos números.", ""]
    if t["unsafe"]:
        L += ["", f"**⚠ {t['unsafe']} resultado(s) inseguro(s):** ver `SELECT case_id, failed_checks FROM eval.v_results "
                  f"WHERE run_id = {run_id} AND unsafe`."]
    for title, expr in GROUPS.items():
        L += ["", f"## Por {title}", "", "| Grupo | n | Pasan todo | Inseguros |", "|---|---|---|---|"]
        for r in conn.execute(f"""SELECT {expr} AS g, count(*) n, count(*) FILTER (WHERE all_pass) ok, count(*) FILTER (WHERE unsafe) u
                                  FROM eval.v_results WHERE run_id = %s GROUP BY 1 ORDER BY 1""", (run_id,)).fetchall():
            L.append(f"| {r['g']} | {r['n']} | {_frac(r['ok'], r['n'])} | {r['u']} |")
    causes = conn.execute("""SELECT root_cause, count(*) n FROM eval.case_results WHERE run_id = %s AND NOT all_pass
                             GROUP BY 1 ORDER BY 2 DESC""", (run_id,)).fetchall()
    if causes:
        L += ["", "## Fallos por causa raíz", "", "| Causa | Casos |", "|---|---|"] + [f"| {r['root_cause'] or '—'} | {r['n']} |" for r in causes]
    worst = conn.execute("""SELECT seed_case_id, count(*) n, count(*) FILTER (WHERE NOT all_pass) bad,
                                   (array_agg(case_id ORDER BY case_id) FILTER (WHERE NOT all_pass))[1:3] ex
                            FROM eval.v_results WHERE run_id = %s GROUP BY 1 HAVING count(*) FILTER (WHERE NOT all_pass) > 0
                            ORDER BY 3 DESC, 1 LIMIT 10""", (run_id,)).fetchall()
    if worst:
        L += ["", "## Semillas con más fallos", "", "Un caso escrito a mano que falla en muchas de sus variantes señala dónde es frágil el sistema.", "",
              "| Semilla | Fallan | Ejemplos |", "|---|---|---|"]
        L += [f"| {r['seed_case_id']} | {r['bad']}/{r['n']} | {', '.join(r['ex'] or [])} |" for r in worst]
    return "\n".join(L) + "\n"


def status(conn) -> str:
    L = ["Lotes:"]
    for b in conn.execute("""SELECT b.batch_id, b.created_at, b.generator_version, b.n_cases, b.seed,
                                    count(DISTINCT r.run_id) runs FROM eval.batches b LEFT JOIN eval.runs r USING (batch_id)
                             GROUP BY b.batch_id ORDER BY b.batch_id""").fetchall():
        L.append(f"  {b['batch_id']:>3}  {b['created_at'].astimezone():%Y-%m-%d %H:%M}  {b['n_cases']:>6} flujos  {b['generator_version']}  semilla {b['seed']}  ({b['runs']} corridas)")
    L.append("Corridas:")
    for r in conn.execute("""SELECT run_id, batch_id, started_at, variant, sample_size, repeats,
                                    (summary->'casos_que_pasan_todo'->>0)::int ok, (summary->'resultados_inseguros'->>0)::int unsafe,
                                    (summary->>'costo_total_usd')::numeric cost FROM eval.runs ORDER BY run_id""").fetchall():
        L.append(f"  {r['run_id']:>3}  lote {r['batch_id']}  {r['started_at'].astimezone():%Y-%m-%d %H:%M}  {r['variant']:36s} "
                 f"{r['ok']}/{r['sample_size'] * r['repeats']} pasan, {r['unsafe']} inseguros, ${float(r['cost'] or 0):.4f}")
    return "\n".join(L)
