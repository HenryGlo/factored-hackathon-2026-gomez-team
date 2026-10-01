"""Tickets para agentes humanos sobre los handoffs (prompt 08, A4).

- app.handoffs gana: ticket_status (nuevo | en_curso | esperando_cliente | resuelto), assigned_to (usuario),
  first_response_at y resolved_at. El handoff y su payload no cambian.
- app.ticket_events: registro de auditoría de cada cambio (asignación, cambio de estado, nota interna) con quién y cuándo.
  Solo inserción para la app; la consola lo lee.

Revision ID: 0009
Revises: 0008
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0009"
down_revision: Union[str, Sequence[str], None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE app.handoffs
        ADD COLUMN ticket_status varchar(20) NOT NULL DEFAULT 'nuevo'
            CONSTRAINT ck_handoffs_ticket_status CHECK (ticket_status IN ('nuevo', 'en_curso', 'esperando_cliente', 'resuelto')),
        ADD COLUMN assigned_to varchar(40),
        ADD COLUMN first_response_at timestamptz,
        ADD COLUMN resolved_at timestamptz""")
    op.execute("CREATE INDEX ix_handoffs_ticket_status ON app.handoffs (ticket_status, priority, created_at)")
    op.execute("""
    CREATE TABLE app.ticket_events (
        event_id       bigserial PRIMARY KEY,
        handoff_id     varchar(40) NOT NULL REFERENCES app.handoffs (handoff_id),
        actor_user_id  varchar(40) NOT NULL,
        actor_username varchar(60) NOT NULL,
        kind           varchar(20) NOT NULL CHECK (kind IN ('asignacion', 'estado', 'nota')),
        from_value     varchar(60),
        to_value       varchar(60),
        note           varchar(2000),
        created_at     timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX ix_ticket_events_handoff ON app.ticket_events (handoff_id, event_id)")
    op.execute("REVOKE ALL ON app.ticket_events FROM app_rw")
    op.execute("GRANT SELECT, INSERT ON app.ticket_events TO app_rw")
    op.execute("GRANT USAGE, SELECT ON SEQUENCE app.ticket_events_event_id_seq TO app_rw")
    op.execute("GRANT SELECT ON app.ticket_events TO app_ro")


def downgrade() -> None:
    op.execute("DROP TABLE app.ticket_events")
    op.execute("DROP INDEX app.ix_handoffs_ticket_status")
    op.execute("""ALTER TABLE app.handoffs DROP COLUMN ticket_status, DROP COLUMN assigned_to,
                  DROP COLUMN first_response_at, DROP COLUMN resolved_at""")
