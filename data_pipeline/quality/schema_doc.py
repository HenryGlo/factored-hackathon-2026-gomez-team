"""Genera docs/data/postgres-schema.md desde los modelos SQLAlchemy (fuente única del esquema).

    python -m data_pipeline.quality.schema_doc

Un erDiagram de Mermaid por esquema (ref, app, ops) y una tabla de columnas por tabla. Las
referencias lógicas de app hacia ref (sin FK, a propósito) se dibujan con línea punteada.
"""
from __future__ import annotations

import re

from sqlalchemy.dialects import postgresql

from backend.persistence.models import metadata
from data_pipeline.config import REPO
from data_pipeline.contracts.engine import load_contracts

OUT = REPO / "docs" / "data" / "postgres-schema.md"
# app → ref: referencias lógicas que validan los tools y el chequeo de consistencia del ETL
LOGICAL = [
    ("app.dispute_cases", "ref.transactions", "transaction_id + customer_id"),
    ("app.card_status_overrides", "ref.products", "product_id + customer_id"),
    ("app.handoffs", "ref.customers", "customer_id"),
    ("app.conversations", "ref.customers", "customer_id"),
    ("app.sessions", "ref.customers", "customer_id"),
]


# Índice → consulta que lo justifica y medición (docs/data/postgres-explain.md, PostgreSQL 17.9, dataset completo)
INDEX_WHY = {
    "pk_transactions": ("get_transaction / fraud_risk: una transacción por id (más filtro por cliente)", "PK"),
    "ix_transactions_customer_id_transaction_date": (
        "search_transactions: ventana de fechas del cliente, más recientes primero; también la búsqueda por monto ±10 %",
        "0,011 ms con índice · 97 ms sin él"),
    "ix_transactions_product_id": ("historial de una tarjeta (lock_card); soporte de la FK compuesta", "0,015 ms · 92 ms"),
    "ix_transactions_process_date": ("carga incremental: DELETE de una partición (process_date)", "1,1 ms · 180 ms"),
    "ix_products_customer_id": ("tarjetas del cliente (get_card_status, lock_card)", "0,012 ms · 12 ms"),
    "uq_products_product_id_customer_id": ("destino de la FK compuesta transacción → (producto, dueño)", "restricción"),
    "ix_rejected_rows_table_name_reason": ("resumen de la cuarentena por tabla y motivo", "no medido (tabla vacía)"),
    "uq_dispute_cases_open_customer_transaction": ("get_existing_case y R3: un solo reclamo abierto por transacción", "restricción"),
    "uq_dispute_cases_idempotency_key": ("create_dispute_case idempotente por Idempotency-Key", "restricción"),
    "ix_dispute_cases_status_created_at": ("consola: GET /api/cases filtrado por estado, más recientes", "no medido (tabla vacía)"),
    "ix_card_status_overrides_product_id_created_at": ("get_card_status: override más reciente (vista card_status_effective)", "no medido (tabla vacía)"),
    "ix_conversations_customer_id_created_at": ("conversaciones de un cliente (P-26: una nueva por conversación cerrada)", "no medido (tabla vacía)"),
    "ix_handoffs_status_created_at": ("consola: cola de handoffs pendientes", "no medido (tabla vacía)"),
    "ix_idempotency_keys_expires_at": ("purga de claves vencidas (IDEMPOTENCY_TTL_HOURS)", "no medido (tabla vacía)"),
    "ix_etl_files_table_name_source_file": ("carga incremental: último hash cargado por archivo (pending_files)", "no medido"),
    "ix_etl_files_run_id": ("archivos de una corrida (auditoría del linaje)", "no medido"),
}

FRESHNESS = """## Política de frescura

Detalle y justificación: [postgres.md](postgres.md#política-de-frescura).

| Qué | Cómo se calcula | Dónde | Para qué |
|---|---|---|---|
| `data_as_of` | máx. `process_date` en `ref.transactions` | `ops.etl_runs.data_as_of` | Particiones completas cargadas; uso interno (linaje, alertas). |
| `max_transaction_date` | máx. `transaction_date` en `ref.transactions` | `ops.etl_runs.max_transaction_date` | **Aviso al cliente**: "movimientos disponibles hasta …". |
| Última carga válida | corrida más reciente con `status` en (`success`, `warning`, `noop`) | `ops.etl_runs.finished_at` | Detectar datos viejos. |
| Horario de carga | **[Supuesto]** incremental diaria a las 07:00 UTC; la partición D se considera completa después de D+1 06:00 (último `transaction_date` posible, H16) | no implementado (sin scheduler) | P-30 en [open-questions.md](../open-questions.md). |
| Umbral de datos viejos | **[Supuesto]** más de 26 h sin carga válida o `data_as_of` < hoy − 2 días | no implementado | Aviso "los datos pueden estar desactualizados" y alerta operativa. |
"""


def mtype(col) -> str:
    t = str(col.type.compile(dialect=postgresql.dialect())).replace("TIMESTAMP WITHOUT TIME ZONE", "TIMESTAMP") \
        .replace("TIMESTAMP WITH TIME ZONE", "TIMESTAMPTZ")
    return re.sub(r"[^A-Za-z0-9_]+", "_", t.replace(", ", ",")).strip("_")


def ename(table) -> str:
    return f"{table.schema}_{table.name}"


