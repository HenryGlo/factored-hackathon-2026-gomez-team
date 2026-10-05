"""app.conversations.origin: 'real' | 'synthetic'. Las conversaciones sintéticas (scripts/seed_synthetic_history.py) dan volumen a
la analítica del administrador en entornos de demostración; siempre van marcadas y la analítica permite separarlas.

Revision ID: 0012
Revises: 0011
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0012"
down_revision: Union[str, Sequence[str], None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""ALTER TABLE app.conversations ADD COLUMN origin varchar(12) NOT NULL DEFAULT 'real'
                  CONSTRAINT ck_conversations_origin CHECK (origin IN ('real', 'synthetic'))""")
    op.execute("COMMENT ON COLUMN app.conversations.origin IS 'real: de un cliente. synthetic: sembrada para la analítica de demostración.'")
    op.execute("CREATE INDEX ix_conversations_origin_created_at ON app.conversations (origin, created_at)")


def downgrade() -> None:
    op.execute("DROP INDEX app.ix_conversations_origin_created_at")
    op.execute("ALTER TABLE app.conversations DROP COLUMN origin")
