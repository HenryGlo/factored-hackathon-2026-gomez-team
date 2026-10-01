"""Rol `admin` (prompt 08, A5): panel de administración, SLO y logs. El rol `analyst` sigue siendo el del agente de soporte.

Revision ID: 0010
Revises: 0009
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0010"
down_revision: Union[str, Sequence[str], None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _roles(staff: str, customer_required: str) -> None:
    for table in ("users", "sessions"):
        op.execute(f"ALTER TABLE app.{table} DROP CONSTRAINT ck_{table}_role")
        op.execute(f"ALTER TABLE app.{table} ADD CONSTRAINT ck_{table}_role CHECK (role IN ('customer', {staff}))")
    op.execute("ALTER TABLE app.sessions DROP CONSTRAINT ck_sessions_customer_required")
    op.execute(f"ALTER TABLE app.sessions ADD CONSTRAINT ck_sessions_customer_required CHECK ({customer_required} OR customer_id IS NOT NULL)")


def upgrade() -> None:
    _roles("'analyst', 'admin'", "role IN ('analyst', 'admin')")


def downgrade() -> None:
    op.execute("UPDATE app.users SET role = 'analyst' WHERE role = 'admin'")
    op.execute("DELETE FROM app.sessions WHERE role = 'admin'")
    _roles("'analyst'", "role = 'analyst'")
