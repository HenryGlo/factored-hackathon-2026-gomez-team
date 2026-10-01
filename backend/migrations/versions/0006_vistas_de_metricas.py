"""Vistas de métricas sobre app.traces para el panel de administración (prompt 05, fase 3).

- app.v_llm_daily: por día (UTC), nodo, modelo y proveedor: llamadas, errores, fallbacks, costo, latencia p50/p95.
  Las plantillas del modo degradado (implementation = 'fake') también aparecen, separadas por proveedor.
- app.v_turn_daily: por día: turnos, suma de latencias de los pasos (p50/p95), costo, llamadas al LLM y turnos con error.
  La suma de pasos es una aproximación del tiempo del turno: intent y extract corren en paralelo y suman los dos.

Lectura para la consola (app_ro) y el backend (app_rw).

Revision ID: 0006
Revises: 0005
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0006"
down_revision: Union[str, Sequence[str], None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LLM_DAILY = """
CREATE VIEW app.v_llm_daily AS
SELECT (t.created_at AT TIME ZONE 'utc')::date AS day,
       t.node,
       coalesce(t.model_id, t.model) AS model,
       t.implementation AS provider,
       count(*) AS calls,
       count(*) FILTER (WHERE t.error IS NOT NULL) AS errors,
       count(*) FILTER (WHERE t.payload->>'fallback' IS NOT NULL) AS fallbacks,
       round(coalesce(sum(t.cost_usd), 0)::numeric, 6) AS cost_usd,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY t.latency_ms)::numeric, 1) AS latency_ms_p50,
       round(percentile_cont(0.95) WITHIN GROUP (ORDER BY t.latency_ms)::numeric, 1) AS latency_ms_p95
FROM app.traces t
WHERE t.kind = 'llm'
GROUP BY 1, 2, 3, 4
"""

TURN_DAILY = """
CREATE VIEW app.v_turn_daily AS
WITH per_turn AS (
    SELECT t.turn_id, min(t.created_at) AS at, sum(t.latency_ms) AS steps_ms, coalesce(sum(t.cost_usd), 0) AS cost_usd,
           count(*) FILTER (WHERE t.kind = 'llm' AND coalesce(t.implementation, '') <> 'fake') AS llm_calls,
           bool_or(t.error IS NOT NULL) AS had_error
    FROM app.traces t GROUP BY t.turn_id)
SELECT (at AT TIME ZONE 'utc')::date AS day,
       count(*) AS turns,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY steps_ms)::numeric, 1) AS steps_ms_p50,
       round(percentile_cont(0.95) WITHIN GROUP (ORDER BY steps_ms)::numeric, 1) AS steps_ms_p95,
       round(sum(cost_usd)::numeric, 6) AS cost_usd,
       sum(llm_calls) AS llm_calls,
       count(*) FILTER (WHERE had_error) AS turns_with_error
FROM per_turn
GROUP BY 1
"""


def upgrade() -> None:
    op.execute(LLM_DAILY)
    op.execute(TURN_DAILY)
    op.execute("GRANT SELECT ON app.v_llm_daily, app.v_turn_daily TO app_ro, app_rw")


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS app.v_turn_daily")
    op.execute("DROP VIEW IF EXISTS app.v_llm_daily")
