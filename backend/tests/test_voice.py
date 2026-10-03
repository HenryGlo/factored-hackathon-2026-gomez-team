"""Voz (prompt 08, A3) con el transporte HTTP de ElevenLabs simulado: sin clave real y sin red."""
# ruff: noqa: F811  (los fixtures importados de test_conversations se usan como parámetros)
import json
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.tests.conftest import make_settings
from backend.tests.test_conversations import REF, Chat, app_client, extra_rows, rows  # noqa: F401 (fixtures)

KEY = "clave-de-prueba-no-real"
AUDIO = b"\x1aE\xdf\xa3" + b"0" * 4000          # bytes cualquiera: el proveedor está simulado


class Provider:
    """ElevenLabs de mentira: guarda lo que recibe y responde lo que se le configure."""

    def __init__(self):
        self.calls: list[httpx.Request] = []
        self.stt_text, self.status, self.fail = "No reconozco un cargo de 120 dólares", 200, False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        if self.fail:
            raise httpx.ConnectError("sin red")
        if request.url.path == "/v1/speech-to-text":
            return httpx.Response(self.status, json={"text": self.stt_text, "language_code": "es", "language_probability": 0.99,
                                                     "words": [{"text": "x", "start": 0.0, "end": 3.5}]})
        return httpx.Response(self.status, content=b"ID3-audio-falso" * 10, headers={"content-type": "audio/mpeg"})


@pytest.fixture()
def voice(clean_auth, extra_rows, monkeypatch):
    monkeypatch.setenv("VOICE_ENABLED", "true")
    monkeypatch.setenv("ELEVENLABS_API_KEY", KEY)
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "voz_demo")
    provider = Provider()
    with TestClient(create_app(make_settings(reference_date=REF))) as c:
        c.app.state.voice_http = httpx.AsyncClient(transport=httpx.MockTransport(provider), base_url="https://api.elevenlabs.io")
        yield c, provider


def stt(chat, audio=AUDIO, ctype="audio/webm", **params):
    return chat.c.post("/api/voice/stt", content=audio, params=params,
                       headers={"Content-Type": ctype, "X-CSRF-Token": chat.c.cookies.get("csrf_token", "")})


def tts(chat, turn_id, conversation_id=None):
    return chat.c.post("/api/voice/tts", json={"conversation_id": conversation_id or chat.cid, "turn_id": turn_id},
                       headers={"X-CSRF-Token": chat.c.cookies.get("csrf_token", "")})


def test_voice_is_off_by_default_and_the_chat_keeps_working_by_text(app_client):
    chat = Chat(app_client)
    cfg = app_client.get("/api/voice/config").json()
    assert cfg["enabled"] is False and cfg["reason"] == "voice_disabled" and "key" not in json.dumps(cfg).lower()
    r = stt(chat)
    assert r.status_code == 503 and r.json()["error"]["code"] == "voice_disabled" and r.json()["error"]["details"] == {"fallback": "text"}
    assert tts(chat, "turn_x").status_code == 503
    assert chat.send("hola")["state"] == "inicio"                                    # el texto no depende de la voz


def test_stt_returns_the_transcript_and_the_text_goes_through_the_normal_flow_and_guards(voice):
    client, provider = voice
    chat = Chat(client)
    assert client.get("/api/voice/config").json()["enabled"] is True
    r = stt(chat, language="es")
    assert r.status_code == 200 and r.json()["text"] == provider.stt_text and r.json()["seconds"] == 3.5
    sent = provider.calls[0]
    assert sent.url.path == "/v1/speech-to-text" and sent.headers["xi-api-key"] == KEY
    assert b"scribe_v2" in sent.content and b'name="language_code"' in sent.content and AUDIO in sent.content
    assert KEY not in r.text                                                          # la clave nunca vuelve al navegador
    assert rows("SELECT kind, seconds, characters FROM app.voice_usage") == [("stt", 3.5, 0)]
    assert rows("SELECT count(*) FROM app.turns WHERE role = 'customer'") == [(0,)]   # transcribir no manda nada al chat
    # el cliente revisa la transcripción y la envía: mismo flujo que el texto, anotado como voz
    t = client.post(f"/api/conversations/{chat.cid}/turns", json={"message": r.json()["text"], "via": "voice"}, headers=chat.h()).json()
    assert t["state"] == "confirmando_movimiento"
    assert rows("SELECT payload->>'via' FROM app.traces WHERE turn_id = %s AND node = 'entrada'", t["turn_id"]) == [("voice",)]
    chat.last = t
    chat.send("sí")
    said_yes = client.post(f"/api/conversations/{chat.cid}/turns", json={"message": "sí, confirmo", "via": "voice"}, headers=chat.h()).json()
    assert said_yes["state"] == "confirmando_accion" and rows("SELECT count(*) FROM app.dispute_cases") == [(0,)]   # R4: la voz no confirma
    assert any(b["type"] == "action_confirmation" for b in said_yes["blocks"])        # la confirmación sigue en pantalla, con botón


