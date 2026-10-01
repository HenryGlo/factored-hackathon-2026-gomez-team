"""Fase 4: política R1–R6 como funciones puras (supuestos del equipo)."""
from datetime import date, datetime
from decimal import Decimal

import pytest

from backend.app.ml.base import RiskAssessment
from backend.app.policy import rules as P

CFG = P.PolicyConfig()
TODAY = date(2026, 7, 5)


def tx(status="Approved", day=datetime(2026, 7, 1, 12), usd=Decimal("120")):
    return {"transaction_status": status, "transaction_date": day, "amount_usd_filled": usd}


def risk(band, p=None):
    return RiskAssessment(p, band, 0.70, "raw_fraud_score", "raw_fraud_score@v1")


def decide(t=None, case=None, band="bajo", reason="unrecognized", p=0.1, refund=False):
    return P.evaluate_dispute(t or tx(), TODAY, case, risk(band, None if band == "desconocido" else p), reason, CFG, refund)


def test_allow_when_everything_passes():
    d = decide()
    assert d.outcome == "permitir" and d.decisive is None and not d.offer_lock
    assert [r.id for r in d.rules] == ["R4", "R5", "R2", "R3", "R1", "R6"]


@pytest.mark.parametrize("status, notice", [("Pending", "pending_transaction"), ("Declined", "no_active_charge"),
                                            ("Reversed", "no_active_charge")])
def test_r2_informs(status, notice):
    d = decide(tx(status=status))
    assert (d.outcome, d.decisive.id, d.notice_code) == ("informar", "R2", notice)


def test_r3_existing_case_informs():
    d = decide(case={"case_id": "case_1", "status": "registrado"})
    assert (d.outcome, d.decisive.id, d.notice_code) == ("informar", "R3", "existing_case")


def test_r1_escalates_old_charges():
    d = decide(tx(day=datetime(2026, 4, 1, 12)))
    assert (d.outcome, d.decisive.id, d.handoff_reason, d.handoff_queue) == ("escalar", "R1", "fuera_de_plazo", "disputas")
    assert d.decisive.evidencia == {"dias": 95, "limite": 60}
    assert decide(tx(day=datetime(2026, 5, 6, 12))).outcome == "permitir"      # 60 días exactos


def test_r2_before_r1():
    assert decide(tx(status="Pending", day=datetime(2026, 1, 1))).decisive.id == "R2"


def test_r6_high_escalates_to_fraud_and_recommends_lock():
    d = decide(band="alto", p=0.85)
    assert (d.outcome, d.handoff_reason, d.handoff_queue, d.recommend_lock) == ("escalar", "riesgo_alto", "fraude", True)
    assert d.decisive.evidencia["banda"] == "alto" and d.decisive.evidencia["score_faltante"] is False


def test_r6_medium_offers_lock_without_handoff():
    d = decide(band="medio", p=0.4)
    assert d.outcome == "permitir" and d.offer_lock and not d.recommend_lock


def test_r6_unknown_is_not_low():
    d = decide(band="desconocido", t=tx(usd=Decimal("120")))
    assert d.outcome == "permitir" and d.offer_lock                                       # ofrece bloqueo
    assert next(r for r in d.rules if r.id == "R6").evidencia["score_faltante"] is True
    d = decide(band="desconocido", t=tx(usd=Decimal("900")))
    assert (d.outcome, d.handoff_reason, d.handoff_queue, d.offer_lock) == ("escalar", "riesgo_desconocido", "fraude", True)
    # en cobro_indebido (comercio reconocido) la falta de score no ofrece bloqueo
    assert not decide(band="desconocido", reason="duplicate").offer_lock


def test_r5_refund_request_is_recorded_but_does_not_block():
    d = decide(refund=True)
    assert d.outcome == "permitir" and next(r for r in d.rules if r.id == "R5").resultado == "informar"


def test_priority_and_queues():
    assert P.handoff_priority("riesgo_alto") == "alta" and P.handoff_priority("pide_humano") == "media"
    assert P.handoff_queue("reposicion_tarjeta") == "tarjetas" and P.handoff_queue("pide_humano") == "general"


def test_config_file_and_override():
    cfg = P.load_policy_config({})
    assert cfg.dispute_window_days == 60 and cfg.self_service_max_usd == Decimal("500") and cfg.max_clarify_rounds == 3
    assert P.load_policy_config({"SELF_SERVICE_MAX_USD": "100"}).self_service_max_usd == Decimal("100")
