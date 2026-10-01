"""Ciclo de vida de la conversación, varios cargos con una confirmación y regla R2b.

- app.conversations:
  - previous_conversation_id: conversación anterior enlazada, para retomar el cargo en foco.
  - closed_reason: por qué se cerró (cliente | inactividad). Ningún resultado cierra la conversación por sí solo.
- app.dispute_cases: una confirmación puede crear varios reclamos, uno por transacción.
  - El token y la Idempotency-Key dejan de ser únicos por sí solos.
  - Pasan a ser únicos junto con transaction_id: el mismo token o el mismo reintento nunca crean dos reclamos
    sobre la misma transacción.
- app.handoffs: motivo nuevo cargo_pendiente_no_reconocido (R2b).

Revision ID: 0005
Revises: 0004
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_REASONS = ("fuera_de_plazo", "riesgo_alto", "riesgo_desconocido", "aclaracion_agotada", "pide_humano", "fallo_tool",
               "accion_no_verificada", "acceso_no_autorizado", "reposicion_tarjeta")
NEW_REASONS = OLD_REASONS + ("cargo_pendiente_no_reconocido",)


def _in(values) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    op.add_column("conversations", sa.Column("previous_conversation_id", sa.String(40),
                  sa.ForeignKey("app.conversations.conversation_id", name=op.f("fk_conversations_previous_conversation_id_conversations")),
                  comment="Conversación anterior del mismo cliente; se hereda el cargo en foco."), schema="app")
    op.add_column("conversations", sa.Column("closed_reason", sa.String(20),
                  comment="cliente (se despidió) | inactividad. Los resultados no cierran la conversación."), schema="app")
    op.create_check_constraint(op.f("ck_conversations_closed_reason"), "conversations",
                               "closed_reason IS NULL OR closed_reason IN ('cliente', 'inactividad')", schema="app")
    op.drop_constraint("uq_dispute_cases_confirmation_token_id", "dispute_cases", schema="app")
    op.drop_constraint("uq_dispute_cases_idempotency_key", "dispute_cases", schema="app")
    op.create_unique_constraint(op.f("uq_dispute_cases_confirmation_token_id_transaction_id"), "dispute_cases",
                                ["confirmation_token_id", "transaction_id"], schema="app")
    op.create_unique_constraint(op.f("uq_dispute_cases_idempotency_key_transaction_id"), "dispute_cases",
                                ["idempotency_key", "transaction_id"], schema="app")
    op.drop_constraint("ck_handoffs_reason_code", "handoffs", schema="app")
    op.create_check_constraint(op.f("ck_handoffs_reason_code"), "handoffs", f"reason_code IN ({_in(NEW_REASONS)})", schema="app")


def downgrade() -> None:
    op.execute(f"UPDATE app.handoffs SET reason_code = 'pide_humano' WHERE reason_code NOT IN ({_in(OLD_REASONS)})")
    op.drop_constraint("ck_handoffs_reason_code", "handoffs", schema="app")
    op.create_check_constraint(op.f("ck_handoffs_reason_code"), "handoffs", f"reason_code IN ({_in(OLD_REASONS)})", schema="app")
    op.drop_constraint("uq_dispute_cases_idempotency_key_transaction_id", "dispute_cases", schema="app")
    op.drop_constraint("uq_dispute_cases_confirmation_token_id_transaction_id", "dispute_cases", schema="app")
    op.create_unique_constraint(op.f("uq_dispute_cases_idempotency_key"), "dispute_cases", ["idempotency_key"], schema="app")
    op.create_unique_constraint(op.f("uq_dispute_cases_confirmation_token_id"), "dispute_cases", ["confirmation_token_id"], schema="app")
    op.drop_constraint("ck_conversations_closed_reason", "conversations", schema="app")
    op.drop_column("conversations", "closed_reason", schema="app")
    op.drop_column("conversations", "previous_conversation_id", schema="app")
