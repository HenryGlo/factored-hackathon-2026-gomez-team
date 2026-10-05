"""Simulación de umbrales de política: qué habría decidido la política con otros valores, sobre decisiones ya tomadas.

Cada evaluación de política deja en la traza las reglas con su evidencia (días del cargo, probabilidad de riesgo, monto).
Con esa evidencia se puede volver a decidir con otro plazo (R1), otro umbral de riesgo o otro tope de autoservicio (R6) sin
correr nada ni tocar datos. Las reglas R2 (estado del cargo), R3 (reclamo existente), R4 y R5 no dependen de un umbral.

Es una simulación de la DECISIÓN, no del resultado completo: no sabe si el cliente habría confirmado, ni incluye las
conversaciones que no llegaron a evaluar la política. No cambia ninguna configuración: aplicar un valor nuevo sigue siendo
un cambio de `backend/config/*.toml`, medido con el harness y revisado por una persona.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from backend.app.policy.rules import ESCALAR, INFORMAR, PERMITIR  # noqa: F401

ORDER = ("R2b", "R2", "R3", "R1", "R6")          # el primer resultado distinto de permitir decide (rules.evaluate_dispute)


@dataclass(frozen=True)
class Thresholds:
    dispute_window_days: int
    risk_threshold: float
    self_service_max_usd: Decimal

    def as_dict(self) -> dict:
        return {"dispute_window_days": self.dispute_window_days, "risk_threshold": self.risk_threshold,
                "self_service_max_usd": float(self.self_service_max_usd)}


def _decimal(v) -> Decimal | None:
    try:
        return Decimal(str(v)) if v is not None else None
    except InvalidOperation:
        return None


def rule_result(rule: dict, t: Thresholds) -> str:
    """Resultado de una regla guardada con los umbrales `t`. Sin la evidencia necesaria, se conserva el resultado guardado."""
    ev = rule.get("evidencia") or {}
    if rule.get("id") == "R1" and isinstance(ev.get("dias"), (int, float)):
        return ESCALAR if ev["dias"] > t.dispute_window_days else PERMITIR
    if rule.get("id") == "R6":
        p = ev.get("probabilidad")
        if isinstance(p, (int, float)):
            return ESCALAR if p >= t.risk_threshold else PERMITIR
        if str(rule.get("motivo", "")).startswith("riesgo_desconocido_"):      # sin score, en un cargo no reconocido
            amount = _decimal(ev.get("monto_usd"))
            return ESCALAR if amount is None or amount > t.self_service_max_usd else PERMITIR
    return str(rule.get("resultado") or PERMITIR)


def reevaluate(rules: list[dict], t: Thresholds) -> tuple[str, str | None]:
    """(resultado, regla decisiva) de una evaluación guardada, con los umbrales `t`."""
    by_id = {r.get("id"): r for r in rules or []}
    for rid in ORDER:
        if rid in by_id:
            res = rule_result(by_id[rid], t)
            if res != PERMITIR:
                return res, rid
    return PERMITIR, None


def simulate(evaluations: list[list[dict]], current: Thresholds, proposed: Thresholds) -> dict:
    """Compara las decisiones con los umbrales actuales y con los propuestos sobre las mismas evaluaciones."""
    before: dict[str, int] = {PERMITIR: 0, INFORMAR: 0, ESCALAR: 0}
    after = dict(before)
    changes: dict[tuple[str, str, str], int] = {}
    for rules in evaluations:
        b, b_rule = reevaluate(rules, current)
        a, a_rule = reevaluate(rules, proposed)
        before[b] = before.get(b, 0) + 1
        after[a] = after.get(a, 0) + 1
        if a != b:
            key = (b, a, a_rule or b_rule or "—")
            changes[key] = changes.get(key, 0) + 1
    return {"evaluated": len(evaluations), "before": before, "after": after,
            "changes": [{"from": f, "to": to, "rule": rule, "n": n} for (f, to, rule), n in sorted(changes.items(), key=lambda x: -x[1])]}
