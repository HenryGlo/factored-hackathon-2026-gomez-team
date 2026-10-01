"""Analítica operativa (prompt 07, bloque 4): un solo comando regenera el reporte y las figuras.

    python -m analytics.report                 # lee data/bank.duckdb (DUCKDB_PATH) y eval/results/raw/*.json

Escribe docs/analytics.md y docs/analytics/figures/*.png. Solo preguntas operativas; cada figura responde la pregunta de su
título. No escribe datos del dataset en el repo: solo agregados.

Secciones: (1) calidad de datos desde el ETL y sus contratos, (2) demanda desde el dataset, (3) operación desde las trazas
de las corridas de evaluación, (4) ROI con supuestos editables (backend/config/roi.toml).
"""
from __future__ import annotations

import json
import os
import tomllib
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import duckdb

from backend.app.observability.admin_metrics import roi_numbers      # un solo cálculo para el reporte y el endpoint

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "analytics.md"
FIG = REPO / "docs" / "analytics" / "figures"
ROI_FILE = REPO / "backend" / "config" / "roi.toml"
SERVED = ("customers", "products", "transactions", "daily_exchange_rates")
DISPUTABLE = "transaction_type = 'Purchase' AND merchant_name IS NOT NULL"


def n(x: float) -> str:
    return f"{int(x):,}".replace(",", ".")


def frac(a: int, b: int) -> str:
    return f"{n(a)}/{n(b)} ({100 * a / b:.1f} %)" if b else f"{a}/0"


