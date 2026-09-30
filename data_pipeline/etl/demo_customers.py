"""Selección determinista de clientes de demo por escenario.

No se versiona ninguna lista de customer_id (P-04: no publicar derivados del dataset); se
versiona la REGLA. Con los mismos datos y la misma semilla, la selección es siempre la misma:
por cada escenario se ordenan los clientes que lo cumplen por hash(customer_id, semilla).

Escenarios (ventana de 60 días antes de la fecha de referencia, tipos disputables
Purchase/Payment/Withdrawal; ver docs/policies.md):
    cargo_claro        un cargo Approved en los últimos 30 días sin otro de monto ±10 % en la ventana
    cargos_parecidos   dos o más cargos en la ventana con montos a ±10 % entre sí
    pendiente          un cargo Pending en la ventana
    revertido          un cargo Reversed en la ventana
    fraude_alto        un cargo con fraud_score >= 80 en la ventana
    fuera_de_plazo     un cargo Approved de hace 61–120 días (regla R1)
"""
from __future__ import annotations

import os
from datetime import date

import pandas as pd

from data_pipeline.config import SEED

RULE_VERSION = "demo_customers v1"
SCENARIOS = ("cargo_claro", "cargos_parecidos", "pendiente", "revertido", "fraude_alto", "fuera_de_plazo")
DISPUTABLE = "transaction_type IN ('Purchase', 'Payment', 'Withdrawal')"
HIGH_FRAUD = 80


def reference_date(con) -> date:
    env = os.environ.get("REFERENCE_DATE")
    if env:
        return date.fromisoformat(env)
    return con.execute("SELECT max(process_date) FROM transactions").fetchone()[0]


def scenario_candidates(con, ref: date, seed: int = SEED) -> pd.DataFrame:
    """customer_id, scenario, orden determinista dentro del escenario."""
    return con.execute(f"""
    WITH w AS (
      SELECT customer_id, transaction_id, amount, transaction_status, fraud_score, process_date
      FROM transactions
      WHERE {DISPUTABLE} AND process_date BETWEEN DATE '{ref}' - INTERVAL 120 DAY AND DATE '{ref}'),
    win AS (SELECT * FROM w WHERE process_date >= DATE '{ref}' - INTERVAL 60 DAY),
    sim AS (
      SELECT DISTINCT a.customer_id, a.transaction_id FROM win a JOIN win b
        ON a.customer_id = b.customer_id AND a.transaction_id <> b.transaction_id
       AND abs(a.amount - b.amount) <= 0.10 * a.amount),
    s AS (
      SELECT DISTINCT customer_id, 'cargo_claro' AS scenario FROM win
       WHERE transaction_status = 'Approved' AND process_date >= DATE '{ref}' - INTERVAL 30 DAY
         AND transaction_id NOT IN (SELECT transaction_id FROM sim)
      UNION ALL SELECT DISTINCT customer_id, 'cargos_parecidos' FROM sim
      UNION ALL SELECT DISTINCT customer_id, 'pendiente' FROM win WHERE transaction_status = 'Pending'
      UNION ALL SELECT DISTINCT customer_id, 'revertido' FROM win WHERE transaction_status = 'Reversed'
      UNION ALL SELECT DISTINCT customer_id, 'fraude_alto' FROM win WHERE fraud_score >= {HIGH_FRAUD}
      UNION ALL SELECT DISTINCT customer_id, 'fuera_de_plazo' FROM w
       WHERE transaction_status = 'Approved' AND process_date < DATE '{ref}' - INTERVAL 60 DAY)
    SELECT customer_id, scenario, row_number() OVER (PARTITION BY scenario ORDER BY hash(customer_id, {seed})) AS rk
    FROM s""").df()


def select_demo(con, per_scenario: int, seed: int = SEED, strict: bool = True) -> tuple[pd.DataFrame, date]:
    """`per_scenario` clientes distintos por escenario, cada cliente en un solo escenario.

    Con strict=False un escenario sin clientes suficientes no es error (p. ej. en el fixture).
    """
    ref = reference_date(con)
    cand = scenario_candidates(con, ref, seed).sort_values(["rk", "scenario"])
    chosen, rows = set(), []
    for sc in SCENARIOS:
        pool = cand[(cand.scenario == sc) & ~cand.customer_id.isin(chosen)].sort_values("rk")
        pick = pool.head(per_scenario)
        if strict and len(pick) < per_scenario:
            raise RuntimeError(f"escenario {sc}: solo {len(pick)} clientes cumplen la regla")
        chosen |= set(pick.customer_id)
        rows += [dict(customer_id=c, scenario=sc, scenario_rank=i + 1, reference_date=ref)
                 for i, c in enumerate(pick.customer_id)]
    return pd.DataFrame(rows), ref


def rule_text(n: int, seed: int, ref: date) -> str:
    """Descripción de la regla que se guarda en ops.etl_runs.customer_rule."""
    return (f"{RULE_VERSION}: n={n}; ceil(n/12) clientes por escenario ({', '.join(SCENARIOS)}) en orden "
            f"hash(customer_id, seed), resto en el mismo orden; reference_date={ref}; ventana 60 días")


def sample_customers(con, n: int, seed: int = SEED) -> tuple[list[str], pd.DataFrame, date]:
    """Subconjunto determinista de n clientes que cubre todos los escenarios.

    Primero ceil(n/12) clientes por escenario (al menos 1); el resto, clientes cualesquiera en
    orden de hash(customer_id, semilla).
    """
    per = max(1, -(-n // (2 * len(SCENARIOS))))
    if per * len(SCENARIOS) > n:
        raise ValueError(f"--customers-sample debe ser >= {len(SCENARIOS)} para cubrir todos los escenarios")
    demo, ref = select_demo(con, per, seed)
    ids = list(demo.customer_id)
    seen = set(ids)
    rest = con.execute(f"SELECT customer_id FROM customers ORDER BY hash(customer_id, {seed})").df().customer_id
    for c in rest:
        if len(ids) >= n:
            break
        if c not in seen:
            ids.append(c)
            seen.add(c)
    return ids, demo, ref
