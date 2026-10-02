"""Saludos repetidos (revisión en prodlike, 2026-10-02): el menú completo solo va al abrir la conversación; después el
asistente contesta corto, con calidez si le preguntan cómo está, sin repetir el mensaje anterior, y desde el segundo mensaje
seguido sin contenido ofrece las opciones como respuestas rápidas. Todo con plantillas, sin LLM."""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from backend.app.controller import blocks as B
from backend.app.controller.small_talk import asks_how_are_you, small_talk
from backend.app.main import create_app
from backend.tests.conftest import PASSWORD, make_settings


def h(c: TestClient) -> dict:
    return {"X-CSRF-Token": c.cookies["csrf_token"], "Idempotency-Key": str(uuid.uuid4())}


def start(c: TestClient, lang: str = "es") -> tuple[str, str]:
    c.get("/api/auth/csrf")
    assert c.post("/api/auth/login", json={"username": "cliente_uno", "password": PASSWORD}, headers=h(c)).status_code == 200
    r = c.post("/api/conversations", json={"language": lang}, headers=h(c)).json()
    return r["conversation_id"], r["blocks"][0]["text"]


def say(c: TestClient, conv: str, message: str) -> dict:
    r = c.post(f"/api/conversations/{conv}/turns", json={"message": message}, headers=h(c))
    assert r.status_code == 200, r.text
    return r.json()


def texts(resp: dict) -> str:
    return "\n".join(b["text"] for b in resp["blocks"] if b["type"] == "text")


def test_how_are_you_is_small_talk_in_es_and_pt():
    for phrase in ("Hola como estas", "¿Cómo estás?", "Oi, tudo bem?", "Tudo bem?", "hola que tal"):
        assert small_talk(phrase) and small_talk(phrase)[0] == "greeting" and asks_how_are_you(phrase)
    assert not asks_how_are_you("Hola") and small_talk("como estas, tengo un cobro de 120") is None


def test_repeated_greeting_never_repeats_the_menu_or_the_previous_message(clean_auth):
    with TestClient(create_app(make_settings())) as c:
        conv, opening = start(c)
        assert "Puedo ayudarte con" in opening                       # el menú completo va una vez, al abrir
        replies = [say(c, conv, "Hola como estas") for _ in range(3)]
        said = [texts(r) for r in replies]
        assert all("Puedo ayudarte con" not in s for s in said)       # no se repite el menú
        assert all(s in B.variants("es", "how_are_you") for s in said)
        assert said[0] != said[1] != said[2] and said[0] != opening   # nunca el mismo mensaje dos veces seguidas
        assert not [b for b in replies[0]["blocks"] if b["type"] == "quick_replies"]
        options = [b for b in replies[1]["blocks"] if b["type"] == "quick_replies"][0]["options"]   # 2.º sin contenido: opciones
        assert [o["action"].get("topic") for o in options][:4] == list(B.TOPICS) and options[-1]["action"] == {"type": "request_human"}
        assert all(r["state"] == "inicio" for r in replies)


def test_plain_greeting_after_the_opening_is_short_and_pt_has_its_own_variants(clean_auth):
    with TestClient(create_app(make_settings())) as c:
        conv, _ = start(c, "pt")
        first, second = say(c, conv, "Oi"), say(c, conv, "Tudo bem?")
        assert texts(first) in B.variants("pt", "greeting_short") and texts(second) in B.variants("pt", "how_are_you")


def test_topic_quick_reply_starts_that_flow_without_typing(clean_auth):
    with TestClient(create_app(make_settings())) as c:
        conv, _ = start(c)
        say(c, conv, "hola"), say(c, conv, "hola")
        r = c.post(f"/api/conversations/{conv}/turns", json={"action": {"type": "start_topic", "topic": "estado_reclamo"}}, headers=h(c))
        assert r.status_code == 200 and r.json()["state"] == "inicio" and texts(r.json())
        bad = c.post(f"/api/conversations/{conv}/turns", json={"action": {"type": "start_topic", "topic": "aprobar_reembolso"}}, headers=h(c))
        assert bad.status_code == 422                                  # solo los temas del contrato


def test_messages_without_a_request_never_get_the_same_reply_twice(clean_auth):
    """Sin contenido o fuera de alcance, tres veces seguidas: a la segunda ya no repite el texto, ofrece las opciones."""
    with TestClient(create_app(make_settings())) as c:
        conv, _ = start(c)
        first, second, third = say(c, conv, "asdf qwer"), say(c, conv, "asdf qwer"), say(c, conv, "asdf qwer")
        assert texts(first) != texts(second) != texts(third)
        assert texts(second) in B.variants("es", "pick_topic")
        options = [b for b in second["blocks"] if b["type"] == "quick_replies"][0]["options"]
        assert [o["action"].get("topic") for o in options][:4] == list(B.TOPICS)
