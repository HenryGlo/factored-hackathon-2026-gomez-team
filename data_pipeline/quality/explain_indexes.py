"""EXPLAIN ANALYZE de las consultas de las tools, con y sin cada índice de ref.

    python -m data_pipeline.quality.explain_indexes [--database-url URL] [--out archivo.md]

Cada consulta se mide en varias variantes de índices. Cada variante crea o borra índices dentro
de una transacción y hace ROLLBACK, así que la base queda igual. Cada medición se toma después
de una corrida de calentamiento (caché caliente). Se usa el cliente con más transacciones (peor
caso) y una transacción/producto suyo. Los identificadores se reemplazan por marcadores en la
salida para no publicar datos del dataset (P-04).

La variante con ix_transactions_customer_id_amount, creado temporalmente, deja la evidencia de
por qué se eliminó en la migración 0002.
"""
from __future__ import annotations

import argparse
import os
import re

import psycopg

from data_pipeline.config import REPO
from data_pipeline.etl.load_postgres import pg_url

DATE_IDX = "ix_transactions_customer_id_transaction_date"
AMOUNT_IDX_DDL = "CREATE INDEX ix_transactions_customer_id_amount ON ref.transactions (customer_id, amount)"
NO_CUSTOMER_IDX = [f"DROP INDEX ref.{DATE_IDX}"]

# (título, consulta que justifica, SQL, [(variante, sentencias previas)])
QUERIES = [
    (DATE_IDX, "search_transactions: ventana de fechas del cliente, más recientes primero",
     """SELECT transaction_id, transaction_date, amount, currency, merchant_name, channel, transaction_type,
               transaction_status, product_id
        FROM ref.transactions
        WHERE customer_id = %(cid)s AND transaction_date >= %(to)s::timestamp - interval '90 days'
          AND transaction_date < %(to)s::timestamp
        ORDER BY transaction_date DESC LIMIT 50""",
     [("índices actuales", []), (f"sin `{DATE_IDX}`", NO_CUSTOMER_IDX)]),
    ("ix_transactions_customer_id_amount (eliminado en 0002)",
     "search_transactions con monto: candidatas a ±10 % del monto dicho",
     """SELECT transaction_id, transaction_date, amount, currency
        FROM ref.transactions
        WHERE customer_id = %(cid)s AND amount BETWEEN %(amt)s * 0.9 AND %(amt)s * 1.1""",
     [("índices actuales (sirve el de fecha)", []),
      ("con `ix_transactions_customer_id_amount` (creado temporalmente)", [AMOUNT_IDX_DDL]),
      ("sin ningún índice por customer_id", NO_CUSTOMER_IDX)]),
    ("ix_transactions_product_id", "historial de una tarjeta (contexto de lock_card) y soporte de la FK a products",
     """SELECT transaction_id, transaction_date, amount FROM ref.transactions
        WHERE product_id = %(pid)s ORDER BY transaction_date DESC LIMIT 20""",
     [("índices actuales", []), ("sin `ix_transactions_product_id`", ["DROP INDEX ref.ix_transactions_product_id"])]),
    ("ix_transactions_process_date", "carga incremental: borrar una partición (un día) antes de recargarla",
     """DELETE FROM ref.transactions WHERE process_date = %(pd)s""",
     [("índices actuales", []), ("sin `ix_transactions_process_date`", ["DROP INDEX ref.ix_transactions_process_date"])]),
    ("ix_products_customer_id", "productos/tarjetas del cliente (get_card_status, lock_card)",
     """SELECT product_id, product_type, product_status FROM ref.products WHERE customer_id = %(cid)s""",
     [("índices actuales", []), ("sin `ix_products_customer_id`", ["DROP INDEX ref.ix_products_customer_id"])]),
]


def explain(cur, sql: str, params: dict) -> str:
    """EXPLAIN ANALYZE con caché caliente. Un DELETE se ejecuta de verdad: quien llama hace ROLLBACK."""
    if sql.lstrip().upper().startswith("SELECT"):
        cur.execute(sql, params).fetchall()  # calentamiento
    else:
        cur.execute("SAVEPOINT warm")
        cur.execute(sql, params)
        cur.execute("ROLLBACK TO SAVEPOINT warm")
    rows = cur.execute("EXPLAIN (ANALYZE, BUFFERS, COSTS OFF, SUMMARY ON) " + sql, params).fetchall()
    return "\n".join(r[0] for r in rows)


def redact(text: str, params: dict) -> str:
    for k, v in params.items():
        text = text.replace(str(v), f"<{k}>")
    return re.sub(r"(CLI|PRD|TRX)-[A-Z0-9]+", r"<\1>", text)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--database-url", default=os.environ.get("ADMIN_DATABASE_URL"))
    ap.add_argument("--out", default=str(REPO / "docs" / "data" / "postgres-explain.md"))
    args = ap.parse_args()
    with psycopg.connect(pg_url(args.database_url)) as pg, pg.cursor() as cur:
        version = cur.execute("SHOW server_version").fetchone()[0]
        n_tx = cur.execute("SELECT count(*) FROM ref.transactions").fetchone()[0]
        cid, n = cur.execute("SELECT customer_id, count(*) FROM ref.transactions GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 1").fetchone()
        to, amt, pid = cur.execute("""SELECT max(transaction_date), (array_agg(amount ORDER BY transaction_date DESC))[1],
                                             mode() WITHIN GROUP (ORDER BY product_id)
                                      FROM ref.transactions WHERE customer_id = %s""", (cid,)).fetchone()
        pd_ = cur.execute("SELECT max(process_date) - 7 FROM ref.transactions").fetchone()[0]
        params = {"cid": cid, "to": to, "amt": amt, "pid": pid, "pd": pd_}
        pg.commit()
        out = ["# EXPLAIN ANALYZE de los índices de `ref`\n",
               f"Generado por `python -m data_pipeline.quality.explain_indexes`. PostgreSQL {version}, "
               f"{n_tx:,} transacciones. Cliente de prueba: el de más transacciones ({n}). "
               "Identificadores reemplazados por marcadores.\n"]
        t = lambda s: re.search(r"Execution Time: ([\d.]+) ms", s).group(1)
        uses = lambda s: ", ".join(sorted(set(re.findall(r"(?:Index Only Scan|Index Scan|Bitmap Index Scan)(?: Backward)? (?:using|on) (\w+)", s)))) or "Seq Scan"
        for title, why, sql, variants in QUERIES:
            out += [f"## `{title}`\n", f"Consulta: {why}.\n", "```sql", redact(re.sub(r"\s+", " ", sql).strip(), params), "```\n",
                    "| Variante | Tiempo de ejecución | Acceso |", "|---|---|---|"]
            plans = []
            for label, setup in variants:
                for stmt in setup:
                    cur.execute(stmt)
                plan = explain(cur, sql, params)
                pg.rollback()
                out.append(f"| {label} | {t(plan)} ms | {uses(plan)} |")
                plans.append((label, plan))
                print(f"{title} [{label}]: {t(plan)} ms · {uses(plan)}")
            out.append("")
            for label, plan in plans:
                out += [f"<details><summary>Plan: {label}</summary>\n", "```", redact(plan, params), "```", "</details>\n"]
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print(f"→ {args.out}")


if __name__ == "__main__":
    main()
