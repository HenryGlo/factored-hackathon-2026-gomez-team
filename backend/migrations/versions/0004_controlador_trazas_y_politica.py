"""Controlador, trazas y política (fase 4 del prompt 03).

- app.conversations: session_date ('hoy' de la conversación) y context (estado del controlador).
- app.confirmation_tokens: invalidated_at; acción create_handoff (reposición de tarjeta).
- app.dispute_cases: CHECK de reason_code (unrecognized, amount_mismatch, duplicate).
- app.handoffs: cola (fraude, disputas, tarjetas, general) y motivos nuevos riesgo_desconocido y
  reposicion_tarjeta.
- app.traces: kind pasa a llm | ml | code; implementación, ID real del modelo y reglas evaluadas.

Generada con autogenerate y revisada a mano (los CHECK no los detecta autogenerate).

Revision ID: 0004
Revises: 0003
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_REASONS = ("fuera_de_plazo", "riesgo_alto", "aclaracion_agotada", "pide_humano", "fallo_tool",
               "accion_no_verificada", "acceso_no_autorizado")
NEW_REASONS = ("fuera_de_plazo", "riesgo_alto", "riesgo_desconocido", "aclaracion_agotada", "pide_humano", "fallo_tool",
               "accion_no_verificada", "acceso_no_autorizado", "reposicion_tarjeta")


def _in(values) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _replace_check(table: str, name: str, condition: str) -> None:
    op.drop_constraint(name, table, schema="app")
    op.create_check_constraint(op.f(name), table, condition, schema="app")


def upgrade() -> None:
    op.add_column("conversations", sa.Column("session_date", sa.Date(), server_default=sa.text("CURRENT_DATE"), nullable=False,
                  comment="'Hoy' de la conversación: resuelve fechas relativas y la regla R1 (REFERENCE_DATE o simulada en el harness)."),
                  schema="app")
    op.add_column("conversations", sa.Column("context", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False,
                  comment="Estado del controlador: intención, pistas, candidatas mostradas, movimiento elegido, acción pendiente."),
                  schema="app")
    op.add_column("confirmation_tokens", sa.Column("invalidated_at", sa.DateTime(timezone=True),
                  comment="Anulado sin usarse: el cliente cambió de movimiento o se emitió otro token."), schema="app")
    _replace_check("confirmation_tokens", "ck_confirmation_tokens_action",
                   "action IN ('create_dispute_case', 'lock_card', 'create_handoff')")
    op.execute("UPDATE app.dispute_cases SET reason_code = 'unrecognized' WHERE reason_code NOT IN "
               "('unrecognized', 'amount_mismatch', 'duplicate')")
    op.create_check_constraint(op.f("ck_dispute_cases_reason_code"), "dispute_cases",
                               "reason_code IN ('unrecognized', 'amount_mismatch', 'duplicate')", schema="app")
    op.add_column("handoffs", sa.Column("queue", sa.String(20), server_default="general", nullable=False), schema="app")
    op.create_check_constraint(op.f("ck_handoffs_queue"), "handoffs", "queue IN ('fraude', 'disputas', 'tarjetas', 'general')",
                               schema="app")
    _replace_check("handoffs", "ck_handoffs_reason_code", f"reason_code IN ({_in(NEW_REASONS)})")
    # trazas: tipo llm | ml | code
    op.drop_constraint("ck_traces_kind", "traces", schema="app")
    op.execute("UPDATE app.traces SET kind = 'code' WHERE kind IN ('tool', 'policy', 'controller')")
    op.create_check_constraint(op.f("ck_traces_kind"), "traces", "kind IN ('llm', 'ml', 'code')", schema="app")
    op.alter_column("traces", "kind", existing_type=sa.String(20), existing_nullable=False,
                    comment="llm | ml | code (tools, política y controlador son código).", schema="app")
    op.add_column("traces", sa.Column("implementation", sa.String(60),
                  comment="Implementación y versión del componente (p. ej. rule@v3, keyword@v1)."), schema="app")
    op.add_column("traces", sa.Column("model_id", sa.String(80), comment="ID real que devolvió el proveedor."), schema="app")
    op.add_column("traces", sa.Column("rules", postgresql.JSONB(),
                  comment="Reglas de política evaluadas en el paso: [{id, resultado, motivo, evidencia}]."), schema="app")
    op.alter_column("traces", "model", existing_type=sa.String(80), existing_nullable=True,
                    comment="Alias pedido (haiku | sonnet).", schema="app")
    op.alter_column("traces", "payload", existing_type=postgresql.JSONB(), existing_nullable=False,
                    existing_server_default=sa.text("'{}'::jsonb"), comment="Entrada y salida del paso. Sin cadena de pensamiento.",
                    schema="app")


def downgrade() -> None:
    op.alter_column("traces", "payload", existing_type=postgresql.JSONB(), existing_nullable=False,
                    existing_server_default=sa.text("'{}'::jsonb"),
                    comment="Entradas y salidas (enmascaradas), reglas evaluadas. Sin cadena de pensamiento.", schema="app")
    op.alter_column("traces", "model", existing_type=sa.String(80), existing_nullable=True, comment=None, schema="app")
    for col in ("rules", "model_id", "implementation"):
        op.drop_column("traces", col, schema="app")
    op.alter_column("traces", "kind", existing_type=sa.String(20), existing_nullable=False, comment=None, schema="app")
    op.drop_constraint("ck_traces_kind", "traces", schema="app")
    op.execute("UPDATE app.traces SET kind = CASE WHEN kind = 'llm' THEN 'llm' ELSE 'controller' END")
    op.create_check_constraint(op.f("ck_traces_kind"), "traces", "kind IN ('llm', 'tool', 'policy', 'controller')", schema="app")
    op.execute(f"UPDATE app.handoffs SET reason_code = 'pide_humano' WHERE reason_code NOT IN ({_in(OLD_REASONS)})")
    _replace_check("handoffs", "ck_handoffs_reason_code", f"reason_code IN ({_in(OLD_REASONS)})")
    op.drop_constraint("ck_handoffs_queue", "handoffs", schema="app")
    op.drop_column("handoffs", "queue", schema="app")
    op.drop_constraint("ck_dispute_cases_reason_code", "dispute_cases", schema="app")
    op.execute("UPDATE app.confirmation_tokens SET invalidated_at = now() WHERE action = 'create_handoff'")
    op.execute("DELETE FROM app.confirmation_tokens WHERE action = 'create_handoff'")
    _replace_check("confirmation_tokens", "ck_confirmation_tokens_action", "action IN ('create_dispute_case', 'lock_card')")
    op.drop_column("confirmation_tokens", "invalidated_at", schema="app")
    op.drop_column("conversations", "context", schema="app")
    op.drop_column("conversations", "session_date", schema="app")
