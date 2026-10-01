"""Modelos SQLAlchemy de PostgreSQL. Fuente única del esquema para Alembic y para el ETL.

Tres esquemas con ciclos de vida distintos:

- ``ref``: datos del banco. El ETL los recarga desde DuckDB (TRUNCATE + COPY o reemplazo de
  particiones). Nadie más escribe aquí.
- ``ops``: linaje del ETL (``etl_runs``, ``etl_files``). Nunca se trunca: sobrevive a las recargas.
- ``app``: estado de la aplicación. Una recarga de ``ref`` nunca lo toca. Por eso ``app`` no
  tiene FK hacia ``ref``: guarda ``customer_id``, ``transaction_id`` y ``product_id`` como
  referencias lógicas, y los tools validan la pertenencia contra ``ref`` al leer.

Tipos: montos en NUMERIC(15,2), nunca float. Los timestamps de ``ref`` son TIMESTAMP sin zona,
tal como vienen en el dataset (no traen zona; ver docs/data/postgres.md). Los de ``app`` y ``ops``
los genera el sistema y van en TIMESTAMPTZ (UTC).
"""
from __future__ import annotations

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, ForeignKeyConstraint, Index,
    Integer, MetaData, Numeric, PrimaryKeyConstraint, SmallInteger, String, Table, Text, UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import JSONB

NAMING = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
metadata = MetaData(naming_convention=NAMING)

MONEY = Numeric(15, 2)
NOW = text("now()")


def _lineage() -> list[Column]:
    """Columnas de linaje de cada fila de ref: archivo de origen y corrida del ETL que la cargó."""
    return [Column("source_file", Text, nullable=False), Column("etl_run_id", BigInteger, nullable=False)]


# =============================================================================== ref

ref_customers = Table(
    "customers", metadata,
    Column("customer_id", String(20), primary_key=True),
    Column("display_name", String(120), nullable=False,
           comment="first_name + inicial del apellido ('Samuel Andrés D.'), para el selector de demo."),
    Column("country", String(50), nullable=False, comment="Análisis de disparidades por país."),
    Column("segment", String(50), nullable=False, comment="Comparación por segmento de cliente (lo pide el reto)."),
    Column("customer_status", String(20), nullable=False),
    Column("detected_accent", String(50)),
    Column("registration_date", DateTime(timezone=False)),
    Column("last_updated", DateTime(timezone=False)),
    *_lineage(),
    schema="ref",
    comment="Clientes, minimizado: nombre visible, país, segmento, estado y acento. Sin documento, contacto, "
            "dirección, ciudad, fecha de nacimiento, credit_score ni ingresos (docs/data/postgres.md).",
)

ref_products = Table(
    "products", metadata,
    Column("product_id", String(20), primary_key=True),
    Column("customer_id", String(20), ForeignKey("ref.customers.customer_id"), nullable=False),
    Column("product_type", String(50), nullable=False),
    Column("product_number", String(30), nullable=False,
           comment="No es UNIQUE: el dataset trae 6 números repetidos en productos distintos."),
    Column("currency", String(3), nullable=False),
    Column("current_balance", MONEY),
    Column("credit_limit", MONEY),
    Column("interest_rate", Numeric(7, 4)),
    Column("opening_date", Date),
    Column("expiration_date", Date),
    Column("opening_branch_id", String(20)),
    Column("product_status", String(20), nullable=False),
    Column("opening_channel", String(30)),
    Column("has_linked_app", Boolean),
    Column("days_past_due", Integer),
    Column("last_transaction_date", DateTime(timezone=False)),
    Column("last_updated", DateTime(timezone=False)),
    *_lineage(),
    Index("ix_products_customer_id", "customer_id"),
    schema="ref",
)

