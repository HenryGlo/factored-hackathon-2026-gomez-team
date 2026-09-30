"""Usuarios con contraseña, eventos de login y rol `analyst` (antes `agent`).

- app.users (argon2) y app.login_events (auditoría y límite de intentos).
- app.sessions: user_id, token CSRF, IP, user agent y última actividad (vencimiento por
  inactividad). Las sesiones anteriores no tienen usuario: se revocan (ya no son válidas con
  el login por contraseña) y un CHECK exige usuario en toda sesión no revocada.
- Rol de la consola: `agent` → `analyst`, para no confundir a la persona con el agente de IA.
- app_ro (consola) no puede leer password_hash: permisos por columna en app.users.

Generada con autogenerate y revisada a mano (CHECK, datos existentes y permisos).

Revision ID: 0003
Revises: 0002
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

USERS_PUBLIC_COLS = "user_id, username, role, customer_id, display_name, is_active, created_at, updated_at, last_login_at"


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("user_id", sa.String(40), primary_key=True),
        sa.Column("username", sa.String(60), nullable=False,
                  comment="Único sin distinguir mayúsculas (índice sobre lower(username))."),
        sa.Column("password_hash", sa.Text(), nullable=False, comment="argon2id; la contraseña nunca se guarda."),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("customer_id", sa.String(20),
                  comment="Referencia lógica a ref.customers (sin FK). Obligatorio solo para role=customer."),
        sa.Column("display_name", sa.String(120), comment="Nombre visible de analistas; el de clientes sale de ref.customers."),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("role IN ('customer', 'analyst')", name=op.f("ck_users_role")),
        sa.CheckConstraint("(role = 'customer') = (customer_id IS NOT NULL)", name=op.f("ck_users_customer_only_for_customers")),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_users")),
        schema="app",
    )
    op.create_index("uq_users_username_lower", "users", [sa.text("lower(username)")], unique=True, schema="app")

    op.create_table(
        "login_events",
        sa.Column("event_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(60), nullable=False, comment="Tal como se intentó (normalizado a minúsculas)."),
        sa.Column("user_id", sa.String(40), sa.ForeignKey("app.users.user_id", name=op.f("fk_login_events_user_id_users"))),
        sa.Column("ip", sa.String(64), nullable=False),
        sa.Column("user_agent", sa.Text()),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("reason IN ('ok', 'bad_credentials', 'inactive', 'locked_user', 'locked_ip', 'logout')",
                           name=op.f("ck_login_events_reason")),
        sa.PrimaryKeyConstraint("event_id", name=op.f("pk_login_events")),
        schema="app",
    )
    op.create_index("ix_login_events_username_created_at", "login_events", ["username", sa.text("created_at DESC")], schema="app")
    op.create_index("ix_login_events_ip_created_at", "login_events", ["ip", sa.text("created_at DESC")], schema="app")

    # --- app.sessions
    op.add_column("sessions", sa.Column("user_id", sa.String(40),
                  comment="Usuario autenticado. Solo puede ser nulo en sesiones heredadas ya revocadas (antes de 0003)."),
                  schema="app")
    op.add_column("sessions", sa.Column("csrf_token_hash", sa.String(64),
                  comment="SHA-256 del token CSRF (doble envío: cookie + cabecera)."), schema="app")
    op.add_column("sessions", sa.Column("ip", sa.String(64)), schema="app")
    op.add_column("sessions", sa.Column("user_agent", sa.Text()), schema="app")
    op.add_column("sessions", sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                                        nullable=False), schema="app")
    op.create_foreign_key(op.f("fk_sessions_user_id_users"), "sessions", "users", ["user_id"], ["user_id"],
                          source_schema="app", referent_schema="app")
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"], schema="app")
    op.alter_column("sessions", "token_hash", existing_type=sa.String(64), existing_nullable=False,
                    comment="SHA-256 del token de la cookie; el token no se guarda.", schema="app")
    op.alter_column("sessions", "customer_id", existing_type=sa.String(20), existing_nullable=True,
                    comment="Copia del usuario al iniciar sesión: el backend lo toma SIEMPRE de aquí. Nulo para analyst.",
                    schema="app")
    op.alter_column("sessions", "expires_at", existing_type=sa.DateTime(timezone=True), existing_nullable=False,
                    comment="Vencimiento por inactividad: last_seen_at + SESSION_IDLE_MINUTES.", schema="app")
    # sesiones anteriores (sin usuario ni contraseña): ya no son válidas
    op.execute("UPDATE app.sessions SET revoked_at = now() WHERE revoked_at IS NULL")
    # rol de la consola: agent → analyst
    op.drop_constraint("ck_sessions_customer_required", "sessions", schema="app")
    op.drop_constraint("ck_sessions_role", "sessions", schema="app")
    op.execute("UPDATE app.sessions SET role = 'analyst' WHERE role = 'agent'")
    op.create_check_constraint(op.f("ck_sessions_role"), "sessions", "role IN ('customer', 'analyst')", schema="app")
    op.create_check_constraint(op.f("ck_sessions_customer_required"), "sessions",
                               "role = 'analyst' OR customer_id IS NOT NULL", schema="app")
    op.create_check_constraint(op.f("ck_sessions_user_required"), "sessions",
                               "user_id IS NOT NULL OR revoked_at IS NOT NULL", schema="app")

    # --- permisos: los defaults de 0002 dan SELECT a app_ro en tablas nuevas; se retira el hash
    op.execute("REVOKE SELECT ON app.users FROM app_ro")
    op.execute(f"GRANT SELECT ({USERS_PUBLIC_COLS}) ON app.users TO app_ro")


def downgrade() -> None:
    op.execute(f"REVOKE SELECT ({USERS_PUBLIC_COLS}) ON app.users FROM app_ro")
    op.drop_constraint("ck_sessions_user_required", "sessions", schema="app")
    op.drop_constraint("ck_sessions_customer_required", "sessions", schema="app")
    op.drop_constraint("ck_sessions_role", "sessions", schema="app")
    op.execute("UPDATE app.sessions SET role = 'agent' WHERE role = 'analyst'")
    op.create_check_constraint(op.f("ck_sessions_role"), "sessions", "role IN ('customer', 'agent')", schema="app")
    op.create_check_constraint(op.f("ck_sessions_customer_required"), "sessions",
                               "role = 'agent' OR customer_id IS NOT NULL", schema="app")
    op.alter_column("sessions", "expires_at", existing_type=sa.DateTime(timezone=True), existing_nullable=False,
                    comment=None, schema="app")
    op.alter_column("sessions", "customer_id", existing_type=sa.String(20), existing_nullable=True,
                    comment="Referencia lógica a ref.customers (sin FK). Nulo para role=agent.", schema="app")
    op.alter_column("sessions", "token_hash", existing_type=sa.String(64), existing_nullable=False,
                    comment="SHA-256 del session_token; el token no se guarda.", schema="app")
    op.drop_index("ix_sessions_user_id", table_name="sessions", schema="app")
    op.drop_constraint("fk_sessions_user_id_users", "sessions", schema="app")
    for col in ("last_seen_at", "user_agent", "ip", "csrf_token_hash", "user_id"):
        op.drop_column("sessions", col, schema="app")
    op.drop_index("ix_login_events_ip_created_at", table_name="login_events", schema="app")
    op.drop_index("ix_login_events_username_created_at", table_name="login_events", schema="app")
    op.drop_table("login_events", schema="app")
    op.drop_index("uq_users_username_lower", table_name="users", schema="app")
    op.drop_table("users", schema="app")
