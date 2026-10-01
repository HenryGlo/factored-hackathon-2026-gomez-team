"""Política de aclaración: decide si hay una candidata clara o hay que preguntar, y qué preguntar.

Pregunta si (cualquiera):
- sin_pistas: el cliente no dio monto ni comercio;
- empate_monto: más de una candidata dentro de ±amount_tolerance del monto dicho que además siga
  siendo compatible con las otras pistas (dentro del rango de fechas dicho; comercio parecido si lo
  dijo). Si el cliente dio el monto exacto (sin "como") y una sola candidata coincide al centavo, no
  hay empate: las demás quedan descartadas por el monto;
- baja_confianza: probabilidad de la primera < tau, o margen sobre la segunda < delta;
- tipo_problema: en cobro_indebido no se sabe si es monto de más o duplicado.
Con una sola candidata y pistas, no pregunta. Sin candidatas, no hay nada que aclarar aquí
(el controlador decide qué hacer).

El atributo discriminante es el que mejor separa a las candidatas que se van a mostrar.
"""
from __future__ import annotations

from decimal import Decimal

from backend.app.ml.base import ClarifyDecision, ClarifyPolicy, RankQuery, RankResult
from backend.app.ml.ranker import _day


class ThresholdClarifyPolicy(ClarifyPolicy):
    implementation = "threshold"
    version = "threshold@v2"
    MERCHANT_MIN = 0.6

    def __init__(self, tau: float = 0.60, delta: float = 0.20, amount_tolerance: float = 0.10, max_show: int = 3):
        self.tau, self.delta, self.tol, self.max_show = tau, delta, Decimal(str(amount_tolerance)), max_show

    def decide(self, query: RankQuery, ranked: RankResult, problem_known: bool = True) -> ClarifyDecision:
        c = ranked.candidates
        if not c:
            return ClarifyDecision(False, ("sin_candidatas",), None, (), self.implementation, self.version)
        reasons = []
        if not problem_known:
            reasons.append("tipo_problema")
        if query.amount is None and not query.merchant_hint and len(c) > 1:
            reasons.append("sin_pistas")
        if query.amount is not None and query.amount > 0:
            tied = [s for s in c if abs(Decimal(str(s.transaction["amount"])) - query.amount) / query.amount <= self.tol
                    and s.features.get("date_days_out", 0) == 0
                    and (not query.merchant_hint or s.features.get("merchant_sim", 0) >= self.MERCHANT_MIN
                         or s.features.get("category_match", 0) == 1)]
            exact = [s for s in tied if s.features.get("amount_exact")]
            if len(tied) > 1 and not (not query.amount_approx and len(exact) == 1):
                reasons.append("empate_monto")
        top = c[0].probability
        second = c[1].probability if len(c) > 1 else 0.0
        if len(c) > 1 and (top < self.tau or top - second < self.delta):
            reasons.append("baja_confianza")
        if not reasons:
            return ClarifyDecision(False, ("clara",), None, (0,), self.implementation, self.version)
        show = tuple(range(min(self.max_show, len(c))))
        disc = "tipo_problema" if "tipo_problema" in reasons else self._discriminant(query, [c[i].transaction for i in show])
        return ClarifyDecision(True, tuple(reasons), disc, show, self.implementation, self.version)

    def _discriminant(self, q: RankQuery, txs: list[dict]) -> str:
        if len(txs) < 2:
            return "fecha"
        days = {_day(t["transaction_date"]) for t in txs}
        merchants = {(t.get("merchant_name") or t.get("transaction_category") or t.get("transaction_type")) for t in txs}
        amounts = [Decimal(str(t["amount"])) for t in txs]
        spread = (max(amounts) - min(amounts)) / max(min(amounts), Decimal("0.01"))
        # lo que el cliente NO dijo y además distingue a las candidatas
        if q.date_range is None and len(days) == len(txs):
            return "fecha"
        if not q.merchant_hint and len(merchants) == len(txs):
            return "comercio"
        if q.amount is None and spread > self.tol:
            return "monto"
        return "fecha" if len(days) > 1 else "comercio" if len(merchants) > 1 else "monto"