ref_transactions = Table(
    "transactions", metadata,
    Column("transaction_id", String(30), primary_key=True),
    Column("transaction_date", DateTime(timezone=False), nullable=False,
           comment="Tal como viene (sin zona). Evidencia: siempre 6–30 h después de process_date → UTC con día hábil en UTC-6."),
    Column("process_date", Date, nullable=False, comment="Partición diaria y día hábil local; unidad de la carga incremental."),
    Column("product_id", String(20), nullable=False),
    Column("customer_id", String(20), nullable=False),
    Column("transaction_type", String(50), nullable=False),
    Column("transaction_category", String(50)),
    Column("amount", MONEY, nullable=False),
    Column("currency", String(3), nullable=False),
    Column("amount_usd", MONEY, comment="Original del dataset; nulo en USD."),
    Column("amount_usd_filled", MONEY, comment="amount_usd o amount × tasa diaria (ASOF); igual a amount en USD."),
    Column("channel", String(30), nullable=False),
    Column("branch_id", String(20)),
    Column("merchant_name", String(150)),
    Column("merchant_category", String(50)),
    Column("transaction_country", String(50), nullable=False),
    Column("transaction_city", String(100)),
    Column("transaction_status", String(20), nullable=False),
    Column("response_code", String(10)),
    Column("is_fraud", Boolean, nullable=False),
    Column("fraud_score", Numeric(5, 2)),
    Column("latitude", Numeric(10, 7)),
    Column("longitude", Numeric(10, 7)),
    *_lineage(),
    # FK compuesta: la transacción pertenece al MISMO cliente dueño del producto. Garantiza en la base
    # el aislamiento por cliente (una tool que filtra por customer_id no puede ver un producto ajeno).
    ForeignKeyConstraint(["product_id", "customer_id"], ["ref.products.product_id", "ref.products.customer_id"],
                         name="fk_transactions_product_owner"),
    ForeignKeyConstraint(["customer_id"], ["ref.customers.customer_id"], name="fk_transactions_customer_id_customers"),
    # search_transactions: ventana por fecha del cliente, más recientes primero
    Index("ix_transactions_customer_id_transaction_date", "customer_id", text("transaction_date DESC")),
    # (customer_id, amount) se eliminó en 0002: con <= 150 filas por cliente el índice por fecha ya sirve
    # la búsqueda por monto (docs/data/postgres-explain.md)
    # FK a products y consultas por tarjeta (historial de un producto, lock_card)
    Index("ix_transactions_product_id", "product_id"),
    # carga incremental: DELETE de las particiones afectadas
    Index("ix_transactions_process_date", "process_date"),
    schema="ref",
)

# products necesita UNIQUE (product_id, customer_id) para ser destino de la FK compuesta
ref_products.append_constraint(UniqueConstraint("product_id", "customer_id", name="uq_products_product_id_customer_id"))

ref_daily_exchange_rates = Table(
    "daily_exchange_rates", metadata,
    Column("date", Date, nullable=False),
    Column("source_currency", String(3), nullable=False),
    Column("target_currency", String(3), nullable=False),
    Column("exchange_rate", Numeric(20, 10), nullable=False),
    Column("buy_rate", Numeric(20, 10)),
    Column("sell_rate", Numeric(20, 10)),
    Column("source", String(50)),
    *_lineage(),
    PrimaryKeyConstraint("date", "source_currency", "target_currency", name="pk_daily_exchange_rates"),
    schema="ref",
)

