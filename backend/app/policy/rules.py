"""Reglas R1–R6 (docs/policies.md). Cada regla es una función pura con id que devuelve un RuleResult
con la evidencia usada; la decisión registra todas las reglas evaluadas.

⚠ SUPUESTOS DEL EQUIPO (P-14): no son políticas oficiales del banco ni del reto.

Orden: R4 y R5 son restricciones permanentes (R4 la aplica el controlador con el token; R5, los
textos). Luego R2 → R3 → R1 → R6; el primer resultado distinto de `permitir` decide.
R6 (riesgo), acordado el 2026-09-30:
- banda alta → escalar al equipo de fraude y recomendar bloquear la tarjeta;
- banda desconocida (sin fraud_score) NO cuenta como baja: en cargo_no_reconocido se ofrece el
  bloqueo, y si además el monto supera el umbral de autoservicio, se escala;
- banda media → se ofrece el bloqueo como opción; no obliga a escalar;
- banda baja → sin efecto.
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from backend.app.ml.base import RiskAssessment

CONFIG_FILE = Path(__file__).resolve().parents[2] / "config" / "policy.toml"

PERMITIR, INFORMAR, DENEGAR, ESCALAR = "permitir", "informar", "denegar", "escalar"


@dataclass(frozen=True)
class PolicyConfig:
    dispute_window_days: int = 60
    search_window_days: int = 120
    self_service_max_usd: Decimal = Decimal("500")
    max_clarify_rounds: int = 3
    confirmation_token_ttl_seconds: int = 300
    list_default_days: int = 30
    list_max_results: int = 50


def load_policy_config(env: dict[str, str] | None = None, path: Path = CONFIG_FILE) -> PolicyConfig:
    env = dict(os.environ if env is None else env)
    cfg = tomllib.loads(path.read_text(encoding="utf-8"))
    get = lambda k: env.get(k.upper()) or cfg[k]
    return PolicyConfig(dispute_window_days=int(get("dispute_window_days")), search_window_days=int(get("search_window_days")),
                        self_service_max_usd=Decimal(str(get("self_service_max_usd"))),
                        max_clarify_rounds=int(get("max_clarify_rounds")),
                        confirmation_token_ttl_seconds=int(get("confirmation_token_ttl_seconds")),
                        list_default_days=int(get("list_default_days")), list_max_results=int(get("list_max_results")))


@dataclass(frozen=True)
class RuleResult:
    id: str
    resultado: str
    motivo: str
    evidencia: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PolicyDecision:
    outcome: str                                  # permitir | informar | escalar
    rules: tuple[RuleResult, ...]
    decisive: RuleResult | None                   # la regla que decidió (None si todo permite)
    notice_code: str | None = None                # pending_transaction, existing_case, …
    handoff_reason: str | None = None
    handoff_queue: str | None = None
    offer_lock: bool = False                      # ofrecer bloqueo como opción
    recommend_lock: bool = False                  # recomendar bloqueo (banda alta)

    def rules_dicts(self) -> list[dict]:
        return [r.as_dict() for r in self.rules]


def _day(d) -> date:
    return d.date() if hasattr(d, "date") else d


def r2_status(tx: dict) -> RuleResult:
    """R2: Pending es informativo. Supuesto (P-23): Declined y Reversed también, no hay cargo vigente."""
    st = tx["transaction_status"]
    if st == "Pending":
        return RuleResult("R2", INFORMAR, "cargo_pendiente", {"estado": st})
    if st in ("Declined", "Reversed"):
        return RuleResult("R2", INFORMAR, "sin_cargo_vigente", {"estado": st})
    return RuleResult("R2", PERMITIR, "cargo_procesado", {"estado": st})


def r3_existing_case(case: dict | None) -> RuleResult:
    """R3: no duplicar reclamos abiertos sobre la misma transacción."""
    if case:
        return RuleResult("R3", INFORMAR, "reclamo_existente", {"case_id": case["case_id"], "estado": case["status"]})
    return RuleResult("R3", PERMITIR, "sin_reclamo_previo", {})


def r1_window(tx: dict, session_date: date, max_days: int) -> RuleResult:
    """R1: reclamo automático solo si el cargo tiene <= max_days días (contra transaction_date)."""
    days = (session_date - _day(tx["transaction_date"])).days
    if days > max_days:
        return RuleResult("R1", ESCALAR, "fuera_de_plazo", {"dias": days, "limite": max_days})
    return RuleResult("R1", PERMITIR, "dentro_de_plazo", {"dias": days, "limite": max_days})


def r6_risk(risk: RiskAssessment, reason_code: str, amount_usd: Decimal | None, cfg: PolicyConfig) -> tuple[RuleResult, dict]:
    """R6 con bandas. Devuelve la regla y los efectos (cola, bloqueo ofrecido o recomendado)."""
    ev = {"banda": risk.band, "probabilidad": risk.probability, "score_faltante": risk.probability is None,
          "umbral": risk.threshold, "modelo": risk.version, "monto_usd": str(amount_usd) if amount_usd is not None else None}
    if risk.band == "alto":
        return RuleResult("R6", ESCALAR, "riesgo_alto", ev), {"queue": "fraude", "recommend_lock": True}
    if risk.band == "desconocido" and reason_code == "unrecognized":
        ev["umbral_autoservicio_usd"] = str(cfg.self_service_max_usd)
        if amount_usd is None or amount_usd > cfg.self_service_max_usd:
            return RuleResult("R6", ESCALAR, "riesgo_desconocido_monto_alto", ev), {"queue": "fraude", "offer_lock": True}
        return RuleResult("R6", PERMITIR, "riesgo_desconocido_ofrecer_bloqueo", ev), {"offer_lock": True}
    if risk.band == "medio":
        return RuleResult("R6", PERMITIR, "riesgo_medio_ofrecer_bloqueo", ev), {"offer_lock": True}
    return RuleResult("R6", PERMITIR, f"riesgo_{risk.band}", ev), {}


def r4_constant() -> RuleResult:
    return RuleResult("R4", PERMITIR, "requiere_confirmation_token", {"nota": "se valida al ejecutar"})


def r5_constant(refund_requested: bool) -> RuleResult:
    return RuleResult("R5", INFORMAR if refund_requested else PERMITIR,
                      "no_se_aprueban_devoluciones" if refund_requested else "sin_pedido_de_devolucion", {})


def evaluate_dispute(tx: dict, session_date: date, existing_case: dict | None, risk: RiskAssessment, reason_code: str,
                     cfg: PolicyConfig, refund_requested: bool = False) -> PolicyDecision:
    """Evalúa si se puede registrar un reclamo sobre `tx` (ya confirmada por el cliente y del propio cliente)."""
    amount_usd = Decimal(str(tx["amount_usd_filled"])) if tx.get("amount_usd_filled") is not None else None
    r6, effects = r6_risk(risk, reason_code, amount_usd, cfg)
    ordered = [r2_status(tx), r3_existing_case(existing_case), r1_window(tx, session_date, cfg.dispute_window_days), r6]
    rules = (r4_constant(), r5_constant(refund_requested), *ordered)
    decisive = next((r for r in ordered if r.resultado != PERMITIR), None)
    if decisive is None:
        return PolicyDecision(PERMITIR, rules, None, offer_lock=bool(effects.get("offer_lock")))
    if decisive.resultado == INFORMAR:
        code = {"cargo_pendiente": "pending_transaction", "sin_cargo_vigente": "no_active_charge",
                "reclamo_existente": "existing_case"}[decisive.motivo]
        return PolicyDecision(INFORMAR, rules, decisive, notice_code=code)
    reason = {"fuera_de_plazo": "fuera_de_plazo", "riesgo_alto": "riesgo_alto",
              "riesgo_desconocido_monto_alto": "riesgo_desconocido"}[decisive.motivo]
    queue = effects.get("queue") if decisive.id == "R6" else "disputas"
    return PolicyDecision(ESCALAR, rules, decisive, handoff_reason=reason, handoff_queue=queue,
                          offer_lock=bool(effects.get("offer_lock")) if decisive.id == "R6" else False,
                          recommend_lock=bool(effects.get("recommend_lock")) if decisive.id == "R6" else False)


HANDOFF_PRIORITY = {"riesgo_alto": "alta", "acceso_no_autorizado": "alta", "riesgo_desconocido": "alta"}  # P-28
HANDOFF_QUEUE = {"riesgo_alto": "fraude", "riesgo_desconocido": "fraude", "reposicion_tarjeta": "tarjetas",
                 "fuera_de_plazo": "disputas", "aclaracion_agotada": "disputas", "accion_no_verificada": "disputas"}


def handoff_priority(reason: str) -> str:
    return HANDOFF_PRIORITY.get(reason, "media")


def handoff_queue(reason: str) -> str:
    return HANDOFF_QUEUE.get(reason, "general")