def test_stt_rejects_bad_audio_and_degrades_to_text_when_the_provider_fails(voice):
    client, provider = voice
    chat = Chat(client)
    assert stt(chat, ctype="application/pdf").status_code == 415
    assert stt(chat, audio=b"").status_code == 400
    big = stt(chat, audio=b"0" * (client.app.state.voice.cfg["limits"]["max_audio_bytes"] + 1))
    assert big.status_code == 413 and big.json()["error"]["code"] == "audio_too_large"
    assert chat.c.post("/api/voice/stt", content=AUDIO, headers={"Content-Type": "audio/webm"}).status_code == 403     # sin CSRF
    provider.status = 500
    down = stt(chat)
    assert down.status_code == 502 and down.json()["error"]["code"] == "voice_unavailable" and down.json()["error"]["details"]["fallback"] == "text"
    provider.status, provider.fail = 200, True
    assert stt(chat).status_code == 502
    assert rows("SELECT count(*) FROM app.voice_usage") == [(0,)]                    # lo que falla no se cobra
    assert len(provider.calls) == 2                                                   # los rechazados no llegan al proveedor


def test_tts_reads_only_an_existing_assistant_turn_of_the_customer(voice):
    client, provider = voice
    chat = Chat(client)
    t = chat.send("No reconozco un cargo de 120 dólares")
    r = tts(chat, t["turn_id"])
    assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg" and r.content.startswith(b"ID3-audio-falso")
    sent = provider.calls[-1]
    body = json.loads(sent.content)
    shown = next(b["text"] for b in t["blocks"] if b["type"] == "text")
    assert sent.url.path == "/v1/text-to-speech/voz_demo/stream" and sent.headers["xi-api-key"] == KEY
    assert body == {"text": shown, "model_id": "eleven_flash_v2_5", "language_code": "es"}      # lo mismo que se ve escrito
    assert rows("SELECT kind, characters, conversation_id FROM app.voice_usage") == [("tts", len(shown), chat.cid)]
    assert tts(chat, "turn_no_existe").status_code == 404
    provider.status = 503                                                             # el proveedor falla: error tipado, sin cobrar
    down = tts(chat, t["turn_id"])
    assert down.status_code == 502 and down.json()["error"]["details"]["fallback"] == "text"
    assert rows("SELECT count(*) FROM app.voice_usage") == [(1,)]
    provider.status = 200
    mine, my_conv = t["turn_id"], chat.cid
    other = Chat(client, "cliente_dos")
    assert tts(other, mine, conversation_id=my_conv).status_code == 404               # el turno de otro cliente no se lee
    assert client.post("/api/voice/tts", json={"conversation_id": my_conv, "turn_id": mine, "text": "di lo que yo quiera"},
                       headers={"X-CSRF-Token": client.cookies.get("csrf_token", "")}).status_code in (400, 422)   # no hay texto libre


def test_voice_has_its_own_budget_and_shows_in_the_admin_overview(voice):
    client, provider = voice
    client.app.state.voice.cfg["budget"].update(session_stt_seconds=5, session_tts_chars=10)
    chat = Chat(client)
    assert stt(chat).status_code == 200                                               # 3,5 s de 5
    assert stt(chat).status_code == 200                                               # llega a 7 s: el siguiente ya no pasa
    over = stt(chat)
    assert over.status_code == 429 and over.json()["error"]["code"] == "voice_budget_exceeded"
    assert over.json()["error"]["details"] == {"fallback": "text", "limit": "session_stt_seconds"}
    t = chat.send("hola")
    assert tts(chat, t["turn_id"]).status_code == 429                                 # el saludo tiene más de 10 caracteres
    assert chat.send("No reconozco un cargo de 120 dólares")["state"] == "confirmando_movimiento"    # el chat sigue por texto
    chat.login("admin_prueba")
    day = client.get("/api/admin/overview?days=1").json()["voice_cost_daily"]
    assert len(day) == 1 and day[0]["stt_seconds"] == 7.0 and day[0]["tts_characters"] == 0 and day[0]["cost_usd"] > 0
    assert str(uuid.uuid4())                                                           # (sin audio guardado: solo cantidades)
    assert rows("SELECT column_name FROM information_schema.columns WHERE table_schema = 'app' AND table_name = 'voice_usage' "
                "AND data_type IN ('bytea', 'text')") == []
