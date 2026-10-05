"""Simulación de umbrales (sobre la evidencia guardada de cada regla) y temas de mensajes sin texto de clientes."""
from decimal import Decimal

from backend.app.ml.topics import normalize, topic_clusters
from backend.app.policy.simulate import Thresholds, reevaluate, simulate

NOW = Thresholds(dispute_window_days=60, risk_threshold=0.5, self_service_max_usd=Decimal("500"))


def rules(days=10, p=0.01, amount="100.00", missing=False, r2="permitir", r3="permitir"):
    r6 = ({"id": "R6", "resultado": "permitir", "motivo": "riesgo_desconocido_ofrecer_bloqueo", "evidencia": {"probabilidad": None, "score_faltante": True, "monto_usd": amount}}
          if missing else {"id": "R6", "resultado": "permitir", "motivo": "riesgo_bajo", "evidencia": {"probabilidad": p, "score_faltante": False, "monto_usd": amount}})
    return [{"id": "R4", "resultado": "permitir", "motivo": "requiere_confirmation_token", "evidencia": {}},
            {"id": "R5", "resultado": "permitir", "motivo": "sin_pedido_de_devolucion", "evidencia": {}},
            {"id": "R2", "resultado": r2, "motivo": "cargo_procesado", "evidencia": {"estado": "Approved"}},
            {"id": "R3", "resultado": r3, "motivo": "sin_reclamo_previo", "evidencia": {}},
            {"id": "R1", "resultado": "permitir", "motivo": "dentro_de_plazo", "evidencia": {"dias": days, "limite": 60}}, r6]


def test_reevaluate_matches_the_policy_order_and_thresholds():
    assert reevaluate(rules(), NOW) == ("permitir", None)
    assert reevaluate(rules(days=61), NOW) == ("escalar", "R1")
    assert reevaluate(rules(days=60), NOW) == ("permitir", None)                              # <= plazo: dentro
    assert reevaluate(rules(p=0.5), NOW) == ("escalar", "R6")                                 # >= umbral: alto
    assert reevaluate(rules(missing=True, amount="500.00"), NOW) == ("permitir", None)
    assert reevaluate(rules(missing=True, amount="500.01"), NOW) == ("escalar", "R6")
    assert reevaluate(rules(days=90, r2="informar"), NOW) == ("informar", "R2")              # R2 decide antes que R1
    assert reevaluate(rules(days=90, p=0.9, r3="informar"), NOW) == ("informar", "R3")       # un umbral no cambia R2 ni R3
    assert reevaluate([], NOW) == ("permitir", None)


def test_simulation_counts_what_changes_and_which_rule_decides():
    evals = [rules(days=d) for d in (5, 20, 40, 50, 70)] + [rules(p=p) for p in (0.1, 0.3, 0.45, 0.6)] + [rules(missing=True, amount="400")]
    out = simulate(evals, NOW, Thresholds(dispute_window_days=30, risk_threshold=0.4, self_service_max_usd=Decimal("300")))
    assert out["evaluated"] == 10 and out["before"] == {"permitir": 8, "informar": 0, "escalar": 2}
    assert out["after"] == {"permitir": 4, "informar": 0, "escalar": 6}
    assert {(c["from"], c["to"], c["rule"]): c["n"] for c in out["changes"]} == {("permitir", "escalar", "R1"): 2, ("permitir", "escalar", "R6"): 2}
    relaxed = simulate(evals, NOW, Thresholds(dispute_window_days=90, risk_threshold=0.7, self_service_max_usd=Decimal("500")))
    assert relaxed["after"]["escalar"] == 0 and sum(c["n"] for c in relaxed["changes"]) == 2
    assert simulate(evals, NOW, NOW)["changes"] == []


def test_topics_group_messages_without_returning_any_message_or_rare_term():
    loans = [f"quiero pedir un préstamo de {1000 + i} para mi casa" for i in range(12)]
    pins = [f"necesito cambiar el PIN de mi tarjeta {i}" for i in range(12)]
    rare = ["mi vecino Anacleto Zurbarán me debe 77 pesos"]
    out = topic_clusters(loans + pins + rare, min_group=5)
    assert out["messages"] == 25 and len(out["clusters"]) == 2
    terms = [" ".join(c["terms"]) for c in out["clusters"]]
    assert any("prestamo" in t for t in terms) and any("pin" in t for t in terms)
    flat = str(out)
    assert "anacleto" not in flat and "zurbaran" not in flat and "77" not in flat and "1000" not in flat   # ni frases raras ni números
    assert all(c["size"] >= 5 for c in out["clusters"]) and out["unclustered"] == 25 - sum(c["size"] for c in out["clusters"])
    assert topic_clusters(loans[:6], min_group=5) == {"messages": 6, "clusters": [], "unclustered": 6}      # muy pocos: nada


def test_normalize_drops_numbers_accents_and_stopwords():
    assert normalize("Hola, ¿CUÁNTO es la tasa del CDT a 90 días? Não sei") == "cuanto tasa cdt sei"
    assert normalize("año señor 12345 TRX-99 del cliente CLI-ZZZZ9999ZZZZ, ref ATN_ABCDEF") == "año señor cliente ref"   # sin identificadores