def pct(values: list[float], q: float) -> float:
    s = sorted(values)
    if not s:
        return float("nan")
    k = (len(s) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


# ------------------------------------------------------------------ 1. calidad de datos
def data_quality(con) -> list[str]:
    from data_pipeline.contracts.engine import evaluate, load_contracts
    contracts = load_contracts()
    rej, warnings = evaluate(con, contracts, {t: t for t in SERVED})
    rejected = {(r.table_name, r.reason): int(r.n) for r in rej.itertuples()}
    L = ["## 1. Calidad de datos (reporte del ETL)", "",
         "Fuente: la base DuckDB del pipeline (`raw_*` → tablas limpias) y los contratos de `data_pipeline/contracts/`. "
         "Cada problema tiene la regla del contrato que se le aplica: `block` manda la fila a cuarentena (`ref.rejected_rows`), "
         "`warn` la deja pasar y la cuenta.", "",
         "| Tabla | Filas crudas | Filas limpias | PK duplicadas (crudo) | Filas a cuarentena | Advertencias |", "|---|---|---|---|---|---|"]
    for t in SERVED:
        pk = ", ".join(contracts[t].primary_key)
        raw = con.execute(f"SELECT count(*) FROM raw_{t}").fetchone()[0]
        clean = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        dup = con.execute(f"SELECT coalesce(sum(c - 1), 0) FROM (SELECT count(*) c FROM raw_{t} GROUP BY {pk} HAVING count(*) > 1)").fetchone()[0]
        q = sum(v for (tt, _), v in rejected.items() if tt == t)
        w = sum(warnings.get(t, {}).values())
        L.append(f"| `{t}` | {n(raw)} | {n(clean)} | {n(dup)} | {n(q)} | {n(w)} |")
    L += ["", "**Reglas con filas afectadas** (las demás reglas de los contratos dieron 0):", "",
          "| Tabla | Regla del contrato | Tipo | Severidad | Filas | Por qué |", "|---|---|---|---|---|---|"]
    any_rule = False
    for t in SERVED:
        for r in contracts[t].all_rules:
            k = rejected.get((t, r.id), 0) if r.severity == "block" else warnings.get(t, {}).get(r.id, 0)
            if k:
                any_rule = True
                L.append(f"| `{t}` | `{r.id}` | {r.check} | {r.severity} | {n(k)} | {r.why or ''} |")
    if not any_rule:
        L.append("| — | ninguna | | | 0 | |")
    total_rules = sum(len(contracts[t].all_rules) for t in SERVED)
    L += ["", f"Reglas evaluadas: {total_rules} (not_null, dominios, rangos, unicidad e integridad referencial).", "",
          "**Nulos que importan para el flujo de disputas** (`transactions`):", "", "| Columna | Nulos | Qué implica |", "|---|---|---|"]
    tot = con.execute("SELECT count(*) FROM transactions").fetchone()[0]
    for col, why in (("fraud_score", "riesgo `desconocido` (R6): no se trata como bajo"),
                     ("merchant_name", "no se puede identificar por comercio; no es un cargo disputable por este canal"),
                     ("amount_usd", "se completa con la tasa del día en `amount_usd_filled`"),
                     ("amount_usd_filled", "monto en USD ya completado: es el que usa el umbral de autoservicio de R6")):
        k = con.execute(f"SELECT count(*) FROM transactions WHERE {col} IS NULL").fetchone()[0]
        L.append(f"| `{col}` | {frac(k, tot)} | {why} |")
    rng = con.execute("""SELECT sum((amount <= 0)::INT), sum((fraud_score < 0 OR fraud_score > 100)::INT),
                         sum((transaction_date > process_date + INTERVAL 2 DAY)::INT) FROM transactions""").fetchone()
    cast = con.execute("SELECT coalesce(sum(n_failed), 0), count(*) FROM cast_failures").fetchone()
    files = con.execute("SELECT count(*), sum(rows), coalesce(sum(rejected_rows), 0), sum((error IS NOT NULL)::INT) FROM ingest_log").fetchone()
    fresh = con.execute("SELECT max(process_date), max(transaction_date) FROM transactions").fetchone()
    built = con.execute("SELECT CAST(built_at AS VARCHAR) FROM build_info").fetchone()[0]
    L += ["", "**Rangos y tipos:**", "",
          f"- Montos ≤ 0: {n(rng[0])}. `fraud_score` fuera de 0–100: {n(rng[1])}. Movimientos con fecha más de 2 días después de su partición: {n(rng[2])}.",
          f"- Valores que no se pudieron convertir al tipo del diccionario: {n(cast[0])} ({cast[1]} columnas con tipo revisadas, tabla `cast_failures`).",
          f"- Archivos leídos: {n(files[0])} CSV, {n(files[1])} filas; filas rechazadas al leer: {n(files[2])}; archivos con error: {n(files[3] or 0)}.",
          "", "**Claves huérfanas** (las tres dan 0 en la carga completa): transacciones con producto inexistente, productos sin cliente y "
          "transacciones cuyo cliente no es el dueño del producto. La última es la que rompería el aislamiento por cliente.", "",
          f"**Frescura:** última partición `process_date` = {fresh[0]}; último movimiento = {str(fresh[1])[:16]}; base construida el {str(built)[:16]}. "
          "El chat muestra al cliente \"datos actualizados al…\" con esa fecha.", ""]
    return L


# ------------------------------------------------------------------ 2. demanda
def demand(con, plt) -> list[str]:
    total = con.execute("SELECT count(*) FROM transactions").fetchone()[0]
    disp = con.execute(f"SELECT count(*) FROM transactions WHERE {DISPUTABLE}").fetchone()[0]
    by_cat = con.execute(f"SELECT merchant_category, count(*) FROM transactions WHERE {DISPUTABLE} GROUP BY 1 ORDER BY 2 DESC").fetchall()
    by_ch = con.execute(f"SELECT channel, count(*) FROM transactions WHERE {DISPUTABLE} GROUP BY 1 ORDER BY 2 DESC").fetchall()
    by_hour = con.execute(f"SELECT hour(transaction_date), count(*) FROM transactions WHERE {DISPUTABLE} GROUP BY 1 ORDER BY 1").fetchall()
    status = con.execute("SELECT transaction_status, count(*) FROM transactions GROUP BY 1 ORDER BY 2 DESC").fetchall()
    # cargos "parecidos": otro cargo disputable del mismo cliente, en ±30 días, con monto a ±10 % (lo que obliga a aclarar)
    sample = con.execute(f"""
        WITH d AS (SELECT customer_id, transaction_id, transaction_date, amount, currency FROM transactions
                   WHERE {DISPUTABLE} AND transaction_status = 'Approved' AND hash(customer_id) % 20 = 0)
        SELECT count(*) AS n,
               sum(EXISTS (SELECT 1 FROM d o WHERE o.customer_id = d.customer_id AND o.transaction_id <> d.transaction_id
                           AND o.currency = d.currency AND abs(o.amount - d.amount) <= 0.10 * d.amount
                           AND abs(date_diff('day', o.transaction_date, d.transaction_date)) <= 30)::INT) AS similar,
               sum(EXISTS (SELECT 1 FROM d o WHERE o.customer_id = d.customer_id AND o.transaction_id <> d.transaction_id
                           AND o.currency = d.currency AND o.amount = d.amount
                           AND abs(date_diff('day', o.transaction_date, d.transaction_date)) <= 30)::INT) AS same
        FROM d""").fetchone()
    claims = con.execute("SELECT category, count(*) FROM complaints WHERE case_type = 'Claim' GROUP BY 1 ORDER BY 2 DESC").fetchall()
    claims_total = sum(c for _, c in claims)

    fig, ax = plt.subplots(1, 3, figsize=(15, 4.2))
    ax[0].barh([c or "sin categoría" for c, _ in by_cat][::-1], [v / disp * 100 for _, v in by_cat][::-1])
    ax[0].set(title="¿En qué tipo de comercio se concentran\nlos cargos disputables?", xlabel="% de los cargos disputables")
    ax[1].bar([c for c, _ in by_ch], [v / disp * 100 for _, v in by_ch])
    ax[1].set(title="¿Por qué canal entran los cargos disputables?", ylabel="%")
    ax[1].tick_params(axis="x", rotation=30)
    ax[2].bar([h for h, _ in by_hour], [v / disp * 100 for _, v in by_hour])
    ax[2].set(title="¿A qué hora ocurren los cargos disputables?", xlabel="hora del día", ylabel="%")
    fig.tight_layout()
    fig.savefig(FIG / "demanda-cargos-disputables.png", dpi=110)

    top = by_cat[0]
    pend = dict(status).get("Pending", 0)
    L = ["## 2. Demanda (desde el dataset)", "",
         "El dataset no tiene disputas etiquetadas por movimiento, así que se mira el universo de **cargos disputables por este canal**: "
         f"compras con comercio ({frac(disp, total)} de los movimientos). Es un proxy de dónde pueden aparecer las disputas, no un conteo de disputas.", "",
         "![Cargos disputables por comercio, canal y hora](analytics/figures/demanda-cargos-disputables.png)", "",
         f"- **¿Dónde se concentran?** La categoría con más cargos disputables es `{top[0]}` ({frac(top[1], disp)}); la distribución entre "
         f"categorías es bastante pareja ({len(by_cat)} categorías, la menor con {frac(by_cat[-1][1], disp)}). "
         f"Canal principal: `{by_ch[0][0]}` ({frac(by_ch[0][1], disp)}).",
         f"- **¿Qué tan frecuentes son los cargos parecidos?** En una muestra del 5 % de los clientes ({n(sample[0])} cargos aprobados), "
         f"{frac(sample[1], sample[0])} tienen otro cargo del mismo cliente con monto a ±10 % en ±30 días, y {frac(sample[2], sample[0])} "
         "tienen otro con el **mismo** monto. Son los casos en que el monto no alcanza para identificar el cargo y el asistente tiene que "
         "aclarar (lista de candidatas, máximo 3 vueltas).",
         f"- **¿Qué proporción queda pendiente?** {frac(pend, total)} de los movimientos están en estado `Pending` "
         "(R2: se informa, no se abre el reclamo formal; R2b: si el cliente afirma que no lo hizo, va al equipo de fraude). "
         "Estados: " + ", ".join(f"`{s}` {frac(c, total)}" for s, c in status) + ".",
         f"- **Reclamos registrados en el dataset** (`complaints`, tipo `Claim`): {n(claims_total)}; por categoría: "
         + ", ".join(f"{c} {frac(v, claims_total)}" for c, v in claims[:5]) + ". Sus descripciones son de plantilla, así que no se usan como texto.", ""]
    return L


# ------------------------------------------------------------------ 3. operación (corridas de evaluación)
def bucket(case: dict) -> str:
    if case["outcome"] == "escalated":
        return "escalamiento"
    rounds = max([(t.get("response") or {}).get("clarification_round") or 0 for t in case["turns"] if isinstance(t.get("response"), dict)] + [0])
    if case["outcome"] == "clarified_then_resolved" or rounds >= 1:
        return "aclaración"
    if case["outcome"] == "abstained":
        return "abstención"
    return "resolución automática"


def operations(raw_dir: Path, plt) -> tuple[list[str], dict]:
    runs = {}
    for f in sorted(raw_dir.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        runs[(d["variant"], d["split"])] = (f.name, d)          # el último crudo de cada variante y split
    if not runs:
        return ["## 3. Operación", "", "Sin crudos del harness en `eval/results/raw/`: correr `python -m eval.run` primero.", ""], {}
    order = ("resolución automática", "aclaración", "escalamiento", "abstención")
    L = ["## 3. Operación (desde las trazas de las corridas de evaluación)", "",
         "Fuente: los crudos del harness (`eval/results/raw/`, fuera de git) de la última corrida de cada variante. Son casos de "
         "evaluación, no tráfico real: describen cómo se comporta el sistema ante los escenarios del set, no la mezcla de producción.", "",
         "| Variante | Split | Casos | Resolución automática | Aclaración | Escalamiento | Abstención | Pasan todo | Costo por caso correctamente atendido |",
         "|---|---|---|---|---|---|---|---|---|"]
    node_lat, summary, bars = defaultdict(list), {}, {}
    for (variant, split), (name, d) in sorted(runs.items()):
        cases = d["cases"]
        c = Counter(bucket(x) for x in cases)
        ok = sum(all(ch["passed"] for ch in x["checks"]) for x in cases)
        cost = sum(x["cost_usd"] or 0 for x in cases)
        failed = sum(bool(s.get("error")) for x in cases for s in x["traces"] or [] if s["kind"] == "llm")
        calls = sum(1 for x in cases for s in x["traces"] or [] if s["kind"] == "llm")
        L.append(f"| `{variant}` | {split} | {len(cases)} | " + " | ".join(frac(c[k], len(cases)) for k in order)
                 + f" | {frac(ok, len(cases))} | {'$%.4f' % (cost / ok) if ok and cost else '$0 (sin LLM)' if ok else '—'} |")
        summary[(variant, split)] = {"cases": len(cases), "ok": ok, "cost": cost, "contained": len(cases) - c["escalamiento"],
                                     "file": name, "llm_failed": failed, "llm_calls": calls}
        bars[f"{variant}\n{split}"] = [c[k] / len(cases) * 100 for k in order]
        if variant in ("sistema_api", "sistema_cascade"):
            for x in cases:
                for s in x["traces"] or []:
                    if s.get("latency_ms") and (s["kind"] == "llm" or s.get("tool")):
                        node_lat[(variant, s["node"])].append(s["latency_ms"])
    bad = [f"`{v}`/{s} ({x['llm_failed']}/{x['llm_calls']})" for (v, s), x in summary.items() if x["llm_calls"] and x["llm_failed"] / x["llm_calls"] > 0.05]
    if bad:
        L += ["", "> ⚠ Corridas con más del 5 % de llamadas LLM fallidas (miden los fallbacks, no el modelo): " + ", ".join(bad)]
    L += ["", "Crudos usados: " + ", ".join(f"`{x['file']}`" for x in summary.values()) + ".", "",
          "![Resultado por variante](analytics/figures/operacion-resultados.png)", ""]
    fig, ax = plt.subplots(figsize=(max(7, 1.6 * len(bars)), 4.2))
    bottom = [0.0] * len(bars)
    for i, k in enumerate(order):
        vals = [v[i] for v in bars.values()]
        ax.bar(list(bars), vals, bottom=bottom, label=k)
        bottom = [b + v for b, v in zip(bottom, vals)]
    ax.set(ylabel="% de los casos", title="¿Cómo termina cada caso: solo, con aclaración o con una persona?")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG / "operacion-resultados.png", dpi=110)

    L += ["**Latencia por nodo** (llamadas al LLM y tools, en las corridas con la API real):", "",
          "| Variante | Nodo | Llamadas | p50 | p95 |", "|---|---|---|---|---|"]
    rows = sorted(node_lat.items(), key=lambda kv: (kv[0][0], -pct(kv[1], 0.5)))
    for (variant, node), vals in rows:
        L.append(f"| `{variant}` | `{node}` | {len(vals)} | {pct(vals, 0.5):.0f} ms | {pct(vals, 0.95):.0f} ms |")
    api = {k: v for k, v in node_lat.items() if k[0] == "sistema_api"}
    if api:
        top = sorted(api.items(), key=lambda kv: -pct(kv[1], 0.5))[:8]
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.barh([k[1] for k, _ in top][::-1], [pct(v, 0.95) for _, v in top][::-1], label="p95", color="lightgray")
        ax.barh([k[1] for k, _ in top][::-1], [pct(v, 0.5) for _, v in top][::-1], label="p50")
        ax.set(xlabel="ms", title="¿Qué nodo tarda más en responder? (sistema_api)")
        ax.legend()
        fig.tight_layout()
        fig.savefig(FIG / "operacion-latencia-por-nodo.png", dpi=110)
        L += ["", "![Latencia por nodo](analytics/figures/operacion-latencia-por-nodo.png)"]
    L.append("")
    return L, summary


# ------------------------------------------------------------------ 4. ROI
def roi(summary: dict, plt) -> list[str]:
    a = tomllib.loads(ROI_FILE.read_text(encoding="utf-8"))["assumptions"]
    r = roi_numbers(a)
    measured = summary.get(("sistema_api", "dev"))
    L = ["## 4. ROI (estimación con supuestos explícitos)", "",
         "**Esto es una estimación, no un resultado.** Los supuestos están en `backend/config/roi.toml`, son del equipo y se pueden "
         "editar; el endpoint `/api/admin/metrics/roi` devuelve los mismos números.", "",
         "| Supuesto | Valor | Origen |", "|---|---|---|",
         f"| Costo de una persona por minuto | ${a['agent_cost_per_minute_usd']:.2f} | supuesto del equipo |",
         f"| Minutos por caso atendido por una persona | {a['minutes_per_case_human']} | medido en el dataset (duración media de `call_center_interactions`) |",
         f"| Casos por mes | {n(a['cases_per_month'])} | supuesto del equipo |",
         f"| Casos que no pasan a una persona | {a['automatable_share']:.0%} | supuesto, apoyado en la contención medida en dev"
         + (f" ({frac(measured['contained'], measured['cases'])})" if measured else "") + " |",
         f"| Costo de LLM por caso | ${a['llm_cost_per_case_usd']:.4f} | medido (`sistema_api`)"
         + (f": ${measured['cost'] / measured['cases']:.4f} en la última corrida" if measured and measured["cost"] else "") + " |",
         f"| Costo fijo mensual | ${a['fixed_monthly_cost_usd']:.2f} | hosting de la demo + mantenimiento estimado |", "",
         f"- Costo de un caso atendido por una persona: **${r['human_cost_per_case_usd']:.2f}**.",
         f"- Ahorro estimado por caso (incluye el costo de LLM de los casos que igual pasan a una persona): **${r['saving_per_case_usd']:.2f}**.",
         f"- Ahorro mensual estimado con {n(a['cases_per_month'])} casos: **${r['monthly_saving_usd']:,.0f}**.".replace(",", "."),
         f"- **Punto de equilibrio:** {n(r['break_even_cases_per_month'])} casos por mes." if r["break_even_cases_per_month"] else "- Sin punto de equilibrio con estos supuestos.",
         "", "![ROI](analytics/figures/roi-punto-de-equilibrio.png)", "",
         "Lo que este cálculo **no** incluye: el costo de construir y evaluar el sistema, el de los casos que el asistente atiende mal "
         "(se miden en la evaluación, no en dinero) y el efecto en la satisfacción del cliente.", ""]
    xs = list(range(0, int(a["cases_per_month"] * 1.5) + 1, max(1, int(a["cases_per_month"] / 50))))
    fig, ax = plt.subplots(figsize=(8, 4))
    for share, style in ((a["automatable_share"], "-"), (max(a["automatable_share"] - 0.2, 0), "--"), (min(a["automatable_share"] + 0.1, 1), ":")):
        s = roi_numbers({**a, "automatable_share": share})["saving_per_case_usd"]
        ax.plot(xs, [x * s - a["fixed_monthly_cost_usd"] for x in xs], style, label=f"{share:.0%} sin persona")
    ax.axhline(0, color="gray", lw=0.8)
    ax.set(xlabel="casos por mes", ylabel="ahorro mensual estimado (USD)", title="¿Desde cuántos casos por mes se paga solo? (estimación)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIG / "roi-punto-de-equilibrio.png", dpi=110)
    return L


def main() -> int:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    FIG.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(os.environ.get("DUCKDB_PATH") or str(REPO / "data" / "bank.duckdb"), read_only=True)
    ops, summary = operations(REPO / "eval" / "results" / "raw", plt)
    L = ["# Analítica operativa", "",
         f"Generado por `python -m analytics.report` el {date.today()}. Regenera este documento y sus figuras; el notebook "
         "`analysis/analytics.ipynb` llama a las mismas funciones. Solo preguntas operativas: cada figura responde la pregunta de su título.", "",
         "- Mediciones del dataset y de las corridas de evaluación: **medido**. ROI: **estimación** con supuestos.",
         "- Endpoints para el panel: `/api/admin/metrics/operations`, `/latency` y `/roi` ([api-contract.md](api-contract.md)).", ""]
    L += data_quality(con) + demand(con, plt) + ops + roi(summary, plt)
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"escrito {OUT.relative_to(REPO)} y {len(list(FIG.glob('*.png')))} figuras")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