ref_rejected_rows = Table(
    "rejected_rows", metadata,
    Column("rejected_id", BigInteger, primary_key=True, autoincrement=True),
    Column("etl_run_id", BigInteger, nullable=False),
    Column("table_name", String(40), nullable=False),
    Column("pk_value", Text),
    Column("partition_date", Date),
    Column("reason", String(60), nullable=False),
    Column("detail", Text),
    Column("row_data", JSONB, nullable=False),
    Column("rejected_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    Index("ix_rejected_rows_table_name_reason", "table_name", "reason"),
    schema="ref",
    comment="Cuarentena: filas que no cumplen integridad (FK, dueño del producto, partición). Nunca se borran en silencio.",
)

ref_demo_customers = Table(
    "demo_customers", metadata,
    Column("customer_id", String(20), ForeignKey("ref.customers.customer_id"), primary_key=True),
    Column("scenario", String(40), nullable=False),
    Column("scenario_rank", SmallInteger, nullable=False),
    Column("reference_date", Date, nullable=False),
    schema="ref",
    comment="Clientes de demo elegidos de forma determinista (semilla fija) por escenario; alimenta /api/demo/customers.",
)

# =============================================================================== ops

ops_etl_runs = Table(
    "etl_runs", metadata,
    Column("run_id", BigInteger, primary_key=True, autoincrement=True),
    Column("mode", String(20), nullable=False),
    Column("status", String(20), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    Column("finished_at", DateTime(timezone=True)),
    Column("git_commit", String(40)),
    Column("git_dirty", Boolean),
    Column("source_dir", Text),
    Column("duckdb_path", Text),
    Column("duckdb_sha256", String(64)),
    Column("data_as_of", Date, comment="Máximo process_date cargado en ref.transactions (particiones)."),
    Column("max_transaction_date", DateTime(timezone=False),
           comment="Máximo transaction_date cargado: base del aviso de frescura al cliente."),
    Column("customer_scope", String(20), nullable=False, server_default="all"),
    Column("customer_rule", Text, comment="Regla de selección de clientes (versión incluida)."),
    Column("customer_seed", Integer),
    Column("customer_list_sha256", String(64),
           comment="sha256 de los customer_id cargados, ordenados y unidos por '\\n': prueba que dos despliegues usan los mismos clientes."),
    Column("app_orphans", JSONB, comment="Filas de app que apuntan a IDs inexistentes en ref (chequeo al final de cada corrida)."),
    Column("params", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("counts", JSONB, nullable=False, server_default=text("'{}'::jsonb"),
           comment="Filas por tabla en cada capa: csv, raw, clean (DuckDB), ref (PostgreSQL), rejected."),
    Column("partitions_replaced", JSONB),
    Column("error", Text),
    CheckConstraint("mode IN ('full', 'incremental')", name="mode"),
    CheckConstraint("status IN ('running', 'success', 'warning', 'failed', 'noop')", name="status"),
    schema="ops",
)

ops_etl_files = Table(
    "etl_files", metadata,
    Column("file_id", BigInteger, primary_key=True, autoincrement=True),
    Column("run_id", BigInteger, ForeignKey("ops.etl_runs.run_id"), nullable=False),
    Column("table_name", String(40), nullable=False),
    Column("source_file", Text, nullable=False),
    Column("partition_date", Date),
    Column("sha256", String(64), nullable=False),
    Column("size_bytes", BigInteger, nullable=False),
    Column("rows", BigInteger, nullable=False),
    Column("rejected_rows", BigInteger, nullable=False, server_default="0",
           comment="Líneas mal formadas del CSV (lector de DuckDB)."),
    Column("action", String(20), nullable=False),
    Column("error", Text),
    CheckConstraint("action IN ('loaded', 'new', 'changed')", name="action"),
    Index("ix_etl_files_table_name_source_file", "table_name", "source_file"),
    Index("ix_etl_files_run_id", "run_id"),
    schema="ops",
)

# =============================================================================== app

APP_TS = DateTime(timezone=True)


def _created() -> Column:
    return Column("created_at", APP_TS, nullable=False, server_default=NOW)


ROLES = ("customer", "analyst")  # analyst = persona de la consola del banco (no el agente de IA)

app_users = Table(
    "users", metadata,
    Column("user_id", String(40), primary_key=True),
    Column("username", String(60), nullable=False, comment="Único sin distinguir mayúsculas (índice sobre lower(username))."),
    Column("password_hash", Text, nullable=False, comment="argon2id; la contraseña nunca se guarda."),
    Column("role", String(20), nullable=False),
    Column("customer_id", String(20), comment="Referencia lógica a ref.customers (sin FK). Obligatorio solo para role=customer."),
    Column("display_name", String(120), comment="Nombre visible de analistas; el de clientes sale de ref.customers."),
    Column("is_active", Boolean, nullable=False, server_default=text("true")),
    _created(),
    Column("updated_at", APP_TS, nullable=False, server_default=NOW),
    Column("last_login_at", APP_TS),
    CheckConstraint("role IN ('customer', 'analyst', 'admin')", name="role"),
    CheckConstraint("(role = 'customer') = (customer_id IS NOT NULL)", name="customer_only_for_customers"),
    Index("uq_users_username_lower", text("lower(username)"), unique=True),
    schema="app",
)

app_sessions = Table(
    "sessions", metadata,
    Column("session_id", String(40), primary_key=True),
    Column("token_hash", String(64), nullable=False, unique=True, comment="SHA-256 del token de la cookie; el token no se guarda."),
    Column("user_id", String(40), ForeignKey("app.users.user_id"),
           comment="Usuario autenticado. Solo puede ser nulo en sesiones heredadas ya revocadas (antes de 0003)."),
    Column("role", String(20), nullable=False),
    Column("customer_id", String(20), comment="Copia del usuario al iniciar sesión: el backend lo toma SIEMPRE de aquí. Nulo para analyst."),
    Column("language", String(2)),
    Column("csrf_token_hash", String(64), comment="SHA-256 del token CSRF (doble envío: cookie + cabecera)."),
    Column("ip", String(64)),
    Column("user_agent", Text),
    _created(),
    Column("last_seen_at", APP_TS, nullable=False, server_default=NOW),
    Column("expires_at", APP_TS, nullable=False, comment="Vencimiento por inactividad: last_seen_at + SESSION_IDLE_MINUTES."),
    Column("revoked_at", APP_TS),
    CheckConstraint("role IN ('customer', 'analyst', 'admin')", name="role"),
    CheckConstraint("role IN ('analyst', 'admin') OR customer_id IS NOT NULL", name="customer_required"),
    CheckConstraint("user_id IS NOT NULL OR revoked_at IS NOT NULL", name="user_required"),
    Index("ix_sessions_user_id", "user_id"),
    schema="app",
)

app_login_events = Table(
    "login_events", metadata,
    Column("event_id", BigInteger, primary_key=True, autoincrement=True),
    Column("username", String(60), nullable=False, comment="Tal como se intentó (normalizado a minúsculas)."),
    Column("user_id", String(40), ForeignKey("app.users.user_id")),
    Column("ip", String(64), nullable=False),
    Column("user_agent", Text),
    Column("success", Boolean, nullable=False),
    Column("reason", String(30), nullable=False),
    _created(),
    CheckConstraint("reason IN ('ok', 'bad_credentials', 'inactive', 'locked_user', 'locked_ip', 'logout')", name="reason"),
    # límite de intentos: fallos recientes por usuario y por IP
    Index("ix_login_events_username_created_at", "username", text("created_at DESC")),
    Index("ix_login_events_ip_created_at", "ip", text("created_at DESC")),
    schema="app",
)

app_conversations = Table(
    "conversations", metadata,
    Column("conversation_id", String(40), primary_key=True),
    Column("session_id", String(40), ForeignKey("app.sessions.session_id"), nullable=False),
    Column("customer_id", String(20), nullable=False),
    Column("state", String(40), nullable=False),
    Column("language", String(2)),
    Column("clarification_round", SmallInteger, nullable=False, server_default="0"),
    Column("session_date", Date, nullable=False, server_default=text("CURRENT_DATE"),
           comment="'Hoy' de la conversación: resuelve fechas relativas y la regla R1 (REFERENCE_DATE o simulada en el harness)."),
    Column("context", JSONB, nullable=False, server_default=text("'{}'::jsonb"),
           comment="Estado del controlador: intención, pistas, candidatas mostradas, movimiento elegido, acción pendiente."),
    _created(),
    Column("updated_at", APP_TS, nullable=False, server_default=NOW),
    Column("closed_at", APP_TS),
    Column("previous_conversation_id", String(40), ForeignKey("app.conversations.conversation_id"),
           comment="Conversación anterior del mismo cliente; se hereda el cargo en foco."),
    Column("closed_reason", String(20), comment="cliente (se despidió) | inactividad. Los resultados no cierran la conversación."),
    CheckConstraint("clarification_round BETWEEN 0 AND 3", name="clarification_round"),
    CheckConstraint("closed_reason IS NULL OR closed_reason IN ('cliente', 'inactividad')", name="closed_reason"),
    Index("ix_conversations_customer_id_created_at", "customer_id", "created_at"),
    schema="app",
)

app_turns = Table(
    "turns", metadata,
    Column("turn_id", String(40), primary_key=True),
    Column("conversation_id", String(40), ForeignKey("app.conversations.conversation_id"), nullable=False),
    Column("seq", Integer, nullable=False),
    Column("role", String(20), nullable=False),
    Column("message", Text),
    Column("action", JSONB),
    Column("blocks", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("state_before", String(40)),
    Column("state_after", String(40)),
    _created(),
    UniqueConstraint("conversation_id", "seq"),
    CheckConstraint("role IN ('customer', 'assistant', 'system')", name="role"),
    schema="app",
)

app_confirmation_tokens = Table(
    "confirmation_tokens", metadata,
    Column("token_id", String(40), primary_key=True),
    Column("token_hash", String(64), nullable=False, unique=True),
    Column("session_id", String(40), ForeignKey("app.sessions.session_id"), nullable=False),
    Column("conversation_id", String(40), ForeignKey("app.conversations.conversation_id"), nullable=False),
    Column("action", String(40), nullable=False),
    Column("params", JSONB, nullable=False),
    Column("params_hash", String(64), nullable=False),
    _created(),
    Column("expires_at", APP_TS, nullable=False),
    Column("consumed_at", APP_TS, comment="Un solo uso: se marca al consumir; si ya tiene valor, invalid_confirmation."),
    Column("invalidated_at", APP_TS, comment="Anulado sin usarse: el cliente cambió de movimiento o se emitió otro token."),
    CheckConstraint("action IN ('create_dispute_case', 'lock_card', 'create_handoff')", name="action"),
    schema="app",
)

app_idempotency_keys = Table(
    "idempotency_keys", metadata,
    Column("session_id", String(40), ForeignKey("app.sessions.session_id"), nullable=False),
    Column("idempotency_key", String(64), nullable=False),
    Column("request_hash", String(64), nullable=False),
    Column("status_code", SmallInteger),
    Column("response", JSONB),
    _created(),
    Column("expires_at", APP_TS, nullable=False),
    PrimaryKeyConstraint("session_id", "idempotency_key", name="pk_idempotency_keys"),
    Index("ix_idempotency_keys_expires_at", "expires_at"),
    schema="app",
)

DISPUTE_OPEN = ("registrado", "en_revision")
app_dispute_cases = Table(
    "dispute_cases", metadata,
    Column("case_id", String(40), primary_key=True),
    Column("customer_id", String(20), nullable=False),
    Column("transaction_id", String(30), nullable=False),
    Column("conversation_id", String(40), ForeignKey("app.conversations.conversation_id")),
    Column("turn_id", String(40), ForeignKey("app.turns.turn_id")),
    Column("confirmation_token_id", String(40), ForeignKey("app.confirmation_tokens.token_id"),
           comment="Una confirmación puede cubrir varios cargos: único junto con transaction_id."),
    Column("idempotency_key", String(64),
           comment="Idempotency-Key del turno que lo creó; único junto con transaction_id: un reintento no duplica."),
    Column("status", String(20), nullable=False, server_default="registrado"),
    Column("reason_code", String(40), nullable=False),
    Column("customer_statement", Text),
    Column("policy_rules_applied", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("confirmed_at", APP_TS, nullable=False, comment="Momento en que el cliente confirmó (consumo del token)."),
    _created(),
    Column("updated_at", APP_TS, nullable=False, server_default=NOW),
    Column("closed_at", APP_TS),
    CheckConstraint("status IN ('registrado', 'en_revision', 'resuelto', 'rechazado', 'anulado')", name="status"),
    CheckConstraint("confirmed_at <= created_at", name="confirmed_before_created"),
    CheckConstraint("reason_code IN ('unrecognized', 'amount_mismatch', 'duplicate')", name="reason_code"),
    UniqueConstraint("confirmation_token_id", "transaction_id"),
    UniqueConstraint("idempotency_key", "transaction_id"),
    # R3: a lo sumo un reclamo ABIERTO por transacción del cliente (los cerrados no bloquean uno nuevo)
    Index("uq_dispute_cases_open_customer_transaction", "customer_id", "transaction_id", unique=True,
          postgresql_where=text("status IN ('registrado', 'en_revision')")),
    Index("ix_dispute_cases_status_created_at", "status", "created_at"),
    schema="app",
)

app_card_status_overrides = Table(
    "card_status_overrides", metadata,
    Column("override_id", BigInteger, primary_key=True, autoincrement=True),
    Column("customer_id", String(20), nullable=False),
    Column("product_id", String(20), nullable=False),
    Column("status", String(20), nullable=False),
    Column("reason", Text),
    Column("conversation_id", String(40), ForeignKey("app.conversations.conversation_id")),
    Column("confirmation_token_id", String(40), ForeignKey("app.confirmation_tokens.token_id"), unique=True),
    _created(),
    CheckConstraint("status IN ('Blocked', 'Active')", name="status"),
    Index("ix_card_status_overrides_product_id_created_at", "product_id", text("created_at DESC")),
    schema="app",
    comment="Bloqueos de tarjeta hechos por la app. Estado efectivo = override más reciente o ref.products.product_status.",
)

HANDOFF_REASONS = ("fuera_de_plazo", "riesgo_alto", "riesgo_desconocido", "aclaracion_agotada", "pide_humano", "fallo_tool",
                   "accion_no_verificada", "acceso_no_autorizado", "reposicion_tarjeta", "cargo_pendiente_no_reconocido")
HANDOFF_QUEUES = ("fraude", "disputas", "tarjetas", "general")
app_handoffs = Table(
    "handoffs", metadata,
    Column("handoff_id", String(40), primary_key=True),
    Column("conversation_id", String(40), ForeignKey("app.conversations.conversation_id"), nullable=False),
    Column("customer_id", String(20), nullable=False),
    Column("language", String(2), nullable=False),
    Column("reason_code", String(40), nullable=False),
    Column("priority", String(10), nullable=False),
    Column("queue", String(20), nullable=False, server_default="general"),
    Column("status", String(20), nullable=False, server_default="pendiente"),
    Column("summary", Text),
    Column("payload", JSONB, nullable=False, comment="Objeto completo de docs/handoff-schema.md."),
    _created(),
    Column("updated_at", APP_TS, nullable=False, server_default=NOW),
    Column("ticket_status", String(20), nullable=False, server_default="nuevo", comment="Estado de trabajo del ticket (prompt 08, A4)."),
    Column("assigned_to", String(40), comment="user_id del agente asignado."),
    Column("first_response_at", APP_TS),
    Column("resolved_at", APP_TS),
    CheckConstraint("reason_code IN (" + ", ".join(f"'{r}'" for r in HANDOFF_REASONS) + ")", name="reason_code"),
    CheckConstraint("priority IN ('urgente', 'alta', 'media')", name="priority"),
    CheckConstraint("queue IN (" + ", ".join(f"'{q}'" for q in HANDOFF_QUEUES) + ")", name="queue"),
    CheckConstraint("status IN ('pendiente', 'tomado', 'cerrado')", name="status"),
    Index("ix_handoffs_status_created_at", "status", "created_at"),
    schema="app",
)

app_traces = Table(
    "traces", metadata,
    Column("trace_id", BigInteger, primary_key=True, autoincrement=True),
    Column("turn_id", String(40), ForeignKey("app.turns.turn_id"), nullable=False),
    Column("conversation_id", String(40), ForeignKey("app.conversations.conversation_id"), nullable=False),
    Column("step_seq", Integer, nullable=False),
    Column("node", String(60), nullable=False),
    Column("kind", String(20), nullable=False, comment="llm | ml | code (tools, política y controlador son código)."),
    Column("implementation", String(60), comment="Implementación y versión del componente (p. ej. rule@v3, keyword@v1)."),
    Column("tool", String(60)),
    Column("model", String(80), comment="Alias pedido (haiku | sonnet)."),
    Column("model_id", String(80), comment="ID real que devolvió el proveedor."),
    Column("prompt_version", String(60)),
    Column("latency_ms", Integer),
    Column("input_tokens", Integer),
    Column("output_tokens", Integer),
    Column("cost_usd", Numeric(12, 6)),
    Column("payload", JSONB, nullable=False, server_default=text("'{}'::jsonb"),
           comment="Entrada y salida del paso. Sin cadena de pensamiento."),
    Column("rules", JSONB, comment="Reglas de política evaluadas en el paso: [{id, resultado, motivo, evidencia}]."),
    Column("error", Text),
    _created(),
    UniqueConstraint("turn_id", "step_seq"),
    CheckConstraint("kind IN ('llm', 'ml', 'code')", name="kind"),
    schema="app",
)

app_ticket_events = Table(
    "ticket_events", metadata,
    Column("event_id", BigInteger, primary_key=True, autoincrement=True),
    Column("handoff_id", String(40), ForeignKey("app.handoffs.handoff_id"), nullable=False),
    Column("actor_user_id", String(40), nullable=False),
    Column("actor_username", String(60), nullable=False),
    Column("kind", String(20), nullable=False, comment="asignacion | estado | nota"),
    Column("from_value", String(60)),
    Column("to_value", String(60)),
    Column("note", String(2000), comment="Nota interna del agente: nunca se muestra al cliente."),
    _created(),
    CheckConstraint("kind IN ('asignacion', 'estado', 'nota')", name="kind"),
    schema="app",
)

app_feedback = Table(
    "feedback", metadata,
    Column("feedback_id", String(40), primary_key=True),
    Column("conversation_id", String(40), ForeignKey("app.conversations.conversation_id"), nullable=False, unique=True),
    Column("customer_id", String(20), nullable=False),
    Column("session_id", String(40)),
    Column("last_turn_id", String(40), comment="Último turno del asistente que vio el cliente: lleva a sus trazas."),
    Column("rating", String(4), nullable=False),
    Column("category", String(30)),
    Column("comment", String(500), comment="Texto libre del cliente: dato, nunca instrucción. No va a los logs."),
    _created(),
    CheckConstraint("rating IN ('up', 'down')", name="rating"),
    CheckConstraint("category IN ('no_me_entendio', 'respuesta_incorrecta', 'lento', 'otro')", name="category"),
    Index("ix_feedback_rating_created_at", "rating", "created_at"),
    schema="app",
)

SCHEMAS = ("ref", "ops", "app")
REF_LOAD_ORDER = ("customers", "products", "transactions", "daily_exchange_rates")
