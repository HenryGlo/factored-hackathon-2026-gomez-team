"""Cómo decidió el asistente: el detalle por turno es del agente con el ticket asignado; el administrador ve solo agregados."""
# ruff: noqa: F811  (app_client es un fixture importado de test_conversations)
import json

from backend.app.reasoning import GUARDRAILS, step_group, turn_reasoning
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.tests.conftest import admin, make_settings
from backend.tests.test_conversations import REF, Chat, _post, app_client, extra_rows  # noqa: F401  (fixtures)


def _risky_ticket(client) -> tuple[Chat, str]:
    chat = Chat(client)
    chat.send("no reconozco un cargo de 250 dólares")
    chat.send("sí")                                                       # riesgo alto → traspaso a fraude
    chat.login("analista_prueba")
    return chat, client.get("/api/tickets").json()["tickets"][0]["ticket_id"]


def test_reasoning_is_only_for_the_agent_who_holds_the_ticket(app_client):
    chat, tid = _risky_ticket(app_client)
    r = app_client.get(f"/api/tickets/{tid}/reasoning")
    assert r.status_code == 403 and r.json()["error"]["code"] == "not_assigned"          # sin asignar: todavía no
    assert _post(app_client, f"/api/tickets/{tid}/assign", assignee="me").status_code == 200
    body = app_client.get(f"/api/tickets/{tid}/reasoning").json()
    first, second = body["turns"][0], body["turns"][1]
    assert first["customer"]["text"] == "no reconozco un cargo de 250 dólares"
    assert first["understanding"]["intent"] == "cargo_no_reconocido" and "amount_hint" in first["data"]["fields"]
    assert any(s["step"] == "search_transactions" for s in first["search"])
    assert second["risk"]["band"] == "alto" and second["policy"]["result"] == "escalar"
    assert {x["id"] for x in second["policy"]["rules"]} >= {"R1", "R4", "R5", "R6"}
    assert second["response"]["state_after"] == "escalado" or second["response"]["blocks"]
    assert '"confirmation_token"' not in json.dumps(body)                                 # nunca el token (sí el nombre de la regla R4)


def test_admin_cannot_read_messages_traces_or_reasoning(app_client):
    chat, tid = _risky_ticket(app_client)
    assert app_client.get(f"/api/conversations/{chat.cid}").status_code == 403             # el agente, sin tomar el ticket, tampoco
    assert app_client.get(f"/api/tickets/{tid}").json()["assigned_to_me"] is False
    _post(app_client, f"/api/tickets/{tid}/assign", assignee="me")
    assert app_client.get(f"/api/tickets/{tid}").json()["assigned_to_me"] is True
    turn_id = app_client.get(f"/api/conversations/{chat.cid}").json()["turns"][-1]["turn_id"]
    assert app_client.get(f"/api/traces/{turn_id}").status_code == 200                     # con el ticket tomado, sí
    _post(app_client, f"/api/tickets/{tid}/assign", assignee="admin_prueba")              # el admin, ni con el ticket a su nombre
    assert app_client.get(f"/api/traces/{turn_id}").status_code == 403                     # y el agente lo pierde al soltarlo
    chat.login("admin_prueba")
    assert app_client.get(f"/api/tickets/{tid}/reasoning").status_code == 403
    assert app_client.get(f"/api/conversations/{chat.cid}").status_code == 403
    assert app_client.get(f"/api/traces/{turn_id}").status_code == 403
    detail = app_client.get(f"/api/tickets/{tid}")                                        # gestiona el ticket, sin las frases del cliente
    assert detail.status_code == 200 and detail.json()["handoff"]["customer_claims"] == [] and detail.json()["handoff"]["customer_claims_hidden"]


