"""Motor de contratos de datos: lee los YAML de esta carpeta y los evalúa en DuckDB.

Cada contrato declara columnas (tipo, nulabilidad, derivación), PK y reglas. Tipos de regla:

    not_null  implícita por cada columna con nullable: false (siempre bloqueante)
    domain    column ∈ values (los NULL los gobierna not_null)
    range     min <= column <= max
    unique    columns sin repetir
    fk        columns existen en references.table (filas cargables del padre, o lo que ya
              está en PostgreSQL en la carga incremental)
    expr      predicado SQL que debe ser verdadero (NULL cuenta como verdadero)

severity: block → la fila va a cuarentena (_rejected) con el id de la regla como motivo; se
evalúan en orden y manda la primera que falla. warn → solo se cuenta.
Las columnas del contrato deben coincidir con el modelo SQLAlchemy (lo verifica un test).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import yaml

HERE = Path(__file__).resolve().parent
LOAD_ORDER = ("customers", "products", "transactions", "daily_exchange_rates")


@dataclass
class Rule:
    id: str
    check: str
    severity: str
    column: str | None = None
    columns: list[str] = field(default_factory=list)
    values: list | None = None
    min: float | None = None
    max: float | None = None
    expr: str | None = None
    references: dict | None = None
    why: str | None = None


@dataclass
class Contract:
    table: str
    version: int
    primary_key: list[str]
    columns: dict[str, dict]
    rules: list[Rule]
    partition: str | None = None

    @property
    def all_rules(self) -> list[Rule]:
        """not_null implícitas (bloqueantes) primero, luego las declaradas."""
        nn = [Rule(id=f"{self.table}_{c}_not_null", check="not_null", severity="block", column=c)
              for c, spec in self.columns.items() if not spec.get("nullable", True) and "derived" not in spec]
        return nn + self.rules

    def pk_expr(self, alias: str = "x") -> str:
        return " || '|' || ".join(f'CAST({alias}."{c}" AS VARCHAR)' for c in self.primary_key)


def load_contracts(folder: Path = HERE) -> dict[str, Contract]:
    out = {}
    for path in sorted(folder.glob("*.yaml")):
        d = yaml.safe_load(path.read_text(encoding="utf-8"))
        rules = [Rule(**r) for r in d.get("rules", [])]
        for r in rules:
            assert r.severity in ("block", "warn"), f"{path.name}: {r.id} severity inválida"
            assert r.check in ("domain", "range", "unique", "fk", "expr"), f"{path.name}: {r.id} check inválido"
        out[d["table"]] = Contract(d["table"], d["version"], d["primary_key"], d["columns"], rules, d.get("partition"))
    return out


def quote(v) -> str:
    return "'" + str(v).replace("'", "''") + "'"


def violation(rule: Rule, parent_rel: str | None = None) -> str:
    """Predicado SQL (sobre el alias x) que es verdadero cuando la fila INCUMPLE la regla."""
    c = f'x."{rule.column}"' if rule.column else None
    if rule.check == "not_null":
        return f"{c} IS NULL"
    if rule.check == "domain":
        return f"{c} IS NOT NULL AND {c} NOT IN ({', '.join(quote(v) for v in rule.values)})"
    if rule.check == "range":
        conds = ([f"{c} < {rule.min}"] if rule.min is not None else []) + ([f"{c} > {rule.max}"] if rule.max is not None else [])
        return f"{c} IS NOT NULL AND ({' OR '.join(conds)})"
    if rule.check == "expr":
        return f"NOT coalesce(({rule.expr}), TRUE)"
    if rule.check == "fk":
        on = " AND ".join(f'p."{pc}" = x."{cc}"' for cc, pc in zip(rule.columns, rule.references["columns"]))
        nonnull = " AND ".join(f'x."{cc}" IS NOT NULL' for cc in rule.columns)
        return f"{nonnull} AND NOT EXISTS (SELECT 1 FROM {parent_rel} p WHERE {on})"
    raise ValueError(rule.check)


def evaluate(con, contracts: dict[str, Contract], relations: dict[str, str],
             parent_override: dict[str, str] | None = None) -> tuple[pd.DataFrame, dict]:
    """Evalúa los contratos de las tablas de `relations` ({tabla: subconsulta con las filas a cargar}).

    Crea la tabla temporal _rejected (table_name, pk_value, partition_date, reason, detail, row_data) y
    devuelve (rechazos por tabla y motivo, advertencias {tabla: {regla: n}}).
    `parent_override`: relación a usar como padre en las FK (p. ej. lo que ya está en PostgreSQL).
    """
    parent_override = parent_override or {}
    con.execute("""CREATE OR REPLACE TEMP TABLE _rejected (table_name VARCHAR, pk_value VARCHAR, partition_date DATE,
                   reason VARCHAR, detail VARCHAR, row_data JSON)""")
    warnings: dict[str, dict[str, int]] = {}
    for t in [t for t in LOAD_ORDER if t in relations]:
        ct = contracts[t]
        base = relations[t]
        pk = ct.pk_expr()
        part = f'x."{ct.partition}"' if ct.partition else "NULL::DATE"
        not_rejected = f"{pk} NOT IN (SELECT pk_value FROM _rejected WHERE table_name = '{t}')"
        for r in ct.all_rules:
            parent = None
            if r.check == "fk":
                pt = r.references["table"]
                if pt in parent_override:
                    parent = parent_override[pt]
                else:  # filas cargables del padre: las de su relación que no fueron a cuarentena
                    pc = contracts[pt]
                    parent = (f"(SELECT * FROM {relations[pt]} y WHERE {pc.pk_expr('y')} NOT IN "
                              f"(SELECT pk_value FROM _rejected WHERE table_name = '{pt}'))")
            if r.check == "unique":
                cols = ", ".join(f'"{c}"' for c in r.columns)
                xcols = ", ".join(f'x."{c}"' for c in r.columns)
                nn = " AND ".join(f'z."{c}" IS NOT NULL' for c in r.columns)
                pred = f"({xcols}) IN (SELECT {cols} FROM {base} z WHERE {nn} GROUP BY ALL HAVING count(*) > 1)"
                if r.severity == "block":  # se conserva la primera por PK y el resto va a cuarentena
                    order = ", ".join(f'"{c}"' for c in ct.primary_key)
                    pred = (f"{pk} IN (SELECT {ct.pk_expr('w')} FROM (SELECT *, row_number() OVER (PARTITION BY {cols} "
                            f"ORDER BY {order}) AS rn FROM {base} w) w WHERE rn > 1)")
            else:
                pred = violation(r, parent)
            if r.severity == "block":
                con.execute(f"""INSERT INTO _rejected SELECT '{t}', {pk}, {part}, '{r.id}', {quote(r.why) if r.why else 'NULL'},
                                to_json(x) FROM {base} x WHERE ({pred}) AND {not_rejected}""")
            else:
                n = con.execute(f"SELECT count(*) FROM {base} x WHERE ({pred}) AND {not_rejected}").fetchone()[0]
                if n:
                    warnings.setdefault(t, {})[r.id] = int(n)
    rej = con.execute("SELECT table_name, reason, count(*) AS n FROM _rejected GROUP BY ALL ORDER BY ALL").df()
    return rej, warnings


def export_select(contract: Contract, model_columns: list, relation: str) -> str:
    """SELECT de exportación: columnas del modelo en su tipo exacto (derivadas según el contrato)."""
    from sqlalchemy import Boolean, Numeric

    exprs = []
    for col in model_columns:
        spec = contract.columns.get(col.name, {})
        src = f"({spec['derived']})" if "derived" in spec else f'"{col.name}"'
        if isinstance(col.type, Numeric):
            src = f"CAST(round({src}, {col.type.scale}) AS DECIMAL({col.type.precision},{col.type.scale}))"
        elif isinstance(col.type, Boolean):
            src = f"CAST({src} AS BOOLEAN)"
        exprs.append(f'{src} AS "{col.name}"')
    return f"SELECT {', '.join(exprs)} FROM {relation} x"
