"""app.ticket_events: una nota interna se puede borrar sin perder el historial.

El historial del ticket es de solo inserción (0009) y lo sigue siendo: borrar una nota la MARCA (`deleted_at`, `deleted_by`) y
la API deja de devolver su texto, pero la fila y el texto quedan en la base como registro. app_rw recibe UPDATE solo sobre
esas dos columnas: sigue sin poder reescribir una nota, borrar filas ni tocar asignaciones o cambios de estado.

Revision ID: 0013
Revises: 0012
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0013"
down_revision: Union[str, Sequence[str], None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE app.ticket_events ADD COLUMN deleted_at timestamptz, ADD COLUMN deleted_by varchar(60)")
    op.execute("COMMENT ON COLUMN app.ticket_events.deleted_at IS 'Nota borrada por su autor: la API ya no devuelve el texto; la fila queda.'")
    op.execute("GRANT UPDATE (deleted_at, deleted_by) ON app.ticket_events TO app_rw")


def downgrade() -> None:
    op.execute("REVOKE UPDATE (deleted_at, deleted_by) ON app.ticket_events FROM app_rw")
    op.execute("ALTER TABLE app.ticket_events DROP COLUMN deleted_at, DROP COLUMN deleted_by")