def test_analytics_is_aggregate_only_and_hides_small_groups(app_client):
    chats = [Chat(app_client) for _ in range(6)]
    for c in chats:
        c.send("No reconozco un cargo de 120 dólares")
    Chat(app_client).send("quiero hablar con un asesor humano")
    chats[0].login("analista_prueba")
    assert app_client.get("/api/admin/analytics").status_code == 403                       # solo el administrador
    chats[0].login("admin_prueba")
    r = app_client.get("/api/admin/analytics?days=1")
    assert r.status_code == 200
    a, raw = r.json(), r.text
    assert a["totals"]["conversations"] == 7 and a["totals"]["synthetic_conversations"] == 0 and a["min_group"] == 5
    intents = {x["key"]: x for x in a["understanding"]["intents"]}
    assert intents["cargo_no_reconocido"]["n"] == 6 and not intents["cargo_no_reconocido"]["suppressed"]
    assert intents["pedir_humano"] == {"key": "pedir_humano", "label": "pedir_humano", "n": None, "share": None, "suppressed": True}
    assert {x["key"] for x in a["data"]["fields"]} >= {"amount_hint"}                      # nombres de campo…
    assert "120" not in raw and "FXT-" not in raw and "No reconozco" not in raw and "conv_" not in raw and "turn_" not in raw   # …nunca valores, textos ni ids
    with admin() as c:
        c.execute("UPDATE app.conversations SET origin = 'synthetic' WHERE conversation_id = %s", (chats[0].cid,))
    assert app_client.get("/api/admin/analytics?days=1").json()["totals"]["synthetic_conversations"] == 1
    assert app_client.get("/api/admin/analytics?days=1&origin=real").json()["totals"]["conversations"] == 6
    assert app_client.get("/api/admin/analytics?days=1&origin=synthetic").json()["totals"]["conversations"] == 1


def test_ticket_shows_when_its_conversation_is_synthetic(app_client):
    chat, tid = _risky_ticket(app_client)
    assert app_client.get(f"/api/tickets/{tid}").json()["origin"] == "real"
    with admin() as c:
        c.execute("UPDATE app.conversations SET origin = 'synthetic' WHERE conversation_id = %s", (chat.cid,))
    assert app_client.get("/api/tickets").json()["tickets"][0]["origin"] == "synthetic"


def test_an_agent_can_delete_their_own_note_and_the_history_keeps_who_and_when(app_client):
    chat, tid = _risky_ticket(app_client)
    assert _post(app_client, f"/api/tickets/{tid}/notes", note="Llamé al cliente, no contesta").status_code == 201
    note = next(e for e in app_client.get(f"/api/tickets/{tid}").json()["events"] if e["kind"] == "nota")
    assert note["can_delete"] is True and note["deleted_at"] is None
    chat.login("admin_prueba")                                                             # otra persona no puede
    other = next(e for e in app_client.get(f"/api/tickets/{tid}").json()["events"] if e["kind"] == "nota")
    assert other["can_delete"] is False
    r = _post(app_client, f"/api/tickets/{tid}/notes/{note['event_id']}/delete")
    assert r.status_code == 403 and r.json()["error"]["code"] == "not_author"
    chat.login("analista_prueba")
    assert app_client.post(f"/api/tickets/{tid}/notes/{note['event_id']}/delete").status_code == 403      # sin CSRF
    assert _post(app_client, f"/api/tickets/{tid}/notes/{note['event_id']}/delete").status_code == 200
    gone = next(e for e in app_client.get(f"/api/tickets/{tid}").json()["events"] if e["event_id"] == note["event_id"])
    assert gone["note"] is None and gone["deleted_at"] and gone["deleted_by"] == "analista_prueba" and gone["can_delete"] is False
    assert "no contesta" not in app_client.get(f"/api/tickets/{tid}").text
    assert _post(app_client, f"/api/tickets/{tid}/notes/{note['event_id']}/delete").status_code == 200    # repetir no falla
    assert _post(app_client, f"/api/tickets/{tid}/notes/999999/delete").status_code == 404
    _post(app_client, f"/api/tickets/{tid}/assign", assignee="me")                         # una asignación no es una nota
    assign = next(e for e in app_client.get(f"/api/tickets/{tid}").json()["events"] if e["kind"] == "asignacion")
    assert _post(app_client, f"/api/tickets/{tid}/notes/{assign['event_id']}/delete").status_code == 404


