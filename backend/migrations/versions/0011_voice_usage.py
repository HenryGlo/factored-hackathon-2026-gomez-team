"""app.voice_usage: consumo de voz (segundos de STT y caracteres de TTS) para el presupuesto y el costo por día (prompt 08, A3).

No guarda audio ni texto: solo cantidades. El texto transcrito, si el cliente lo envía, queda como cualquier mensaje del chat.

Revision ID: 0011
Revises: 0010
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0011"
down_revision: Union[str, Sequence[str], None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE app.voice_usage (
        usage_id         bigserial PRIMARY KEY,
        session_id       varchar(40) NOT NULL,
        customer_id      varchar(20) NOT NULL,
        conversation_id  varchar(40),
        kind             varchar(4) NOT NULL CHECK (kind IN ('stt', 'tts')),
        seconds          numeric(8, 2) NOT NULL DEFAULT 0,
        characters       integer NOT NULL DEFAULT 0,
        cost_usd         numeric(12, 6) NOT NULL DEFAULT 0,
        created_at       timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX ix_voice_usage_created_at ON app.voice_usage (created_at)")
    op.execute("REVOKE ALL ON app.voice_usage FROM app_rw")
    op.execute("GRANT SELECT, INSERT ON app.voice_usage TO app_rw")
    op.execute("GRANT USAGE, SELECT ON SEQUENCE app.voice_usage_usage_id_seq TO app_rw")
    op.execute("GRANT SELECT ON app.voice_usage TO app_ro")


def downgrade() -> None:
    op.execute("DROP TABLE app.voice_usage")
