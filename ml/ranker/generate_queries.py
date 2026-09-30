"""Genera el dataset de ranking (consulta, candidatas, transacción correcta) con etiquetas por construcción.

Cada consulta parte de una transacción REAL del dataset (la objetivo). Se simula cómo la describiría
el cliente (pistas estructuradas con ruido controlado) y se arma el conjunto de candidatas con TODAS
las transacciones disputables del mismo cliente en la ventana de búsqueda, sin filtrar por monto.
No se fabrican transacciones: el único dato inventado es la consulta.

Uso:
    python ml/ranker/generate_queries.py            # tamaños por defecto
    python ml/ranker/generate_queries.py --small    # prueba rápida

Salidas en data/processed/ranker/ (excluido por .gitignore):
    queries.parquet   una fila por consulta: pistas, parámetros de ruido, objetivo, split
    pairs.parquet     formato largo: query_id, customer_id, target_tx_id, candidate_tx_id, label, features…, noise_params, split
    manifest.json     versión, semilla, cortes, tamaños y controles de leakage
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from rapidfuzz import fuzz

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    DISPUTABLE_SQL, MAX_SESSION_LAG_DAYS, OUT_DIR, SEED, TARGET_STATUSES, WINDOW_DAYS, connect, sql_list,
)

GENERATOR_VERSION = "1.0.0"
ALIASES_PATH = Path(__file__).resolve().parent / "merchant_aliases.json"

# --- Distribución de ruido (documentada en docs/ml/ranker-data-report.md) ---------------------
AMOUNT_MODES = {"exact": 0.30, "rounded": 0.40, "absent": 0.20, "wrong": 0.10}
MERCHANT_MODES = {"name": 0.25, "fragment": 0.15, "category": 0.20, "absent": 0.30, "descriptor": 0.10}
DATE_MODES = {"exact": 0.20, "relative": 0.40, "absent": 0.25, "shifted": 0.15}
CURRENCY_MODES = {"present": 0.40, "absent": 0.60}
WRONG_AMOUNT_RANGE = (0.05, 0.15)   # |error| relativo del monto "equivocado"
DATE_SHIFTS = (-2, -1, 1, 2)        # días de desplazamiento de la fecha "desplazada"
TEMPLATE_HOLDOUT_FRAC = 0.20        # fracción de plantillas (monto×comercio×fecha) reservadas

# --- Splits: por cliente Y temporal sobre la fecha de sesión ----------------------------------
SPLIT_BUCKETS = {"train": (0, 70), "val": (70, 85), "test": (85, 100)}   # hash(customer_id) % 100
T_VAL, T_TEST = "2025-09-01", "2026-01-01"                                # cortes de fecha de sesión
SIZES = {"natural": {"train": 60_000, "val": 10_000, "test": 10_000},
         "hard": {"train": 12_000, "val": 2_000, "test": 2_000}}
AMOUNT_TOL = 0.10  # "mismo monto" para distractores: el cliente que redondea no distingue ±10 %

STOPWORDS = {"un", "una", "el", "la", "los", "las", "de", "del", "en", "que", "no", "hice", "al", "y", "mi"}
FORBIDDEN_FEATURES = {"is_fraud", "fraud_score", "label", "target_tx_id"}


# ============================================================================================
# Texto y resolución de pistas (lo que haría el código después de la extracción del LLM)
# ============================================================================================
def normalize(text: str | None) -> str:
    if not text:
        return ""
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    tokens = [w for w in re.split(r"[^a-z0-9]+", t) if w and w not in STOPWORDS and not w.isdigit()]
    return " ".join(tokens)


@lru_cache(maxsize=None)
def merchant_similarity(clue: str, merchant_name: str) -> float:
    """Similitud 0–1 entre lo que dijo el cliente y el nombre del comercio de la candidata."""
    a, b = normalize(clue), normalize(merchant_name)
    if not a or not b:
        return 0.0
    return max(fuzz.token_set_ratio(a, b), fuzz.partial_ratio(a.replace(" ", ""), b.replace(" ", ""))) / 100


class HintResolver:
    """Convierte el texto de comercio dicho por el cliente en categorías y tipo posibles.

    Solo usa el léxico versionado y el catálogo de comercios; nunca la transacción objetivo.
    """

    def __init__(self, aliases: dict):
        self.merchants = {m: v["category"] for m, v in aliases["merchants"].items()}
        self.kw_cat = aliases["keywords"]["categories"]
        self.kw_type = aliases["keywords"]["types"]

    @lru_cache(maxsize=None)
    def resolve(self, text: str | None) -> tuple[str, str | None]:
        if not text:
            return "", None
        toks = normalize(text).split()
        cats = {c for t in toks for c in self.kw_cat.get(t, [])}
        cats |= {cat for m, cat in self.merchants.items() if merchant_similarity(text, m) >= 0.9}
        types = {self.kw_type[t] for t in toks if t in self.kw_type}
        if cats and not types:
            types = {"Purchase", "Payment"}  # una categoría de comercio implica compra o pago
        return "|".join(sorted(cats)), "|".join(sorted(types)) or None


# ============================================================================================
# Ruido
# ============================================================================================
def choose(rng: np.random.Generator, dist: dict) -> str:
    return rng.choice(list(dist), p=list(dist.values()))


def round_sig(x: float, sig: int = 2) -> float:
    """Redondeo 'humano': 252.14 → 250, 1_867_136 → 1_900_000, 7.43 → 7."""
    if x < 10:
        return float(round(x))
    mag = 10 ** (int(np.floor(np.log10(x))) - sig + 1)
    return float(round(x / mag) * mag)


def relative_options(s: date, d: date) -> list[str]:
    """Expresiones relativas verdaderas para una transacción del día d vista en la sesión del día s."""
    lag = (s - d).days
    opts = []
    if lag == 0: opts.append("hoy")
    if lag == 1: opts.append("ayer")
    if lag == 2: opts.append("anteayer")
    if 2 <= lag <= 6: opts.append(f"hace {lag} días")
    mon = s - timedelta(days=s.weekday())
    if 1 <= lag and d >= mon: opts.append("esta semana")
    if mon - timedelta(days=7) <= d < mon: opts.append("la semana pasada")
    if 7 <= lag <= 10: opts.append("hace una semana")
    if 11 <= lag <= 17: opts.append("hace dos semanas")
    if 18 <= lag <= 30: opts.append("hace como un mes")
    if d.month == s.month and d.year == s.year and lag >= 3: opts.append("este mes")
    prev = s.replace(day=1) - timedelta(days=1)
    if d.month == prev.month and d.year == prev.year: opts.append("el mes pasado")
    return opts


def resolve_relative(expr: str, s: date) -> tuple[date, date]:
    """Convierte una fecha relativa en rango [desde, hasta] (código determinista del workflow)."""
    mon = s - timedelta(days=s.weekday())
    if expr == "hoy": return s, s
    if expr == "ayer": return s - timedelta(1), s - timedelta(1)
    if expr == "anteayer": return s - timedelta(2), s - timedelta(2)
    if m := re.fullmatch(r"hace (\d+) días", expr):
        n = int(m.group(1)); return s - timedelta(n + 1), s - timedelta(n - 1)
    if expr == "esta semana": return mon, s
    if expr == "la semana pasada": return mon - timedelta(7), mon - timedelta(1)
    if expr == "hace una semana": return s - timedelta(10), s - timedelta(5)
    if expr == "hace dos semanas": return s - timedelta(18), s - timedelta(10)
    if expr == "hace como un mes": return s - timedelta(35), s - timedelta(18)
    if expr == "este mes": return s.replace(day=1), s
    if expr == "el mes pasado":
        last = s.replace(day=1) - timedelta(1); return last.replace(day=1), last
    raise ValueError(expr)


def make_clue(rng: np.random.Generator, t: pd.Series, aliases: dict, resolver: HintResolver) -> dict:
    """Pistas estructuradas para una transacción objetivo t + los parámetros de ruido usados."""
    p: dict = {}
    # Monto
    am = choose(rng, AMOUNT_MODES); p["amount_mode"] = am
    amount, approx = None, False
    if am == "exact":
        amount = round(t.amount, 2)
    elif am == "rounded":
        amount, approx = round_sig(t.amount), True
    elif am == "wrong":
        e = rng.uniform(*WRONG_AMOUNT_RANGE) * rng.choice([-1, 1]); p["amount_error"] = round(float(e), 4)
        amount = round_sig(t.amount * (1 + e))   # el cliente lo dice con seguridad (sin "como")
    # Comercio
    mm = choose(rng, MERCHANT_MODES); p["merchant_mode"] = mm
    has_name = isinstance(t.merchant_name, str)
    eff, text = mm, None
    if mm != "absent" and not has_name:
        # Sin comercio (pagos, retiros, 5 % de compras): el cliente solo puede nombrar categoría o tipo
        tinfo = aliases["types"][t.transaction_type]
        if mm == "descriptor":
            text = str(rng.choice(tinfo["descriptors"]))
        elif mm == "category" and isinstance(t.category, str):
            text = str(rng.choice(aliases["categories"][t.category]))
        else:
            eff, text = "type", str(rng.choice(tinfo["phrases"]))
    elif mm == "name":
        text = t.merchant_name
    elif mm == "fragment":
        text = str(rng.choice(aliases["merchants"][t.merchant_name]["fragments"]))
    elif mm == "category":
        text = str(rng.choice(aliases["categories"][t.category]))
    elif mm == "descriptor":
        text = str(rng.choice(aliases["merchants"][t.merchant_name]["descriptors"]))
        if rng.random() < 0.5:
            text += f" {rng.integers(0, 10_000):04d}"
    p["merchant_mode_eff"] = eff
    cat_hint, type_hint = resolver.resolve(text)
    # Fecha
    dm = choose(rng, DATE_MODES); p["date_mode"] = dm
    s, d = t.session_ts.date(), t.transaction_date.date()
    lo = hi = None; expr = None
    if dm == "exact":
        lo = hi = d
    elif dm == "shifted":
        k = int(rng.choice(DATE_SHIFTS)); p["date_shift"] = k
        lo = hi = min(d + timedelta(k), s)
    elif dm == "relative":
        expr = str(rng.choice(relative_options(s, d))); p["date_expr"] = expr
        lo, hi = resolve_relative(expr, s)
        assert lo <= d <= hi, (expr, s, d)
    # Moneda
    cm = choose(rng, CURRENCY_MODES); p["currency_mode"] = cm
    p["session_lag_days"] = round((t.session_ts - t.transaction_date).total_seconds() / 86400, 3)
    return {
        "q_amount": amount, "q_amount_approx": approx, "q_currency": t.currency if cm == "present" else None,
        "q_merchant_text": text, "q_category_hint": cat_hint or None, "q_type_hint": type_hint,
        "q_date_from": lo, "q_date_to": hi, "q_date_expr": expr,
        "template_id": f"{am}|{mm}|{dm}", "noise_params": json.dumps(p, ensure_ascii=False, sort_keys=True),
        **{f"noise_{k}": v for k, v in p.items() if k in ("amount_mode", "merchant_mode", "merchant_mode_eff", "date_mode", "currency_mode")},
    }


# ============================================================================================
# Features por par (solo información disponible en la sesión)
# ============================================================================================
FEATURES = [
    "amt_missing", "amt_rel_diff", "amt_log_ratio_abs", "amt_exact", "amt_within_5", "amt_within_10", "amt_within_20",
    "amt_approx_flag", "amt_rank", "amt_gap_to_best",
    "date_missing", "date_is_relative", "date_days_to_range", "date_in_range", "date_range_width",
    "days_since_tx", "recency_rank",
    "merch_missing", "merch_sim", "merch_sim_rank", "cat_hint_missing", "cat_match", "type_hint_missing", "type_match",
    "cand_has_merchant", "cand_is_purchase", "cand_is_payment", "cand_is_withdrawal",
    "status_declined", "status_reversed", "status_pending",
    "cur_missing", "cur_match", "n_candidates",
]


def build_features(pairs: pd.DataFrame) -> pd.DataFrame:
    f = pairs
    has_amt = f.q_amount.notna()
    rel = (f.amount - f.q_amount).abs() / f.q_amount
    f["amt_missing"] = (~has_amt).astype(int)
    f["amt_rel_diff"] = rel.clip(upper=5).fillna(0)
    f["amt_log_ratio_abs"] = np.log(f.amount / f.q_amount).abs().clip(upper=5).fillna(0)
    f["amt_exact"] = ((f.amount - f.q_amount).abs() < 0.005).astype(int)
    for k in (5, 10, 20):
        f[f"amt_within_{k}"] = (rel <= k / 100).fillna(False).astype(int)
    f["amt_approx_flag"] = f.q_amount_approx.astype(int)
    f["amt_rank"] = rel.fillna(0).groupby(f.query_id).rank(method="min")
    f["amt_gap_to_best"] = (rel - rel.groupby(f.query_id).transform("min")).clip(upper=5).fillna(0)

    has_date = f.q_date_from.notna()
    cd = f.transaction_date.dt.normalize()
    lo, hi = pd.to_datetime(f.q_date_from), pd.to_datetime(f.q_date_to)
    dist = np.maximum((lo - cd).dt.days, (cd - hi).dt.days).clip(lower=0)
    f["date_missing"] = (~has_date).astype(int)
    f["date_is_relative"] = f.q_date_expr.notna().astype(int)
    f["date_days_to_range"] = dist.fillna(0).clip(upper=60)
    f["date_in_range"] = ((dist == 0) & has_date).astype(int)
    f["date_range_width"] = ((hi - lo).dt.days + 1).fillna(0)
    f["days_since_tx"] = (f.session_ts - f.transaction_date).dt.total_seconds() / 86400
    f["recency_rank"] = f.days_since_tx.groupby(f.query_id).rank(method="min")

    has_m = f.q_merchant_text.notna()
    f["merch_missing"] = (~has_m).astype(int)
    f["merch_sim"] = [merchant_similarity(a, b) if isinstance(a, str) and isinstance(b, str) else 0.0
                      for a, b in zip(f.q_merchant_text, f.merchant_name)]
    f["merch_sim_rank"] = (-f.merch_sim).groupby(f.query_id).rank(method="min")
    f["cat_hint_missing"] = f.q_category_hint.isna().astype(int)
    f["cat_match"] = [int(isinstance(h, str) and isinstance(c, str) and c in h.split("|"))
                      for h, c in zip(f.q_category_hint, f.category)]
    f["type_hint_missing"] = f.q_type_hint.isna().astype(int)
    f["type_match"] = [int(isinstance(h, str) and c in h.split("|")) for h, c in zip(f.q_type_hint, f.transaction_type)]
    f["cand_has_merchant"] = f.merchant_name.notna().astype(int)
    for t in ("Purchase", "Payment", "Withdrawal"):
        f[f"cand_is_{t.lower()}"] = (f.transaction_type == t).astype(int)
    for s in ("Declined", "Reversed", "Pending"):
        f[f"status_{s.lower()}"] = (f.transaction_status == s).astype(int)
    f["cur_missing"] = f.q_currency.isna().astype(int)
    f["cur_match"] = (f.q_currency == f.currency).astype(int)
    f["n_candidates"] = f.groupby("query_id").query_id.transform("size")
    return f


# ============================================================================================
# Pipeline
# ============================================================================================
def build_pool(con, seed: int) -> None:
    """Todas las objetivo posibles con sesión simulada, split y conteo de distractores."""
    lag_mod = MAX_SESSION_LAG_DAYS * 86400
    con.execute(f"""
    CREATE OR REPLACE TEMP TABLE disp AS
    SELECT transaction_id, customer_id, transaction_date, amount, currency, transaction_type, transaction_status,
           merchant_name, coalesce(merchant_category, transaction_category) AS category, channel, customer_country,
           coalesce(merchant_name, transaction_category, transaction_type) AS merchant_key
    FROM transactions WHERE {DISPUTABLE_SQL}""")
    lo, hi = con.execute("SELECT min(transaction_date), max(transaction_date) FROM transactions").fetchone()
    case = " ".join(f"WHEN cb >= {a} AND cb < {z} THEN '{s}'" for s, (a, z) in SPLIT_BUCKETS.items())
    con.execute(f"""
    CREATE OR REPLACE TEMP TABLE pool AS
    WITH p0 AS (
      SELECT *, transaction_date + to_seconds((hash(transaction_id, {seed}) % {lag_mod})::BIGINT) AS session_ts,
             hash(customer_id, {seed}) % 100 AS cb
      FROM disp WHERE transaction_status IN ({sql_list(TARGET_STATUSES)})),
    p AS (SELECT * EXCLUDE (cb), CASE {case} END AS cust_split FROM p0)
    SELECT *, CASE
        WHEN cust_split = 'train' AND session_ts < TIMESTAMP '{T_VAL}' THEN 'train'
        WHEN cust_split = 'val' AND session_ts >= TIMESTAMP '{T_VAL}' AND session_ts < TIMESTAMP '{T_TEST}' THEN 'val'
        WHEN cust_split = 'test' AND session_ts >= TIMESTAMP '{T_TEST}' THEN 'test' END AS split
    FROM p
    WHERE session_ts <= TIMESTAMP '{hi}' AND session_ts - INTERVAL {WINDOW_DAYS} DAY >= TIMESTAMP '{lo}'""")
    con.execute("DELETE FROM pool WHERE split IS NULL")
    con.execute(f"""
    CREATE OR REPLACE TEMP TABLE pool_d AS
    SELECT t.*, count(c.transaction_id) AS n_candidates_pool,
           count(*) FILTER (WHERE c.transaction_id <> t.transaction_id AND c.amount = t.amount) AS d_same_amount,
           count(*) FILTER (WHERE c.transaction_id <> t.transaction_id AND abs(c.amount - t.amount) <= {AMOUNT_TOL} * t.amount) AS d_amount10,
           count(*) FILTER (WHERE c.transaction_id <> t.transaction_id AND c.merchant_key = t.merchant_key) AS d_merchant,
           count(*) FILTER (WHERE c.transaction_id <> t.transaction_id AND c.merchant_key = t.merchant_key
                                  AND abs(c.amount - t.amount) <= {AMOUNT_TOL} * t.amount) AS d_both
    FROM pool t JOIN disp c ON c.customer_id = t.customer_id
     AND c.transaction_date BETWEEN t.session_ts - INTERVAL {WINDOW_DAYS} DAY AND t.session_ts
    GROUP BY ALL""")


def sample_queries(con, sizes: dict, seed: int) -> pd.DataFrame:
    parts = []
    for split, n in sizes["natural"].items():
        parts.append(con.execute(f"""SELECT *, 'natural' AS subset FROM pool_d WHERE split = '{split}'
                                     ORDER BY hash(transaction_id, {seed} + 1) LIMIT {n}""").df())
    nat_ids = set(pd.concat(parts).transaction_id)
    con.register("nat_ids", pd.DataFrame({"transaction_id": sorted(nat_ids)}))
    for split, n in sizes["hard"].items():
        # "hard": la objetivo tiene al menos un distractor con mismo comercio Y monto ±10 %
        parts.append(con.execute(f"""SELECT *, 'hard' AS subset FROM pool_d WHERE split = '{split}' AND d_both > 0
                                     AND transaction_id NOT IN (SELECT transaction_id FROM nat_ids)
                                     ORDER BY hash(transaction_id, {seed} + 2) LIMIT {n}""").df())
    q = pd.concat(parts, ignore_index=True).sort_values(["split", "subset", "transaction_id"], ignore_index=True)
    q.insert(0, "query_id", [f"Q{i:06d}" for i in range(len(q))])
    return q.rename(columns={"transaction_id": "target_tx_id"})


def fetch_candidates(con, queries: pd.DataFrame) -> pd.DataFrame:
    con.register("qs", queries[["query_id", "customer_id", "session_ts"]])
    return con.execute(f"""
    SELECT q.query_id, c.transaction_id AS candidate_tx_id, c.transaction_date, c.amount, c.currency, c.transaction_type,
           c.transaction_status, c.merchant_name, c.category
    FROM qs q JOIN disp c ON c.customer_id = q.customer_id
     AND c.transaction_date BETWEEN q.session_ts - INTERVAL {WINDOW_DAYS} DAY AND q.session_ts
    ORDER BY q.query_id, c.transaction_date, c.transaction_id""").df()


def template_holdout(seed: int) -> set[str]:
    combos = sorted(f"{a}|{m}|{d}" for a in AMOUNT_MODES for m in MERCHANT_MODES for d in DATE_MODES)
    rng = np.random.default_rng(seed)
    return set(rng.choice(combos, size=int(len(combos) * TEMPLATE_HOLDOUT_FRAC), replace=False))


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--small", action="store_true", help="tamaños reducidos para prueba")
    args = ap.parse_args()
    sizes = {k: {s: (n // 20 if args.small else n) for s, n in v.items()} for k, v in SIZES.items()}
    aliases = json.loads(ALIASES_PATH.read_text(encoding="utf-8"))
    resolver = HintResolver(aliases)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    con = connect()
    build_pool(con, args.seed)
    pool_stats = con.execute("""
        SELECT split, count(*) AS pool, avg(n_candidates_pool) AS cand_media,
               avg((d_same_amount > 0)::INT) AS pct_d_same_amount, avg((d_amount10 > 0)::INT) AS pct_d_amount10,
               avg((d_merchant > 0)::INT) AS pct_d_merchant, avg((d_both > 0)::INT) AS pct_d_both
        FROM pool_d GROUP BY 1 ORDER BY 1""").df()
    queries = sample_queries(con, sizes, args.seed)
    cands = fetch_candidates(con, queries)
    # El comercio define su categoría 1:1 (01_data_audit, sección 2): se completa cuando falta
    merchant_cat = {m: v["category"] for m, v in aliases["merchants"].items()}
    for df in (queries, cands):
        df["category"] = df.category.fillna(df.merchant_name.map(merchant_cat))

    rng = np.random.default_rng(args.seed)
    clues = pd.DataFrame([make_clue(rng, t, aliases, resolver) for t in queries.itertuples(index=False)])
    queries = pd.concat([queries, clues], axis=1)
    holdout = template_holdout(args.seed)
    queries["tpl_holdout"] = queries.template_id.isin(holdout)
    tx_d = queries.transaction_date.dt.normalize()
    queries["target_in_clue_range"] = np.where(
        queries.q_date_from.isna(), np.nan,
        ((tx_d >= pd.to_datetime(queries.q_date_from)) & (tx_d <= pd.to_datetime(queries.q_date_to))).astype(float))

    qcols = ["query_id", "customer_id", "target_tx_id", "session_ts", "split", "subset", "customer_country", "channel",
             "q_amount", "q_amount_approx", "q_currency", "q_merchant_text", "q_category_hint", "q_type_hint",
             "q_date_from", "q_date_to", "q_date_expr", "template_id", "tpl_holdout", "noise_params"]
    pairs = cands.merge(queries[qcols], on="query_id", how="left")
    pairs["label"] = (pairs.candidate_tx_id == pairs.target_tx_id).astype(int)
    pairs = build_features(pairs)
    queries["n_candidates"] = queries.query_id.map(pairs.groupby("query_id").size())

    # ---- Controles de leakage y consistencia (fallan en voz alta) ---------------------------
    pos = pairs.groupby("query_id").label.sum()
    assert (pos == 1).all(), "cada consulta debe tener exactamente una candidata correcta"
    assert set(pos.index) == set(queries.query_id), "consulta sin candidatas"
    splits_by_cust = queries.groupby("customer_id").split.nunique()
    assert (splits_by_cust == 1).all(), "un cliente aparece en dos splits"
    cand_split = pairs.groupby("candidate_tx_id").split.nunique()
    assert (cand_split == 1).all(), "una candidata aparece en dos splits"
    assert not FORBIDDEN_FEATURES & set(FEATURES)
    assert (pairs.transaction_date <= pairs.session_ts).all(), "candidata posterior a la sesión"
    leak = {c: float(abs(np.corrcoef(pairs[c], pairs.label)[0, 1])) for c in FEATURES if pairs[c].std() > 0}
    tmax = queries.groupby("split").session_ts.agg(["min", "max"])
    assert tmax.loc["train", "max"] < tmax.loc["val", "min"] and tmax.loc["val", "max"] < tmax.loc["test", "min"]

    out_pairs = pairs[["query_id", "customer_id", "target_tx_id", "candidate_tx_id", "label", *FEATURES,
                       "noise_params", "template_id", "tpl_holdout", "split", "subset", "customer_country",
                       "transaction_status", "transaction_type"]]
    queries.to_parquet(OUT_DIR / "queries.parquet", index=False)
    out_pairs.to_parquet(OUT_DIR / "pairs.parquet", index=False)

    natural = queries[queries.subset == "natural"]
    manifest = {
        "generator_version": GENERATOR_VERSION, "seed": args.seed, "aliases_version": aliases["version"],
        "aliases_sha": file_sha(ALIASES_PATH), "window_days": WINDOW_DAYS, "max_session_lag_days": MAX_SESSION_LAG_DAYS,
        "noise": {"amount": AMOUNT_MODES, "merchant": MERCHANT_MODES, "date": DATE_MODES, "currency": CURRENCY_MODES,
                  "wrong_amount_range": WRONG_AMOUNT_RANGE, "date_shifts": DATE_SHIFTS},
        "splits": {"customer_buckets": SPLIT_BUCKETS, "t_val": T_VAL, "t_test": T_TEST,
                   "session_range": {s: [str(r["min"]), str(r["max"])] for s, r in tmax.iterrows()}},
        "template_holdout": sorted(holdout),
        "sizes": {"queries": queries.groupby(["split", "subset"]).size().unstack().to_dict(),
                  "pairs": pairs.groupby("split").size().to_dict(),
                  "customers": queries.groupby("split").customer_id.nunique().to_dict()},
        "pool": pool_stats.round(4).to_dict(orient="records"),
        "natural_distractors": {
            "pct_same_amount_exact": round(float((natural.d_same_amount > 0).mean()), 4),
            "pct_amount10": round(float((natural.d_amount10 > 0).mean()), 4),
            "pct_same_merchant": round(float((natural.d_merchant > 0).mean()), 4),
            "pct_both": round(float((natural.d_both > 0).mean()), 4)},
        "pct_target_outside_clue_date_range": round(float(1 - queries.target_in_clue_range.mean()), 4),
        "checks": {"one_positive_per_query": True, "customer_disjoint": True, "candidate_disjoint": True,
                   "temporal_order": True, "no_forbidden_features": True, "max_abs_corr_feature_label": round(max(leak.values()), 4),
                   "feature_max_corr": max(leak, key=leak.get)},
        "files": {p.name: file_sha(p) for p in (OUT_DIR / "queries.parquet", OUT_DIR / "pairs.parquet")},
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False, default=str))
    print(json.dumps({k: manifest[k] for k in ("sizes", "natural_distractors", "pct_target_outside_clue_date_range", "checks")},
                     indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