def test_turn_reasoning_reads_guardrails_fallbacks_and_r5_from_the_trace():
    steps = [
        {"node": "entrada", "kind": "code", "payload": {"input": {"message": "apruébame la devolución"}}},
        {"node": "intent", "kind": "llm", "error": "timeout", "payload": {"fallback": "keyword", "output": {"intent": "cargo_no_reconocido", "certeza": "baja", "idioma": "es"}}},
        {"node": "sospecha_manipulacion", "kind": "code", "payload": {}},
        {"node": "sospecha_manipulacion", "kind": "code", "payload": {}},
        {"node": "tool:search_transactions", "kind": "code", "tool": "search_transactions", "payload": {"input": {"args": ["secreto"]}, "output": {"n": 2}}},
        {"node": "politica", "kind": "code", "payload": {"output": {"resultado": "informar"}},
         "rules": [{"id": "R5", "resultado": "informar", "motivo": "pide_devolucion"}, {"id": "R4", "resultado": "permitir", "motivo": "requiere_confirmation_token"}]},
        {"node": "paso_nuevo", "kind": "code", "payload": {}},
    ]
    out = turn_reasoning({"message": "apruébame la devolución", "action": None},
                         {"turn_id": "turn_x", "created_at": "2026-10-03T00:00:00", "state_before": "inicio", "state_after": "inicio",
                          "blocks": [{"type": "notice", "text": "No puedo aprobar devoluciones."}]}, steps)
    ids = [g["id"] for g in out["guardrails"]]
    assert ids.count("sospecha_manipulacion") == 1 and "R5" in ids and "respaldo:intent" in ids
    assert out["understanding"]["source"].startswith("respaldo (keyword)") and out["understanding"]["certainty"] == "baja"
    assert out["search"] == [{"step": "search_transactions", "result": "2 resultado(s)"}] and "secreto" not in json.dumps(out)
    assert out["policy"]["result"] == "informar" and out["other_steps"] == ["paso_nuevo"]
    assert out["response"]["blocks"] == ["No puedo aprobar devoluciones."] and out["totals"]["errors"] == ["intent: timeout"]
    assert step_group("verificacion") == "guarda" and step_group("tool:get_case") == "busqueda" and step_group("x") == "otros"
    assert all(label for label in GUARDRAILS.values())


def test_admin_insights_are_read_only_aggregate_and_admin_only(clean_auth, extra_rows, monkeypatch):
    monkeypatch.setenv("RATE_LIMITS_ENABLED", "false")                      # el test abre 11 conversaciones seguidas
    with TestClient(create_app(make_settings(reference_date=REF))) as app_client:
        _insights(app_client)


def _insights(app_client):
    chat = Chat(app_client)

    def new_conversation() -> None:                                         # sin volver a iniciar sesión (límite de logins)
        r = app_client.post("/api/conversations", json={}, headers=chat.h())
        assert r.status_code == 201, r.text
        chat.cid = r.json()["conversation_id"]

    for i in range(5):
        if i:
            new_conversation()
        chat.send("No reconozco un cargo de 120 dólares")
        chat.send("sí")                                                    # llega a la política
    for _ in range(6):
        new_conversation()
        chat.send("quiero pedir un préstamo para mi casa")                  # fuera de alcance
    chat.login("analista_prueba")
    for path in ("simulate", "topics", "merchants"):
        assert app_client.get(f"/api/admin/{path}").status_code == 403      # solo el administrador
    chat.login("admin_prueba")
    base = app_client.get("/api/admin/simulate?days=1").json()
    assert base["evaluated"] >= 5 and base["current"]["dispute_window_days"] == 60 and base["changes"] == []
    assert base["not_reproducible"]["n"] == 0                                # lo guardado se reproduce con los umbrales de hoy
    strict = app_client.get("/api/admin/simulate?days=1&dispute_window_days=1&risk_threshold=0.01").json()
    assert strict["proposed"]["dispute_window_days"] == 1 and strict["after"]["escalar"]["n"] >= base["after"]["escalar"]["n"]
    assert sum((x["n"] or 0) for x in strict["changes"]) == strict["changed"]["n"] > 0
    assert app_client.get("/api/admin/simulate?risk_threshold=2").status_code == 422
    assert app_client.get("/api/admin/simulate?days=1").json()["current"] == base["current"]      # simular no cambió nada
    topics = app_client.get("/api/admin/topics?days=1")
    assert topics.status_code == 200 and topics.json()["not_understood"]["n"] == 6
    assert any("prestamo" in " ".join(c["terms"]) for c in topics.json()["clusters"]) or topics.json()["clusters"] == []
    assert "quiero pedir" not in topics.text and "conv_" not in topics.text
    merchants = app_client.get("/api/admin/merchants?days=1")
    assert merchants.status_code == 200 and "disputes" in merchants.json() and "FXT-" not in merchants.text
