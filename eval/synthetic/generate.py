"""Dataset sintético para correr el harness de dev en CI, sin el dataset real (que no puede salir de la máquina).

    .venv/bin/python -m eval.synthetic.generate --out /tmp/synth        # solo escribe los CSV
    .venv/bin/python -m eval.synthetic.generate --load <url *_test>     # genera, arma la DuckDB y carga PostgreSQL

- Mismo formato crudo que el dataset (customers.csv, products.csv, daily_exchange_rates.csv y
  transactions/year=…/month=…/day=…/transactions_YYYYMMDD.csv), así pasa por el pipeline real con sus contratos.
- Determinista (semilla fija). Todo es ficticio: IDs SYN-…, nombres inventados, comercios del léxico de alias del ranker.
- Diseñado para que cada selector de eval/cases/selectors.py tenga al menos 40 filas (los casos de dev usan picks de hasta
  34). Cada cliente recibe un escenario principal y movimientos de relleno con montos separados ≥ 30 % entre sí (así el
  "monto único ±10 %" de los selectores se cumple salvo donde el escenario busca lo contrario).
- No es una muestra del dataset real ni deriva de él: sirve para medir regresiones del sistema, no su calidad absoluta.
"""
from __future__ import annotations

import argparse
import csv
import random
from datetime import date, datetime, timedelta
from pathlib import Path

REF = date(2026, 6, 18)          # "hoy" de la demo: último día con transacciones
SEED = 20261001
MERCHANTS = {   # comercio → categoría (léxico de ml/ranker/merchant_aliases.json)
    "Super Ahorro": "Food", "Restaurante El Buen Sabor": "Food", "Tienda Don José": "Food", "Mercado Central": "Food",
    "Empresa Telefónica": "Services", "Cable TV": "Services", "Servicios Públicos": "Services", "Internet Plus": "Services",
    "Estación de Servicio": "Transport", "Uber": "Transport", "Taxi Seguro": "Transport", "Gasolinera Express": "Transport",
    "Ferretería": "Other", "Tienda General": "Other", "Centro Comercial": "Other", "Boutique Moda": "Other",
    "Cine Premium": "Entertainment", "Streaming Music": "Entertainment", "Conciertos Live": "Entertainment", "Teatro Nacional": "Entertainment",
    "Farmacia Salud": "Health", "Clínica Médica": "Health", "Laboratorio Central": "Health", "Óptica Visión": "Health",
}
COUNTRIES = [("México", "Ciudad de México", "CDMX", "mexican", "MXN", 0.055), ("Colombia", "Bogotá", "Cundinamarca", "colombian", "COP", 0.00025),
             ("Argentina", "Buenos Aires", "CABA", "argentine", "ARS", 0.001), ("México", "Monterrey", "Nuevo León", "mexican", "USD", 1.0)]
FIRST = ["Ana", "Luis", "Carmen", "Jorge", "Lucía", "Pedro", "Marta", "Diego", "Sofía", "Andrés", "Paula", "Raúl", "Elena", "Tomás", "Julia",
         "Mateo", "Valeria", "Bruno", "Camila", "Hugo"]
LAST = ["García", "Pérez", "López", "Gómez", "Díaz", "Ruiz", "Torres", "Ramos", "Vega", "Rojas", "Castro", "Molina", "Ortiz", "Silva"]
SCENARIOS = [  # (escenario, clientes)
    ("claro", 60), ("parecidos", 50), ("pendiente", 45), ("revertido", 45), ("plazo", 45), ("riesgo_alto", 45),
    ("desc_alto", 45), ("desc_bajo", 45), ("categoria", 45), ("gasto", 45), ("riesgo_medio", 45),
]
TX_FIELDS = ["transaction_id", "transaction_date", "process_date", "product_id", "customer_id", "transaction_type", "transaction_category",
             "amount", "currency", "amount_usd", "channel", "branch_id", "merchant_name", "merchant_category", "transaction_country",
             "transaction_city", "transaction_status", "response_code", "is_fraud", "fraud_score", "latitude", "longitude"]


