"""Minimización de ref.customers, índice por monto eliminado, reclamos con confirmación e
idempotencia, linaje ampliado y roles app_rw / app_ro.

Generada con autogenerate y revisada a mano:
- display_name y confirmed_at se agregan nulos, se completan y luego pasan a NOT NULL, para
  que la migración funcione también sobre una base con datos.
- Los CHECK (status 'warning', confirmed_at <= created_at) no los detecta autogenerate.
- Los GRANT tampoco: se agregan aquí. Los roles de grupo se crean si no existen; los usuarios
  de login los crea infra/postgres/init/01-roles.sh con contraseñas de .env.

Revision ID: 0002
Revises: 0001
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

GRANTS = """
GRANT USAGE ON SCHEMA ref, app, ops TO app_rw, app_ro;
-- ref: solo lectura para ambos (la escribe únicamente el ETL, con el dueño)
GRANT SELECT ON ALL TABLES IN SCHEMA ref TO app_rw, app_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA ref GRANT SELECT ON TABLES TO app_rw, app_ro;
-- app: lectura/escritura para el backend, lectura para la consola
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app TO app_rw;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA app TO app_rw;
GRANT SELECT ON ALL TABLES IN SCHEMA app TO app_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA app GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_rw;
ALTER DEFAULT PRIVILEGES IN SCHEMA app GRANT USAGE, SELECT ON SEQUENCES TO app_rw;
ALTER DEFAULT PRIVILEGES IN SCHEMA app GRANT SELECT ON TABLES TO app_ro;
-- ops: solo lectura (frescura de datos para el aviso al cliente y linaje en la consola)
GRANT SELECT ON ALL TABLES IN SCHEMA ops TO app_rw, app_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA ops GRANT SELECT ON TABLES TO app_rw, app_ro;
"""

REVOKES = """
ALTER DEFAULT PRIVILEGES IN SCHEMA ref REVOKE SELECT ON TABLES FROM app_rw, app_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA app REVOKE ALL ON TABLES FROM app_rw, app_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA app REVOKE ALL ON SEQUENCES FROM app_rw;
ALTER DEFAULT PRIVILEGES IN SCHEMA ops REVOKE SELECT ON TABLES FROM app_rw, app_ro;
REVOKE ALL ON ALL TABLES IN SCHEMA ref, app, ops FROM app_rw, app_ro;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA app FROM app_rw;
REVOKE USAGE ON SCHEMA ref, app, ops FROM app_rw, app_ro;
"""


def upgrade() -> None:
    # --- ref.customers: nombre visible mínimo; fuera nombre completo, ciudad y estado
    op.add_column("customers", sa.Column("display_name", sa.String(120), nullable=True,
                  comment="first_name + inicial del apellido ('Samuel Andrés D.'), para el selector de demo."), schema="ref")
    op.execute("UPDATE ref.customers SET display_name = first_name || ' ' || left(last_name, 1) || '.'")
    op.alter_column("customers", "display_name", nullable=False, schema="ref")
    for col in ("first_name", "last_name", "state", "city"):
        op.drop_column("customers", col, schema="ref")
    op.alter_column("customers", "country", existing_type=sa.String(50), existing_nullable=False,
                    comment="Análisis de disparidades por país.", schema="ref")
    op.alter_column("customers", "segment", existing_type=sa.String(50), existing_nullable=False,
                    comment="Comparación por segmento de cliente (lo pide el reto).", schema="ref")
    op.create_table_comment(
        "customers",
        "Clientes, minimizado: nombre visible, país, segmento, estado y acento. Sin documento, contacto, dirección, "
        "ciudad, fecha de nacimiento, credit_score ni ingresos (docs/data/postgres.md).", schema="ref")

    # --- ref.transactions: (customer_id, amount) no aporta con <= 150 filas por cliente (postgres-explain.md)
    op.drop_index("ix_transactions_customer_id_amount", table_name="transactions", schema="ref")

    # --- app.dispute_cases: confirmación e idempotencia
    op.add_column("dispute_cases", sa.Column("idempotency_key", sa.String(64), nullable=True,
                  comment="Idempotency-Key del turno que lo creó: un reintento no crea un segundo reclamo."), schema="app")
    op.create_unique_constraint("uq_dispute_cases_idempotency_key", "dispute_cases", ["idempotency_key"], schema="app")
    op.add_column("dispute_cases", sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True,
                  comment="Momento en que el cliente confirmó (consumo del token)."), schema="app")
    op.execute("UPDATE app.dispute_cases SET confirmed_at = created_at")
    op.alter_column("dispute_cases", "confirmed_at", nullable=False, schema="app")
    op.create_check_constraint(op.f("ck_dispute_cases_confirmed_before_created"), "dispute_cases",
                               "confirmed_at <= created_at", schema="app")

    # --- ops.etl_runs: frescura, regla de clientes, chequeo de app, estado 'warning'
    op.add_column("etl_runs", sa.Column("max_transaction_date", sa.DateTime(), nullable=True,
                  comment="Máximo transaction_date cargado: base del aviso de frescura al cliente."), schema="ops")
    op.add_column("etl_runs", sa.Column("customer_rule", sa.Text(), nullable=True,
                  comment="Regla de selección de clientes (versión incluida)."), schema="ops")
    op.add_column("etl_runs", sa.Column("customer_seed", sa.Integer(), nullable=True), schema="ops")
    op.add_column("etl_runs", sa.Column("customer_list_sha256", sa.String(64), nullable=True,
                  comment="sha256 de los customer_id cargados, ordenados y unidos por '\\n': prueba que dos "
                          "despliegues usan los mismos clientes."), schema="ops")
    op.add_column("etl_runs", sa.Column("app_orphans", postgresql.JSONB(), nullable=True,
                  comment="Filas de app que apuntan a IDs inexistentes en ref (chequeo al final de cada corrida)."), schema="ops")
    op.alter_column("etl_runs", "data_as_of", existing_type=sa.Date(), existing_nullable=True,
                    comment="Máximo process_date cargado en ref.transactions (particiones).", schema="ops")
    op.drop_constraint("ck_etl_runs_status", "etl_runs", schema="ops")
    op.create_check_constraint(op.f("ck_etl_runs_status"), "etl_runs",
                               "status IN ('running', 'success', 'warning', 'failed', 'noop')", schema="ops")

    # --- roles: el backend usa app_rw y la consola app_ro; ninguno es superusuario ni dueño
    for role in ("app_rw", "app_ro"):
        op.execute(f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') "
                   f"THEN CREATE ROLE {role} NOLOGIN; END IF; END $$")
    op.execute(GRANTS)


def downgrade() -> None:
    op.execute(REVOKES)  # los roles se conservan: son del clúster y pueden usarlos otras bases
    op.drop_constraint("ck_etl_runs_status", "etl_runs", schema="ops")
    op.create_check_constraint(op.f("ck_etl_runs_status"), "etl_runs",
                               "status IN ('running', 'success', 'failed', 'noop')", schema="ops")
    op.alter_column("etl_runs", "data_as_of", existing_type=sa.Date(), existing_nullable=True,
                    comment="Máximo process_date cargado en ref.transactions.", schema="ops")
    for col in ("app_orphans", "customer_list_sha256", "customer_seed", "customer_rule", "max_transaction_date"):
        op.drop_column("etl_runs", col, schema="ops")
    op.drop_constraint("ck_dispute_cases_confirmed_before_created", "dispute_cases", schema="app")
    op.drop_column("dispute_cases", "confirmed_at", schema="app")
    op.drop_constraint("uq_dispute_cases_idempotency_key", "dispute_cases", schema="app")
    op.drop_column("dispute_cases", "idempotency_key", schema="app")
    op.create_index("ix_transactions_customer_id_amount", "transactions", ["customer_id", "amount"], schema="ref")
    # el nombre completo no se puede reconstruir desde display_name: ref se recarga con el ETL
    for col, typ in (("city", sa.String(100)), ("state", sa.String(100)), ("last_name", sa.String(100)),
                     ("first_name", sa.String(100))):
        op.add_column("customers", sa.Column(col, typ, nullable=True), schema="ref")
    op.drop_column("customers", "display_name", schema="ref")
    op.alter_column("customers", "country", existing_type=sa.String(50), existing_nullable=False, comment=None, schema="ref")
    op.alter_column("customers", "segment", existing_type=sa.String(50), existing_nullable=False, comment=None, schema="ref")
    op.create_table_comment(
        "customers",
        "Clientes. Solo las columnas que usa la app: sin documento, contacto, dirección, credit_score ni ingresos "
        "(docs/data/inventory.md).", schema="ref")
