"""Prioridad `urgente` en los handoffs: riesgo alto + el cliente afirma que no hizo el cargo (prompt 07, bloque 2).

Revision ID: 0007
Revises: 0006
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0007"
down_revision: Union[str, Sequence[str], None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQL directo: la convención de nombres de Alembic volvería a anteponer "ck_handoffs_" al nombre existente
    op.execute("ALTER TABLE app.handoffs DROP CONSTRAINT ck_handoffs_priority")
    op.execute("ALTER TABLE app.handoffs ADD CONSTRAINT ck_handoffs_priority CHECK (priority IN ('urgente', 'alta', 'media'))")


def downgrade() -> None:
    op.execute("UPDATE app.handoffs SET priority = 'alta' WHERE priority = 'urgente'")
    op.execute("ALTER TABLE app.handoffs DROP CONSTRAINT ck_handoffs_priority")
    op.execute("ALTER TABLE app.handoffs ADD CONSTRAINT ck_handoffs_priority CHECK (priority IN ('alta', 'media'))")
