"""RuleRanker: ordena las transacciones del cliente según las pistas, sin entrenamiento.

Score escrito a mano (pesos fijados a priori, los mismos del RuleRanker de
ml/ranker/03_baselines.ipynb, que dio 98 % top-1 en validación con pistas simuladas) y softmax
por lista. Ver ADR-0002 y docs/ml/ranker-data-report.md.

    monto      4·exp(-dif_rel/0.10)  (+2 si el cliente dio el monto exacto y coincide)
    fecha      2.5·exp(-días_fuera_del_rango/3)
    recencia   0.5·exp(-días_desde_el_cargo/30)
    comercio   2·similitud (rapidfuzz) + 1 si coincide la categoría deducida de la pista
    moneda     0.5 si el cliente la dijo y coincide
    estado     −1.5 Declined, −1.0 Reversed (se muestran, pero es menos probable que sean el cargo)

Los montos se comparan con el monto original y, si el cliente dijo USD y el cargo es en otra
moneda, también con amount_usd_filled (se usa la diferencia menor).
"""
from __future__ import annotations

import json
import math
import re
from datetime import date, datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz

from backend.app.dates import normalize
from backend.app.ml.base import RankQuery, RankResult, Ranker, ScoredCandidate

ALIASES_FILE = Path(__file__).resolve().parents[3] / "ml" / "ranker" / "merchant_aliases.json"
STOP = {"un", "una", "el", "la", "los", "las", "de", "del", "en", "no", "na", "o", "a", "um", "uma", "que", "mi", "meu"}


@lru_cache
def category_keywords() -> dict[str, list[str]]:
    """palabra → categorías (léxico versionado del generador del ranker)."""
    return json.loads(ALIASES_FILE.read_text(encoding="utf-8"))["keywords"]["categories"]


def _norm(text: str | None) -> str:
    return " ".join(w for w in re.split(r"[^a-z0-9]+", normalize(text or "")) if w and w not in STOP)


def merchant_similarity(hint: str | None, merchant: str | None) -> float:
    a, b = _norm(hint), _norm(merchant)
    if not a or not b:
        return 0.0
    sim = fuzz.token_set_ratio(a, b)
    # partial_ratio sirve para descriptores pegados ("SUPERAHORRO*POS"), pero con pistas cortas da falsos
    # positivos ("uber" ~ "superahorro" = 75): solo se usa si la pista sin espacios tiene 6+ caracteres
    a_ns, b_ns = a.replace(" ", ""), b.replace(" ", "")
    if min(len(a_ns), len(b_ns)) >= 6:
        sim = max(sim, fuzz.partial_ratio(a_ns, b_ns))
    return sim / 100


def hint_categories(hint: str | None) -> set[str]:
    kw = category_keywords()
    return {c for tok in _norm(hint).split() for c in kw.get(tok, [])}


def _day(d) -> date:
    return d.date() if isinstance(d, datetime) else d


class RuleRanker(Ranker):
    implementation = "rule"
    version = "rule@v2"

    def __init__(self, temperature: float = 0.3, recency_days: float = 30):
        self.temperature, self.recency_days = temperature, recency_days

    def features(self, q: RankQuery, t: dict[str, Any]) -> dict[str, float]:
        f: dict[str, float] = {}
        amount = Decimal(str(t["amount"]))
        if q.amount is not None and q.amount > 0:
            rels = [abs(amount - q.amount) / q.amount]
            usd = t.get("amount_usd_filled")
            if q.currency == "USD" and t.get("currency") != "USD" and usd is not None:
                rels.append(abs(Decimal(str(usd)) - q.amount) / q.amount)
            f["amount_rel_diff"] = float(min(rels))
            f["amount_exact"] = float(min(rels) < Decimal("0.00005"))
        if q.date_range is not None:
            f["date_days_out"] = float(q.date_range.distance_days(_day(t["transaction_date"])))
        if q.session_date is not None:
            f["days_since"] = float(max((q.session_date - _day(t["transaction_date"])).days, 0))
        if q.merchant_hint:
            label = t.get("merchant_name") or t.get("merchant_category") or t.get("transaction_category") or ""
            f["merchant_sim"] = merchant_similarity(q.merchant_hint, label)
            cat = t.get("merchant_category") or t.get("transaction_category")
            f["category_match"] = float(bool(cat) and cat in hint_categories(q.merchant_hint))
        if q.currency:
            f["currency_match"] = float(q.currency == t.get("currency"))
        f["declined"] = float(t.get("transaction_status") == "Declined")
        f["reversed"] = float(t.get("transaction_status") == "Reversed")
        return f

    def score(self, q: RankQuery, f: dict[str, float]) -> float:
        s = 0.0
        if "amount_rel_diff" in f:
            s += 4.0 * math.exp(-f["amount_rel_diff"] / 0.10)
            if not q.amount_approx:
                s += 2.0 * f["amount_exact"]
        if "date_days_out" in f:
            s += 2.5 * math.exp(-f["date_days_out"] / 3.0)
        if "days_since" in f:
            s += 0.5 * math.exp(-f["days_since"] / self.recency_days)
        if "merchant_sim" in f:
            s += 2.0 * f["merchant_sim"] + 1.0 * f["category_match"]
        if "currency_match" in f:
            s += 0.5 * f["currency_match"]
        return s - 1.5 * f["declined"] - 1.0 * f["reversed"]

    def rank(self, query: RankQuery, transactions: list[dict[str, Any]]) -> RankResult:
        if not transactions:
            return RankResult([], self.implementation, self.version)
        feats = [self.features(query, t) for t in transactions]
        scores = [self.score(query, f) for f in feats]
        m = max(scores)
        exps = [math.exp((s - m) / self.temperature) for s in scores]
        z = sum(exps)
        # desempate estable: score, luego más reciente, luego id
        order = sorted(range(len(transactions)), key=lambda i: (-scores[i], -_day(transactions[i]["transaction_date"]).toordinal(),
                                                                 transactions[i]["transaction_id"]))
        out = [ScoredCandidate(transactions[i], round(scores[i], 4), exps[i] / z, r + 1, feats[i]) for r, i in enumerate(order)]
        return RankResult(out, self.implementation, self.version)


def duplicate_pairs(transactions: list[dict[str, Any]], max_days: int = 3) -> list[tuple[dict, dict]]:
    """Pares candidatos a cobro duplicado: mismo comercio (o categoría si no hay comercio), mismo monto
    y moneda, a lo sumo `max_days` días de diferencia. Para cobro_indebido con problema=duplicado."""
    pairs = []
    txs = sorted(transactions, key=lambda t: t["transaction_date"])
    for i, a in enumerate(txs):
        for b in txs[i + 1:]:
            if (_day(b["transaction_date"]) - _day(a["transaction_date"])).days > max_days:
                break
            key = lambda t: (t.get("merchant_name") or t.get("transaction_category") or t.get("transaction_type"),
                             Decimal(str(t["amount"])), t.get("currency"))
            if key(a) == key(b):
                pairs.append((a, b))
    return pairs
