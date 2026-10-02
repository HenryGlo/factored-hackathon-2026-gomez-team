"""Revisión del 2026-10-02 (prompt 11): pedir un dato antes de buscar, mostrar solo lo que coincide, decir cuando no hay
coincidencias y no mandar fuera de alcance un reclamo con errores de tipeo."""
from __future__ import annotations

import pytest

from backend.app.ml import keyword_rules as K
from backend.app.ml.base import RankQuery
from backend.app.ml.ranker import RuleRanker, brands, given_criteria, matched_criteria
from backend.tests.test_conversations import Chat, app_client, extra_rows  # noqa: F401  (fixtures)


# ---------------------------------------------------------------- B1: tipeo y costo asimétrico
@pytest.mark.parametrize("text", ["Hola, tengo un cargo n oreconocido en Facebook", "noo reconosco este cobro", "Tengo un cargo no reconocido",
                                  "nao reconhecoo essa cobranca", "tengo un cobro que desconosco", "ese cargo no lo reconozco"])
def test_typos_still_classify_as_an_unrecognized_charge(text):
    assert K.dispute_signal(text) and K.classify(text)["intent"] == "cargo_no_reconocido"


@pytest.mark.parametrize("text", ["quiero un préstamo para comprar un carro", "cuéntame un chiste", "¿qué tasa tiene un CDT?", "hola"])
def test_real_out_of_scope_or_empty_messages_have_no_dispute_signal(text):
    assert not K.dispute_signal(text)


def test_banking_words_and_explicit_out_of_scope_topics():
    assert K.mentions_banking("tengo un cargoo raro") and K.mentions_banking("algo pasó en Netflix") and not K.mentions_banking("cuéntame un chiste")
    assert K.out_of_scope_topic("quiero subir el cupo de mi tarjeta") == "cupo" and K.out_of_scope_topic("tengo un cargo raro") is None


def test_typo_message_from_the_review_never_goes_out_of_scope(app_client):  # noqa: F811
    chat = Chat(app_client)
    chat.send("Hola, tengo un cargo n oreconocido en Facebook")
    codes = [b.get("code") for b in chat.last["blocks"] if b["type"] == "notice"]
    assert "out_of_scope" not in codes and codes == ["no_match"] and chat.state == "aclarando"


def test_banking_mention_without_a_clear_request_is_clarified_not_sent_away(app_client):  # noqa: F811
    chat = Chat(app_client)
    chat.send("tengo un cargoo raro en mi tarjta")
    assert not [b for b in chat.last["blocks"] if b.get("code") == "out_of_scope"] and chat.state in ("inicio", "aclarando")


def test_explicit_other_topic_is_still_out_of_scope(app_client):  # noqa: F811
    chat = Chat(app_client)
    chat.send("quiero subir el cupo de mi tarjeta")
    assert [b for b in chat.last["blocks"] if b.get("code") == "out_of_scope"]


# ---------------------------------------------------------------- B2: sin referencias, primero preguntar
def test_without_amount_merchant_or_date_it_asks_and_shows_no_movements(app_client):  # noqa: F811
    chat = Chat(app_client)
    t = chat.send("No reconozco un cargo")
    kinds = [b["type"] for b in t["blocks"]]
    assert kinds == ["notice", "quick_replies"] and t["blocks"][0]["code"] == "need_detail"
    assert t["blocks"][0]["text"].startswith("Claro, te ayudo. ¿Me das algún dato del cargo")
    actions = [o["action"] for o in t["blocks"][1]["options"]]
    assert actions == [{"type": "start_topic", "topic": "consulta_movimientos"}, {"type": "request_human"}]
    assert chat.state == "aclarando"


def test_view_movements_option_lists_them_without_calling_them_similar(app_client):  # noqa: F811
    chat = Chat(app_client)
    chat.send("No reconozco un cargo")
    t = chat.send(type="start_topic", topic="consulta_movimientos")
    assert t["blocks"][0]["text"] == "Estos son tus últimos movimientos. ¿Cuál no reconoces?"
    listing = chat.block("transaction_list")
    assert listing["can_dispute"] and listing["transactions"] and chat.state == "inicio"
    assert "parecid" not in " ".join(b.get("text", "") for b in t["blocks"]) and not chat.block("quick_replies")


