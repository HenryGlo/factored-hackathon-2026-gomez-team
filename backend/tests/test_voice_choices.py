"""Modo voz manos libres (opción A): elegir diciendo lo que se ve, y que el asistente lea las opciones. Confirmar sigue
exigiendo el botón (R4)."""
from __future__ import annotations

import pytest

from backend.app.controller.choices import pick_option, pick_shown
from backend.app.voice import speakable
from backend.tests.test_conversations import Chat, app_client, extra_rows  # noqa: F401  (fixtures)

VIEWS = [{"transaction_id": "a", "label": "Netflix", "merchant_name": "Netflix", "amount": "15.99"},
         {"transaction_id": "b", "label": "Super Ahorro", "merchant_name": "Super Ahorro", "amount": "120.00"},
         {"transaction_id": "c", "label": "Pago · Entretenimiento", "merchant_name": None, "amount": "1248.65"}]
OPTIONS = [{"label": "Darte otro dato", "action": {"type": "start_topic", "topic": "cargo_no_reconocido"}},
           {"label": "Ver mis últimos movimientos", "action": {"type": "start_topic", "topic": "consulta_movimientos"}},
           {"label": "Hablar con una persona", "action": {"type": "request_human"}}]


@pytest.mark.parametrize("said,tid", [("el primero", "a"), ("la segunda", "b"), ("el último", "c"), ("la tres", "c"), ("o segundo", "b"),
                                      ("el de Netflix", "a"), ("el del super ahorro", "b"), ("el de 120", "b"), ("ese de entretenimiento", "c")])
def test_pick_shown_by_position_name_or_amount(said, tid):
    assert pick_shown(said, VIEWS) == tid


@pytest.mark.parametrize("said", ["el primero de junio", "los dos", "todos", "No reconozco un cargo de 50 en Amazon", "sí"])
def test_pick_shown_ignores_dates_plurals_and_new_requests(said):
    assert pick_shown(said, VIEWS) is None


@pytest.mark.parametrize("said,action", [("ver mis movimientos", OPTIONS[1]["action"]), ("movimientos", OPTIONS[1]["action"]),
                                         ("una persona", OPTIONS[2]["action"]), ("otro dato", OPTIONS[0]["action"])])
def test_pick_option_by_its_name(said, action):
    assert pick_option(said, OPTIONS) == action


def test_pick_option_does_not_swallow_a_real_request():
    assert pick_option("no reconozco un cargo de 50 en Amazon", OPTIONS) is None


def test_spoken_text_reads_options_lists_and_reminds_the_button():
    said = speakable([{"type": "text", "text": "Encontré 2 cargos de cerca de 120,00 USD. ¿Cuál de ellos es?"},
                      {"type": "candidate_list", "candidates": [{"label": "Super Ahorro", "amount_label": "120,00 USD", "date_label": "8 jun 2026"},
                                                                {"label": "Netflix", "amount_label": "118,00 USD", "date_label": "2 jun 2026"}]},
                      {"type": "quick_replies", "options": [{"label": "Ver mis últimos movimientos"}, {"label": "Hablar con una persona"}]}], "es")
    assert "La primera: Super Ahorro, 120,00 USD, 8 jun 2026." in said and "La segunda: Netflix" in said
    assert "Puedes decir: Ver mis últimos movimientos o Hablar con una persona." in said
    confirm = speakable([{"type": "action_confirmation", "summary": "Voy a registrar un reclamo."}], "pt")
    assert confirm.endswith("Para confirmar, toque no botão Confirmar na tela.")


def test_saying_the_option_name_after_being_asked_for_a_detail(app_client):  # noqa: F811
    chat = Chat(app_client)
    chat.send("No reconozco un cargo")
    t = chat.send("ver mis movimientos")                                     # dicho, no tocado
    assert t["blocks"][0]["text"] == "Estos son tus últimos movimientos. ¿Cuál no reconoces?"


def test_choosing_a_candidate_by_voice_shows_it_to_confirm_but_never_confirms(app_client):  # noqa: F811
    chat = Chat(app_client)
    chat.send("no reconozco un cargo de como 77 dólares en la farmacia")
    cands = chat.block("candidate_list")["candidates"]
    chat.send("la segunda")
    assert chat.block("transaction_card")["transaction"]["transaction_id"] == cands[1]["transaction_id"]
    chat.send("sí")
    assert chat.state == "confirmando_accion"
    chat.send("sí, confirmo")                                                # R4: el texto (o la voz) no confirma
    assert chat.state == "confirmando_accion" and chat.block("action_confirmation") and not chat.block("result")
