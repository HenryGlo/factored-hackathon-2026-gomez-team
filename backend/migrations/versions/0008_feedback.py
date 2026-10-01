"""app.feedback: valoración del cliente sobre una conversación (prompt 08, A2).

Una fila por conversación (la valoración no se edita: queda como registro). Enlaza la conversación y el último turno del
asistente que el cliente vio, para llegar a sus trazas. app_rw inserta; app_ro (consola) solo lee.

Revision ID: 0008
Revises: 0007
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0008"
down_revision: Union[str, Sequence[str], None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE app.feedback (
        feedback_id      varchar(40) PRIMARY KEY,
        conversation_id  varchar(40) NOT NULL UNIQUE REFERENCES app.conversations (conversation_id),
        customer_id      varchar(20) NOT NULL,
        session_id       varchar(40),
        last_turn_id     varchar(40),
        rating           varchar(4)  NOT NULL CHECK (rating IN ('up', 'down')),
        category         varchar(30) CHECK (category IN ('no_me_entendio', 'respuesta_incorrecta', 'lento', 'otro')),
        comment          varchar(500),
        created_at       timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX ix_feedback_rating_created_at ON app.feedback (rating, created_at)")
    # registro de solo inserción para la app: los privilegios por defecto de 0002 darían también UPDATE y DELETE
    op.execute("REVOKE ALL ON app.feedback FROM app_rw")
    op.execute("GRANT SELECT, INSERT ON app.feedback TO app_rw")
    op.execute("GRANT SELECT ON app.feedback TO app_ro")


def downgrade() -> None:
    op.execute("DROP TABLE app.feedback")