def keys(table, col) -> str:
    k = []
    if col.primary_key:
        k.append("PK")
    if col.foreign_keys or any(col.name in fk.column_keys for fk in table.foreign_key_constraints):
        k.append("FK")
    if col.unique or any(len(u.columns) == 1 and col.name in u.columns for u in table.constraints
                         if u.__class__.__name__ == "UniqueConstraint"):
        k.append("UK")
    return ",".join(k)


def er(schema: str, extra: list[str] | None = None) -> list[str]:
    tables = [t for t in metadata.sorted_tables if t.schema == schema]
    out = ["```mermaid", "erDiagram"]
    for t in tables:
        out.append(f"    {ename(t)} {{")
        for c in t.columns:
            k = keys(t, c)
            out.append(f"        {mtype(c)} {c.name}{' ' + k if k else ''}")
        out.append("    }")
    for t in tables:
        for fk in t.foreign_key_constraints:
            parent = fk.referred_table
            if parent.schema != schema:
                continue
            out.append(f'    {ename(parent)} ||--o{{ {ename(t)} : "{" + ".join(fk.column_keys)}"')
    out += extra or []
    out.append("```")
    return out


def main() -> None:
    contracts = load_contracts()
    lines = ["# Esquema de PostgreSQL",
             "",
             "Generado por `python -m data_pipeline.quality.schema_doc` a partir de "
             "[backend/persistence/models.py](../../backend/persistence/models.py). No editar a mano. "
             "Decisiones, cargas y linaje: [postgres.md](postgres.md).",
             "",
             "Claves: PK = clave primaria, FK = clave foránea, UK = única. En `app`, las líneas punteadas hacia `ref` son "
             "referencias **lógicas sin FK**: una recarga de `ref` no puede borrar ni bloquear el estado de la app. "
             "Las valida el chequeo `app_orphans` al final de cada corrida del ETL.",
             "", "## ref: datos del banco (los recarga el ETL)", ""]
    lines += er("ref")
    lines += ["", "## app: estado de la aplicación (una recarga nunca lo toca)", ""]
    ref_stub = ["    ref_customers { VARCHAR customer_id PK }", "    ref_products { VARCHAR product_id PK }",
                "    ref_transactions { VARCHAR transaction_id PK }"]
    logical = [f'    {b.replace(".", "_")} ||..o{{ {a.replace(".", "_")} : "{label} (lógica)"' for a, b, label in LOGICAL]
    lines += er("app", ref_stub + logical)
    lines += ["", "## ops: linaje del ETL (nunca se trunca)", ""]
    lines += er("ops")
    lines += ["", "## Índices y consulta que los justifica", "",
              "Medición con el cliente de más transacciones y caché caliente: [postgres-explain.md](postgres-explain.md). "
              "`(customer_id, amount)` se eliminó en la migración 0002 (el índice por fecha ya sirve la búsqueda por monto: "
              "0,054 ms frente a 0,009 ms con el índice propio).", "",
              "| Esquema | Tabla | Índice / restricción | Columnas | Consulta que lo justifica | Medición |", "|---|---|---|---|---|---|"]
    for t in metadata.sorted_tables:
        objs = [(i.name, ", ".join(str(e).split(".")[-1] for e in i.expressions)
                 + (f" WHERE {i.dialect_options['postgresql']['where']}" if i.dialect_options["postgresql"].get("where") is not None else ""))
                for i in t.indexes]
        objs += [(u.name, ", ".join(c.name for c in u.columns)) for u in t.constraints
                 if u.__class__.__name__ == "UniqueConstraint" and u.name in INDEX_WHY]
        if t.name == "transactions" and t.schema == "ref":
            objs.insert(0, ("pk_transactions", "transaction_id"))
        for name, cols in objs:
            why, med = INDEX_WHY.get(name, ("—", "—"))
            lines.append(f"| {t.schema} | {t.name} | `{name}` | {cols} | {why} | {med} |")
    lines += ["", FRESHNESS, "## Columnas", ""]
    for schema in ("ref", "app", "ops"):
        for t in [t for t in metadata.sorted_tables if t.schema == schema]:
            lines += [f"### `{t.schema}.{t.name}`", ""]
            if t.comment:
                lines += [t.comment, ""]
            ct = contracts.get(t.name) if schema == "ref" else None
            if ct:
                lines += [f"Contrato: [contracts/{t.name}.yaml](../../data_pipeline/contracts/{t.name}.yaml) (v{ct.version}).", ""]
            lines += ["| Columna | Tipo | Nulo | Claves | Comentario |", "|---|---|---|---|---|"]
            for c in t.columns:
                typ = str(c.type.compile(dialect=postgresql.dialect()))
                lines.append(f"| `{c.name}` | {typ} | {'sí' if c.nullable else 'no'} | {keys(t, c)} | {c.comment or ''} |")
            idx = [i for i in t.indexes]
            if idx:
                lines += ["", "Índices: " + "; ".join(
                    f"`{i.name}` ({', '.join(str(e) for e in i.expressions)})"
                    + (" UNIQUE" if i.unique else "")
                    + (f" WHERE {i.dialect_options['postgresql']['where']}" if i.dialect_options["postgresql"].get("where") is not None else "")
                    for i in idx)]
            lines.append("")
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"→ {OUT}")


if __name__ == "__main__":
    main()
