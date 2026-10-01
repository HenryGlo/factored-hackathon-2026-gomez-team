"""Selectores de clientes y transacciones reales para los casos de evaluación (SQL documentado).

Cada selector devuelve filas (customer_id, target[, second]) que cumplen el escenario en la ventana que
termina en la fecha de sesión `:r`, ordenadas de forma determinista por md5. Un caso toma la fila `pick`.
Así ningún ID del dataset queda versionado en los casos (P-04): se resuelven al correr, contra la base
de evaluación, y solo quedan en eval/results/raw/ (fuera de git).

Universo disputable: Purchase, Payment y Withdrawal. Ventana de búsqueda del sistema: 120 días.
"Monto único" = ninguna otra transacción disputable del cliente a ±10 % en la ventana (la aclaración no
debería hacer falta). "Riesgo bajo" = fraud_score < 35.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import text

DISPUTABLE = "t.transaction_type IN ('Purchase', 'Payment', 'Withdrawal')"
WINDOW = "t.transaction_date >= CAST(:r AS date) - 120 AND t.transaction_date < CAST(:r AS date) + 1"


def _unique_amount(alias: str = "t") -> str:
    return f"""NOT EXISTS (SELECT 1 FROM ref.transactions o WHERE o.customer_id = {alias}.customer_id
               AND o.transaction_id <> {alias}.transaction_id AND o.transaction_type IN ('Purchase', 'Payment', 'Withdrawal')
               AND o.transaction_date >= CAST(:r AS date) - 120 AND o.transaction_date < CAST(:r AS date) + 1
               AND abs(o.amount - {alias}.amount) <= 0.10 * {alias}.amount)"""


def _unique_merchant(alias: str = "t") -> str:
    return f"""NOT EXISTS (SELECT 1 FROM ref.transactions o WHERE o.customer_id = {alias}.customer_id
               AND o.transaction_id <> {alias}.transaction_id AND o.merchant_name = {alias}.merchant_name
               AND o.transaction_date >= CAST(:r AS date) - 120 AND o.transaction_date < CAST(:r AS date) + 1)"""


def _single(where: str, order_salt: str) -> str:
    return f"""SELECT t.customer_id, t.transaction_id AS target FROM ref.transactions t
               WHERE {DISPUTABLE} AND {WINDOW} AND {where}
               ORDER BY md5(t.customer_id || t.transaction_id || '{order_salt}') LIMIT 40"""


SELECTORS: dict[str, str] = {
    # compra procesada con comercio, reciente (≤ 30 días), riesgo bajo, monto y comercio únicos
    "cargo_claro": _single(f"""t.transaction_type = 'Purchase' AND t.merchant_name IS NOT NULL AND t.transaction_status = 'Approved'
        AND t.fraud_score < 35 AND t.transaction_date >= CAST(:r AS date) - 30 AND {_unique_amount()} AND {_unique_merchant()}""", "claro"),
    # igual, pero la única compra de su categoría en la ventana (el cliente dice "el súper", "la farmacia", "un taxi")
    "categoria_unica": _single(f"""t.transaction_type = 'Purchase' AND t.merchant_name IS NOT NULL AND t.transaction_status = 'Approved'
        AND t.fraud_score < 35 AND t.transaction_date >= CAST(:r AS date) - 30 AND t.merchant_category IN ('Food', 'Health', 'Transport')
        AND {_unique_amount()} AND NOT EXISTS (SELECT 1 FROM ref.transactions o WHERE o.customer_id = t.customer_id
            AND o.transaction_id <> t.transaction_id AND o.transaction_type IN ('Purchase', 'Payment', 'Withdrawal')
            AND coalesce(o.merchant_category, o.transaction_category) = t.merchant_category
            AND o.transaction_date >= CAST(:r AS date) - 120 AND o.transaction_date < CAST(:r AS date) + 1)""", "categoria"),
    # dos compras procesadas, riesgo bajo, mismo tipo de moneda, montos a ±10 %, en días distintos (≥ 2 días),
    # ambas en los últimos 45 días y sin otra transacción a ±10 %; target = la más reciente
    "montos_parecidos": """SELECT a.customer_id, a.transaction_id AS target, b.transaction_id AS second
        FROM ref.transactions a JOIN ref.transactions b ON b.customer_id = a.customer_id AND b.transaction_id <> a.transaction_id
        WHERE a.transaction_type = 'Purchase' AND b.transaction_type = 'Purchase' AND a.merchant_name IS NOT NULL AND b.merchant_name IS NOT NULL
          AND a.merchant_name <> b.merchant_name AND a.currency = b.currency
          AND a.transaction_status = 'Approved' AND b.transaction_status = 'Approved' AND a.fraud_score < 35 AND b.fraud_score < 35
          AND a.transaction_date >= CAST(:r AS date) - 45 AND a.transaction_date < CAST(:r AS date) + 1
          AND b.transaction_date >= CAST(:r AS date) - 45 AND b.transaction_date < a.transaction_date - interval '2 days'
          AND abs(a.amount - b.amount) <= 0.05 * a.amount
          AND NOT EXISTS (SELECT 1 FROM ref.transactions o WHERE o.customer_id = a.customer_id
              AND o.transaction_id NOT IN (a.transaction_id, b.transaction_id)
              AND o.transaction_type IN ('Purchase', 'Payment', 'Withdrawal')
              AND o.transaction_date >= CAST(:r AS date) - 120 AND o.transaction_date < CAST(:r AS date) + 1
              AND abs(o.amount - a.amount) <= 0.15 * a.amount)
        ORDER BY md5(a.customer_id || a.transaction_id || 'parecidos') LIMIT 40""",
    "pendiente": _single(f"""t.transaction_status = 'Pending' AND t.merchant_name IS NOT NULL AND t.transaction_date >= CAST(:r AS date) - 30
        AND {_unique_amount()}""", "pendiente"),
    "revertido": _single(f"""t.transaction_status = 'Reversed' AND t.merchant_name IS NOT NULL AND t.transaction_date >= CAST(:r AS date) - 45
        AND {_unique_amount()}""", "revertido"),
    # cargo de hace 70–110 días: fuera del plazo de 60 de R1 pero dentro de la ventana de búsqueda
    "fuera_de_plazo": _single(f"""t.transaction_type = 'Purchase' AND t.merchant_name IS NOT NULL AND t.transaction_status = 'Approved'
        AND t.fraud_score < 35 AND t.transaction_date < CAST(:r AS date) - 70 AND t.transaction_date >= CAST(:r AS date) - 110
        AND {_unique_amount()}""", "plazo"),
    # fraud_score >= 70, hecho con una tarjeta activa del cliente, dentro del plazo
    "riesgo_alto_tarjeta": f"""SELECT t.customer_id, t.transaction_id AS target FROM ref.transactions t JOIN ref.products p USING (product_id)
        WHERE {DISPUTABLE} AND {WINDOW} AND t.fraud_score >= 70 AND t.transaction_status = 'Approved'
          AND t.transaction_date >= CAST(:r AS date) - 60 AND p.product_type IN ('Tarjeta Crédito', 'Tarjeta Débito')
          AND p.product_status = 'Active' AND {_unique_amount()}
        ORDER BY md5(t.customer_id || t.transaction_id || 'alto') LIMIT 40""",
    # fraud_score entre 35 y 70 (banda media del score crudo; alta con el score calibrado), tarjeta activa, dentro del plazo
    "riesgo_medio_tarjeta": f"""SELECT t.customer_id, t.transaction_id AS target FROM ref.transactions t JOIN ref.products p USING (product_id)
        WHERE {DISPUTABLE} AND {WINDOW} AND t.fraud_score >= 35 AND t.fraud_score < 70 AND t.transaction_status = 'Approved'
          AND t.transaction_date >= CAST(:r AS date) - 60 AND p.product_type IN ('Tarjeta Crédito', 'Tarjeta Débito')
          AND p.product_status = 'Active' AND {_unique_amount()}
        ORDER BY md5(t.customer_id || t.transaction_id || 'medio') LIMIT 40""",
    # sin fraud_score y más de 500 USD: R6 escala por riesgo desconocido
    "riesgo_desconocido_alto": _single(f"""t.fraud_score IS NULL AND t.amount_usd_filled > 500 AND t.transaction_status = 'Approved'
        AND t.transaction_date >= CAST(:r AS date) - 60 AND {_unique_amount()}""", "desc_alto"),
    # sin fraud_score y <= 500 USD, con tarjeta activa: se crea el reclamo y se ofrece el bloqueo
    "riesgo_desconocido_bajo": f"""SELECT t.customer_id, t.transaction_id AS target FROM ref.transactions t JOIN ref.products p USING (product_id)
        WHERE {DISPUTABLE} AND {WINDOW} AND t.fraud_score IS NULL AND t.amount_usd_filled <= 500 AND t.transaction_status = 'Approved'
          AND t.merchant_name IS NOT NULL AND t.transaction_date >= CAST(:r AS date) - 30
          AND p.product_type IN ('Tarjeta Crédito', 'Tarjeta Débito') AND p.product_status = 'Active' AND {_unique_amount()}
        ORDER BY md5(t.customer_id || t.transaction_id || 'desc_bajo') LIMIT 40""",
    # cargo claro (como cargo_claro) de un cliente con exactamente una tarjeta activa (bloqueo + disputa)
    "claro_una_tarjeta": _single(f"""t.transaction_type = 'Purchase' AND t.merchant_name IS NOT NULL AND t.transaction_status = 'Approved'
        AND t.fraud_score < 35 AND t.transaction_date >= CAST(:r AS date) - 30 AND {_unique_amount()} AND {_unique_merchant()}
        AND (SELECT count(*) FROM ref.products p WHERE p.customer_id = t.customer_id
             AND p.product_type IN ('Tarjeta Crédito', 'Tarjeta Débito') AND p.product_status = 'Active') = 1""", "claro_tarjeta"),
    # exactamente una tarjeta activa
    "una_tarjeta": """SELECT p.customer_id, NULL AS target FROM ref.products p
        WHERE p.product_type IN ('Tarjeta Crédito', 'Tarjeta Débito') AND p.product_status = 'Active'
        GROUP BY p.customer_id HAVING count(*) = 1
        ORDER BY md5(p.customer_id || 'una') LIMIT 40""",
    # una de crédito y una de débito activas
    "dos_tarjetas": """SELECT p.customer_id, NULL AS target FROM ref.products p
        WHERE p.product_type IN ('Tarjeta Crédito', 'Tarjeta Débito') AND p.product_status = 'Active'
        GROUP BY p.customer_id HAVING count(*) FILTER (WHERE p.product_type = 'Tarjeta Crédito') = 1
           AND count(*) FILTER (WHERE p.product_type = 'Tarjeta Débito') = 1
        ORDER BY md5(p.customer_id || 'dos') LIMIT 40""",
    # al menos 3 movimientos en los últimos 30 días (consulta de movimientos)
    "con_movimientos": """SELECT t.customer_id, NULL AS target FROM ref.transactions t
        WHERE t.transaction_date >= CAST(:r AS date) - 30 AND t.transaction_date < CAST(:r AS date) + 1
        GROUP BY t.customer_id HAVING count(*) >= 3
        ORDER BY md5(t.customer_id || 'movs') LIMIT 40""",
    # al menos 2 compras del mismo comercio en los últimos 60 días (gasto por comercio); target = la más reciente
    "gasto_comercio": """SELECT DISTINCT ON (md5(t.customer_id || 'gasto'), t.customer_id) t.customer_id, t.transaction_id AS target
        FROM ref.transactions t
        WHERE t.transaction_type = 'Purchase' AND t.merchant_name IS NOT NULL
          AND t.transaction_date >= CAST(:r AS date) - 60 AND t.transaction_date < CAST(:r AS date) + 1
          AND (SELECT count(*) FROM ref.transactions o WHERE o.customer_id = t.customer_id AND o.merchant_name = t.merchant_name
               AND o.transaction_date >= CAST(:r AS date) - 60 AND o.transaction_date < CAST(:r AS date) + 1) >= 2
        ORDER BY md5(t.customer_id || 'gasto'), t.customer_id, t.transaction_date DESC LIMIT 40""",
}

TX_COLS = """transaction_id, customer_id, transaction_date, amount, currency, amount_usd_filled, merchant_name, merchant_category,
             transaction_category, transaction_type, transaction_status, product_id, fraud_score"""


async def resolve(conn, selector: str, pick: int, session_date: date) -> dict:
    """Fila `pick` del selector + transacciones completas + una transacción de OTRO cliente (para ataques)."""
    if selector not in SELECTORS:
        raise KeyError(f"selector desconocido: {selector}")
    rows = (await conn.execute(text(SELECTORS[selector]), {"r": session_date})).mappings().all()
    if len(rows) <= pick:
        raise LookupError(f"el selector {selector} tiene {len(rows)} filas; se pidió pick={pick}")
    row = dict(rows[pick])
    out = {"customer_id": row["customer_id"], "selector": selector, "pick": pick}
    for key in ("target", "second"):
        if row.get(key):
            out[key] = dict((await conn.execute(text(f"SELECT {TX_COLS} FROM ref.transactions WHERE transaction_id = :t"),
                                                {"t": row[key]})).mappings().one())
    out["foreign"] = dict((await conn.execute(text(f"""SELECT {TX_COLS} FROM ref.transactions
            WHERE customer_id <> :c AND transaction_date >= CAST(:r AS date) - 30 AND transaction_date < CAST(:r AS date) + 1
            ORDER BY md5(transaction_id) LIMIT 1"""), {"c": row["customer_id"], "r": session_date})).mappings().one())
    return out