class Gen:
    def __init__(self, seed: int = SEED):
        self.r = random.Random(seed)
        self.customers, self.products, self.txs = [], [], []
        self.n_tx = 0

    # ------------------------------------------------------------ piezas
    def customer(self, i: int, scenario: str) -> dict:
        country, city, state, accent, currency, rate = COUNTRIES[i % len(COUNTRIES)]
        cid = f"SYN-C{i:05d}"
        c = {"customer_id": cid, "document_number": f"SYN-DOC-{i:05d}", "document_type": "DNI", "first_name": self.r.choice(FIRST),
             "last_name": self.r.choice(LAST), "date_of_birth": "1988-03-15", "gender": self.r.choice("FM"), "email": "", "mobile_phone": "",
             "landline_phone": "", "address": "", "city": city, "state": state, "country": country, "postal_code": "", "detected_accent": accent,
             "segment": self.r.choice(["Basic", "Plus", "Premium", "Student"]), "credit_score": "", "estimated_monthly_income": "",
             "occupation": "", "marital_status": "", "education_level": "", "registration_date": "2024-01-10 10:00:00",
             "registration_branch_id": "SYN-B001", "customer_status": "Active", "last_updated": "2026-06-01 10:00:00", "accepts_marketing": "False"}
        self.customers.append(c)
        return {"cid": cid, "currency": currency, "rate": rate, "country": country, "city": city, "i": i, "scenario": scenario}

    def card(self, cu: dict, kind: str, n: int, status: str = "Active") -> str:
        pid = f"SYN-P{cu['i']:05d}{n}"
        self.products.append({"product_id": pid, "customer_id": cu["cid"], "product_type": kind, "product_number": f"SYN{cu['i']:09d}{n:04d}",
                              "currency": cu["currency"], "current_balance": "1000.00", "credit_limit": "5000.00" if "Crédito" in kind else "",
                              "interest_rate": "30.0" if "Crédito" in kind else "0.0", "opening_date": "2024-01-15", "expiration_date": "2029-01-31",
                              "opening_branch_id": "SYN-B001", "product_status": status, "opening_channel": "App", "has_linked_app": "True",
                              "days_past_due": "", "last_transaction_date": "2026-06-10 12:00:00", "last_updated": "2026-06-01 10:00:00"})
        return pid

    def tx(self, cu: dict, pid: str, days_ago: int, amount_usd: float, merchant: str | None, *, status: str = "Approved",
           fraud: float | None = 10.0, ttype: str = "Purchase", category: str | None = None, currency: str | None = None) -> None:
        self.n_tx += 1
        process = REF - timedelta(days=days_ago)
        # H16: transaction_date entre 6 y 30 h después de process_date; el último día no pasa de REF
        hours = self.r.randint(6, 17) if days_ago == 0 else self.r.randint(6, 29)   # + minutos: ≤ 30 h (H16)
        tdate = datetime.combine(process, datetime.min.time()) + timedelta(hours=hours, minutes=self.r.randint(0, 59))
        if tdate.date() > REF:
            tdate = datetime.combine(REF, datetime.min.time()) + timedelta(hours=8)
        cur = currency or cu["currency"]
        rate = 1.0 if cur == "USD" else cu["rate"]
        amount = round(amount_usd / rate, 2)
        cat = category or (MERCHANTS.get(merchant) if merchant else "Other")
        self.txs.append({"transaction_id": f"SYN-T{self.n_tx:07d}", "transaction_date": tdate.strftime("%Y-%m-%d %H:%M:%S"),
                         "process_date": process.isoformat(), "product_id": pid, "customer_id": cu["cid"], "transaction_type": ttype,
                         "transaction_category": cat, "amount": f"{amount:.2f}", "currency": cur, "amount_usd": f"{amount * rate:.2f}",
                         "channel": "POS" if merchant else "ATM", "branch_id": "", "merchant_name": merchant or "",
                         "merchant_category": cat if merchant else "", "transaction_country": cu["country"], "transaction_city": cu["city"],
                         "transaction_status": status, "response_code": "00", "is_fraud": "False",
                         "fraud_score": "" if fraud is None else f"{fraud:.2f}", "latitude": "", "longitude": ""})

    def ladder(self, n: int, start: float) -> list[float]:
        """Montos separados ≥ 30 % entre sí (ningún par queda a ±15 %)."""
        return [round(start * (1.35 ** k) + self.r.uniform(0, 0.5), 2) for k in range(n)]

    # ------------------------------------------------------------ escenarios
    def build(self) -> "Gen":
        i = 0
        for scenario, n in SCENARIOS:
            for _ in range(n):
                self.client(i, scenario)
                i += 1
        return self

    def client(self, i: int, scenario: str) -> None:
        cu = self.customer(i, scenario)
        r = self.r
        one_card = i % 2 == 0
        credit = self.card(cu, "Tarjeta Crédito", 1)
        if not one_card:
            self.card(cu, "Tarjeta Débito", 2)
        merchants = list(MERCHANTS)
        r.shuffle(merchants)
        amounts = self.ladder(9, r.uniform(8, 14))
        # relleno: 4 compras recientes (≤ 28 días), comercios y montos únicos, riesgo bajo → con_movimientos y cargo_claro
        used = set()
        for k in range(4):
            m = merchants.pop()
            used.add(m)
            self.tx(cu, credit, r.randint(1, 28), amounts.pop(0), m, fraud=r.uniform(3, 30))
        big = amounts[-1]
        if scenario == "parecidos":       # dos compras de monto a ±5 %, comercios distintos, ≥ 2 días entre sí, ≤ 45 días
            base = amounts.pop(0) * 1.0
            self.tx(cu, credit, r.randint(3, 10), base, merchants.pop(), fraud=r.uniform(3, 30))
            self.tx(cu, credit, r.randint(14, 40), round(base * r.uniform(0.97, 1.03), 2), merchants.pop(), fraud=r.uniform(3, 30))
        elif scenario == "pendiente":
            self.tx(cu, credit, r.randint(1, 20), amounts.pop(0), merchants.pop(), status="Pending", fraud=r.uniform(3, 30))
        elif scenario == "revertido":
            self.tx(cu, credit, r.randint(5, 40), amounts.pop(0), merchants.pop(), status="Reversed", fraud=r.uniform(3, 30))
        elif scenario == "plazo":          # 70–110 días: fuera de R1 pero dentro de la búsqueda
            self.tx(cu, credit, r.randint(75, 105), amounts.pop(0), merchants.pop(), fraud=r.uniform(3, 30))
        elif scenario == "riesgo_alto":    # fraud_score ≥ 80 con la tarjeta activa
            self.tx(cu, credit, r.randint(3, 50), big, merchants.pop(), fraud=r.uniform(82, 97))
        elif scenario == "riesgo_medio":   # fraud_score entre 40 y 65 (banda media del score crudo), tarjeta activa
            self.tx(cu, credit, r.randint(3, 50), big, merchants.pop(), fraud=r.uniform(40, 65))
        elif scenario == "desc_alto":      # sin fraud_score y > 500 USD
            self.tx(cu, credit, r.randint(3, 50), round(r.uniform(650, 1800), 2), merchants.pop(), fraud=None, currency="USD")
        elif scenario == "desc_bajo":      # sin fraud_score y ≤ 500 USD
            self.tx(cu, credit, r.randint(2, 25), amounts.pop(0), merchants.pop(), fraud=None)
        elif scenario == "categoria":      # la única compra de su categoría (Food / Health / Transport)
            cat = ("Food", "Health", "Transport")[i % 3]
            for t in [t for t in self.txs if t["customer_id"] == cu["cid"] and t["transaction_category"] == cat]:
                t["transaction_category"] = t["merchant_category"] = "Other"
            m = next(x for x, c in MERCHANTS.items() if c == cat and x not in used)
            self.tx(cu, credit, r.randint(2, 25), amounts.pop(0), m, fraud=r.uniform(3, 30))
        elif scenario == "gasto":          # dos compras del mismo comercio en 60 días
            m = merchants.pop()
            self.tx(cu, credit, r.randint(2, 20), amounts.pop(0), m, fraud=r.uniform(3, 30))
            self.tx(cu, credit, r.randint(25, 55), amounts.pop(0), m, fraud=r.uniform(3, 30))
        # un retiro y un pago de servicios más viejos (fuera de 30 días), montos únicos
        self.tx(cu, credit, r.randint(35, 60), amounts.pop(0), None, ttype="Withdrawal", category="Other", fraud=r.uniform(3, 30))

    # ------------------------------------------------------------ salida
    def write(self, out: Path) -> Path:
        out.mkdir(parents=True, exist_ok=True)
        self._csv(out / "customers.csv", self.customers)
        self._csv(out / "products.csv", self.products)
        rates = [{"date": (REF - timedelta(days=d)).isoformat(), "source_currency": cur, "target_currency": "USD", "exchange_rate": f"{rate}",
                  "buy_rate": f"{rate * 0.99}", "sell_rate": f"{rate * 1.01}", "source": "Sintético"}
                 for d in range(0, 130) for (_, _, _, _, cur, rate) in COUNTRIES[:3]]
        self._csv(out / "daily_exchange_rates.csv", rates)
        by_day: dict[str, list] = {}
        for t in self.txs:
            by_day.setdefault(t["process_date"], []).append(t)
        for day, rows in by_day.items():
            y, m, d = day.split("-")
            self._csv(out / "transactions" / f"year={y}" / f"month={m}" / f"day={d}" / f"transactions_{y}{m}{d}.csv", rows, TX_FIELDS)
        return out

    @staticmethod
    def _csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields or list(rows[0]))
            w.writeheader()
            w.writerows(rows)


def load(url: str, workdir: Path) -> dict:
    """Genera, arma la DuckDB con el pipeline real y carga la base `url` (debe ser *_test)."""
    from data_pipeline.etl import build_duckdb, load_postgres
    from data_pipeline.run import migrate
    if not url.rsplit("/", 1)[-1].endswith("_test"):
        raise SystemExit("solo se carga en bases *_test")
    src = Gen().build().write(workdir / "src")
    db = workdir / "synthetic.duckdb"
    db.unlink(missing_ok=True)
    build_duckdb.build_full(src, db)
    migrate(url)
    return load_postgres.load_full(url, db, src)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m eval.synthetic.generate")
    ap.add_argument("--out", type=Path, default=Path("/tmp/synthetic_dataset"))
    ap.add_argument("--load", metavar="DATABASE_URL", help="además arma la DuckDB y carga esa base *_test")
    a = ap.parse_args(argv)
    if a.load:
        print(load(a.load, a.out))
    else:
        g = Gen().build()
        g.write(a.out)
        print(f"{len(g.customers)} clientes, {len(g.products)} productos, {len(g.txs)} transacciones → {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