def test_giving_a_detail_after_being_asked_finds_the_charge(app_client):  # noqa: F811
    chat = Chat(app_client)
    chat.send("No reconozco un cargo")
    chat.send("fue de 120 dólares")
    assert chat.block("transaction_card")["transaction"]["transaction_id"] == "FXT-T0101"


# ---------------------------------------------------------------- B3: relevancia mínima y honestidad
def test_unknown_merchant_says_so_with_the_data_date_and_offers_ways_out(app_client):  # noqa: F811
    chat = Chat(app_client)
    t = chat.send("Tengo un cargo no reconocido en Facebook")
    notice = t["blocks"][0]
    assert notice["code"] == "no_match" and notice["text"].startswith("No encontré cargos de Facebook en tus movimientos hasta el ")
    assert notice["criteria"] == {"merchant": "Facebook", "amount": None, "date": None} and notice["data_as_of"]
    assert not chat.block("candidate_list") and not chat.block("transaction_card")
    actions = [o["action"] for o in chat.block("quick_replies")["options"]]
    assert actions == [{"type": "start_topic", "topic": "cargo_no_reconocido"}, {"type": "start_topic", "topic": "consulta_movimientos"},
                       {"type": "request_human"}]
    again = chat.send(type="start_topic", topic="cargo_no_reconocido")           # "Darte otro dato"
    assert again["blocks"][0]["code"] == "need_detail" and chat.state == "aclarando"


def test_shown_candidates_match_what_the_customer_said_and_the_text_says_how(app_client):  # noqa: F811
    chat = Chat(app_client)
    chat.send("no reconozco un cargo de como 77 dólares en la farmacia")
    cands = chat.block("candidate_list")["candidates"]
    assert cands and all(abs(float(c["amount"]) - 77) / 77 <= 0.20 or "armacia" in (c.get("merchant_name") or c["label"]) for c in cands)
    assert "parecidos" not in chat.block("text")["text"]


def test_exhausted_attempts_hand_off_with_what_was_given_and_searched(app_client):  # noqa: F811
    chat = Chat(app_client)
    seen = [chat.send("Tengo un cargo no reconocido en Facebook")]
    for msg in ("fue en Facebook", "en Facebook, ya te dije", "Facebook"):
        seen.append(chat.send(msg))
    notice = chat.block("handoff_notice")
    assert notice["reason_code"] == "aclaracion_agotada"
    texts = " ".join(b.get("text", "") for t in seen for b in t["blocks"])
    assert "Intento" not in texts and " de 3" not in texts                       # sin contadores internos
    from backend.tests.test_conversations import rows
    questions = rows("SELECT payload->'open_questions' FROM app.handoffs WHERE handoff_id = %s", notice["handoff_id"])[0][0]
    assert any("comercio: Facebook" in q for q in questions) and any("coincidieron 0" in q for q in questions)


# ---------------------------------------------------------------- unidades del filtro
def test_matched_criteria_and_brand_aliases():
    tx = {"transaction_id": "t", "amount": "120.00", "currency": "USD", "merchant_name": "FACEBK *ADS", "transaction_date": __import__("datetime").datetime(2026, 6, 10),
          "transaction_status": "Approved"}
    ranker = RuleRanker()
    q = RankQuery(amount=None, currency=None, amount_approx=False, date_range=None, merchant_hint="Facebook", session_date=None)
    assert brands("meta platforms irl") == brands("fb") == frozenset({"Facebook"})
    assert given_criteria(q) == {"comercio"} and matched_criteria(q, ranker.features(q, tx)) == {"comercio"}
    other = {**tx, "merchant_name": "Restaurante El Buen Sabor"}
    assert matched_criteria(q, ranker.features(q, other)) == set()
    from decimal import Decimal
    qa = RankQuery(amount=Decimal("125"), currency=None, amount_approx=False, date_range=None, merchant_hint=None, session_date=None)
    assert matched_criteria(qa, ranker.features(qa, tx)) == {"monto"} and matched_criteria(qa, ranker.features(qa, {**tx, "amount": "300"})) == set()
