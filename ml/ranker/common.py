"""Constantes y utilidades compartidas por los notebooks y el generador del ranker.

La base DuckDB se lee siempre desde disco y en modo solo lectura. La ruta se toma de
BANK_DUCKDB; si no está definida se usa la copia local del dashboard exploratorio.
"""

from __future__ import annotations

import os
from pathlib import Path

import duckdb

REPO = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.environ.get("BANK_DUCKDB", REPO / "dashboard" / "data" / "bank.duckdb"))
OUT_DIR = REPO / "data" / "processed" / "ranker"
SEED = 42

# Universo disputable (ver 01_data_audit.ipynb, sección 4): cargos iniciados contra la
# cuenta del cliente. Deposit es un abono; Transfer y Adjustment no tienen comercio ni
# categoría y el cliente los origina o el banco los aplica.
DISPUTABLE_TYPES = ("Purchase", "Payment", "Withdrawal")
# Solo un cargo aplicado o en curso puede ser el objetivo de un reclamo. Declined y
# Reversed siguen siendo candidatas (el cliente los ve en su extracto).
TARGET_STATUSES = ("Approved", "Pending")

WINDOW_DAYS = 60          # ventana de búsqueda por defecto antes de la fecha de sesión
MAX_SESSION_LAG_DAYS = 30  # la sesión ocurre entre 0 y 30 días después de la transacción


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    con.execute("SET threads TO 8")
    return con


def sql_list(values) -> str:
    return ", ".join(f"'{v}'" for v in values)


DISPUTABLE_SQL = f"transaction_type IN ({sql_list(DISPUTABLE_TYPES)})"
