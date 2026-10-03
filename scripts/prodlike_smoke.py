"""Prueba de humo del entorno prodlike por HTTP, a través del proxy (un solo origen, TLS). Ver docs/prodlike.md.

    scripts/prodlike_smoke.sh            # la llama con el entorno correcto
    python scripts/prodlike_smoke.py --url https://localhost:8443 [--md salida.md]

Recorre lo que un cliente, un agente y un admin hacen en la demo y comprueba el resultado de cada paso. Usa el LLM que tenga
el backend (en prodlike, claude -p): son ~12 turnos. Escribe en la base prodlike (reclamos, tickets): es su propósito.
El paso del límite de peticiones va al final, con una sesión propia, para no dejar sin cupo a los demás.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
import uuid
from pathlib import Path

import httpx

STATE = Path(os.environ.get("PRODLIKE_HOME", Path.home() / ".factored-prodlike"))


class Session:
    def __init__(self, url: str):
        self.http = httpx.Client(base_url=url, verify=False, timeout=240)      # CA local de Caddy: no está en el almacén del sistema

    def headers(self) -> dict:
        return {"X-CSRF-Token": self.http.cookies.get("csrf_token", ""), "Idempotency-Key": str(uuid.uuid4())}

    def login(self, username: str, password: str) -> "Session":
        self.http.get("/api/auth/csrf").raise_for_status()
        r = self.http.post("/api/auth/login", json={"username": username, "password": password}, headers=self.headers())
        assert r.status_code == 200, f"login de {username}: {r.status_code}"
        return self

    def post(self, path: str, body: dict) -> httpx.Response:
        return self.http.post(path, json=body, headers=self.headers())

    def start(self) -> str:
        r = self.post("/api/conversations", {"language": "es"})
        assert r.status_code == 201, f"abrir conversación: {r.status_code}"
        return r.json()["conversation_id"]

    def turn(self, conv: str, *, message: str | None = None, action: dict | None = None) -> dict:
        r = self.post(f"/api/conversations/{conv}/turns", {"message": message} if message else {"action": action})
        assert r.status_code == 200, f"turno: {r.status_code} {r.text[:200]}"
        return r.json()


def blocks(resp: dict, kind: str) -> list[dict]:
    return [b for b in resp.get("blocks", []) if b["type"] == kind]


def drive(s: Session, conv: str, resp: dict, *, confirm: set[str], prefer: str | None = None, max_steps: int = 6) -> tuple[dict, list[dict]]:
    """Sigue los pasos guiados: elige el cargo `prefer` si hay candidatas, confirma el movimiento mostrado y las acciones
    de `confirm`; rechaza las demás. Devuelve la última respuesta y todos los bloques vistos."""
    seen = list(resp.get("blocks", []))
    for _ in range(max_steps):
        action = None
        if conf := blocks(resp, "action_confirmation"):
            action = ({"type": "confirm", "confirmation_token": conf[0]["confirmation_token"]} if conf[0]["action"] in confirm
                      else {"type": "reject"})
        elif resp.get("state") == "confirmando_movimiento" and (card := blocks(resp, "transaction_card")):
            action = {"type": "select_candidate", "transaction_id": card[0]["transaction"]["transaction_id"]}
        elif (cands := blocks(resp, "candidate_list")) and prefer in [c["transaction_id"] for c in cands[0]["candidates"]]:
            action = {"type": "select_candidate", "transaction_id": prefer}
        if action is None:
            break
        resp = s.turn(conv, action=action)
        seen += resp.get("blocks", [])
    return resp, seen


def of(seen: list[dict], kind: str) -> list[dict]:
    return [b for b in seen if b["type"] == kind]


def run(url: str, password: str) -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []
    ctx: dict = {}

    def step(name: str):
        def deco(fn):
            t0 = time.monotonic()
            try:
                detail, ok = fn() or "", True
            except Exception as e:  # noqa: BLE001 — cada paso reporta su fallo y la prueba sigue
                detail, ok = f"{type(e).__name__}: {str(e)[:160]}", False
            results.append((name, ok, f"{detail} ({time.monotonic() - t0:.1f} s)"))
            print(f"{'✔' if ok else '✘'} {name}: {results[-1][2]}", flush=True)
        return deco

    @step("Un solo origen con TLS y cabeceras de seguridad")
    def _():
        r = httpx.get(url + "/", verify=False)
        assert r.status_code == 200 and "<div id=\"root\">" in r.text, "el proxy no sirve el build del frontend"
        for h in ("content-security-policy", "strict-transport-security", "x-content-type-options"):
            assert h in r.headers, f"falta {h}"
        ready = httpx.get(url + "/api/ready", verify=False).json()
        assert ready["status"] == "ready", ready
        return f"frontend y /api en {url}; LLM {ready['llm_provider']}"

    @step("Login de cliente (cookie Secure + CSRF)")
    def _():
        ctx["claro"] = s = Session(url).login("demo_cargo_claro_1", password)
        me = s.http.get("/api/auth/me").json()
        assert me["role"] == "customer", me
        jar = {c.name: c for c in s.http.cookies.jar}
        assert jar["session"].secure, "la cookie de sesión no es Secure"
        return f"sesión de {me['display_name']}"

    @step("Cargo claro de punta a punta (referencia RCL)")
    def _():
        s = ctx["claro"]
        conv = ctx["conv_claro"] = s.start()
        resp = s.turn(conv, message="¿Cuáles fueron mis últimos movimientos?")
        txs = blocks(resp, "transaction_list")[0]["transactions"]
        tx = txs[0]
        resp = s.turn(conv, message=f"No reconozco el cargo de {tx['amount_label']} del {tx['date_label']}, yo no hice esa compra")
        resp, seen = drive(s, conv, resp, confirm={"create_dispute_case"}, prefer=tx["transaction_id"])
        res = [b for b in of(seen, "result") if b["action"] == "create_dispute_case"]
        ref = re.search(r"RCL-[A-Z0-9]{6}", " ".join(str(b) for b in seen))
        if not res and ref:                              # segunda corrida: el cargo ya tiene su reclamo y no se duplica
            return f"el cargo ya tenía el reclamo {ref.group(0)} (corrida anterior); no se duplica"
        assert res and res[0]["status"] == "success" and res[0].get("verified"), f"sin reclamo verificado (estado {resp.get('state')})"
        ref = re.search(r"RCL-[A-Z0-9]{6}", " ".join(str(b) for b in seen))
        assert ref, "el cliente no vio la referencia RCL"
        return f"reclamo {ref.group(0)} creado y verificado ({res[0]['reference_id']})"

    @step("Caso ambiguo: sin datos pide uno; con el monto, pide elegir entre cargos parecidos")
    def _():
        s = Session(url).login("demo_cargos_parecidos_1", password)
        conv = s.start()
        resp = s.turn(conv, message="No reconozco un cargo")
        codes = [b.get("code") for b in blocks(resp, "notice")]
        assert codes == ["need_detail"] and not blocks(resp, "candidate_list"), f"sin datos debía pedir uno (avisos {codes})"
        resp = s.turn(conv, action={"type": "start_topic", "topic": "consulta_movimientos"})      # "Ver mis últimos movimientos"
        txs = blocks(resp, "transaction_list")[0]["transactions"]
        # monto aproximado (no el exacto): con cargos de monto parecido, el asistente debe pedir que elija
        about = f"{round(float(txs[0]['amount']))} {txs[0]['currency']}"
        resp = s.turn(conv, message=f"No reconozco un cargo de unos {about}")
        cands = blocks(resp, "candidate_list")
        assert cands and len(cands[0]["candidates"]) >= 2, f"no ofreció candidatas (estado {resp.get('state')})"
        assert not of(resp["blocks"], "result"), "actuó sin aclarar"
        assert "parecid" not in " ".join(b["text"] for b in blocks(resp, "text")), "llamó 'parecidos' a los candidatos"
        return f"pide un dato; con el monto muestra {len(cands[0]['candidates'])} candidatas que coinciden, sin acción hasta que el cliente elija"

    @step("Riesgo alto → ticket urgente")
    def _():
        s = Session(url).login("demo_fraude_alto_1", password)
        conv = s.start()
        resp = s.turn(conv, message="¿Cuáles fueron mis últimos movimientos?")
        txs = blocks(resp, "transaction_list")[0]["transactions"]
        tx = txs[0]
        resp = s.turn(conv, message=f"No reconozco el cargo de {tx['amount_label']} del {tx['date_label']}, yo no lo hice")
        resp, seen = drive(s, conv, resp, confirm=set(), prefer=tx["transaction_id"])     # no confirma bloqueos ni reclamos
        notice = of(seen, "handoff_notice")
        assert notice, f"no escaló (estado {resp.get('state')})"
        ctx["handoff"] = notice[0]["handoff_id"]
        agent = ctx["agent"] = Session(url).login("analista_1", password)
        t = agent.http.get(f"/api/tickets/{ctx['handoff']}").json()
        t = t.get("ticket", t)
        assert notice[0].get("reason_code") == "riesgo_alto", f"motivo {notice[0].get('reason_code')}"
        assert t["priority"] == "urgente", f"prioridad {t['priority']}"
        assert not [b for b in of(seen, "result") if b["action"] == "create_dispute_case"], "abrió un reclamo en riesgo alto"
        return f"handoff {ctx['handoff']} · motivo {notice[0].get('reason_code')} · prioridad urgente, sin reclamo automático"

    @step("Fuera de alcance: texto aprobado y enlace, sin acciones")
    def _():
        s = ctx["claro"]
        conv = s.start()
        resp = s.turn(conv, message="¿Me pueden dar un préstamo para comprar un carro?")
        assert not of(resp["blocks"], "result") and not of(resp["blocks"], "handoff_notice"), "actuó en un tema fuera de alcance"
        assert of(resp["blocks"], "link"), "no mostró el enlace al sitio del banco"
        return "redirige al sitio del banco"

    @step("Historial de conversaciones y feedback")
    def _():
        s = ctx["claro"]
        hist = s.http.get("/api/me/conversations").json()
        items = hist.get("conversations") or hist.get("items") or []
        mine = [c for c in items if c["conversation_id"] == ctx["conv_claro"]]
        assert mine, "la conversación del reclamo no aparece en el historial"
        detail = s.http.get(f"/api/me/conversations/{ctx['conv_claro']}")
        assert detail.status_code == 200 and detail.json().get("turns"), "sin detalle de la conversación"
        other = Session(url).login("demo_cargo_claro_2", password).http.get(f"/api/me/conversations/{ctx['conv_claro']}")
        assert other.status_code == 404, f"otro cliente recibió {other.status_code}"
        fb = s.post(f"/api/conversations/{ctx['conv_claro']}/feedback", {"rating": "up", "comment": "prueba de humo"})
        assert fb.status_code in (201, 409), fb.status_code
        return f"{len(items)} conversaciones; ajena → 404; feedback {fb.status_code}"

    @step("Un agente ve y toma el ticket")
    def _():
        agent = ctx["agent"]
        inbox = agent.http.get("/api/tickets", params={"open": "true"}).json()
        ids = [t["ticket_id"] if "ticket_id" in t else t["handoff_id"] for t in inbox["tickets"]]
        assert ctx["handoff"] in ids, "el ticket no está en la bandeja"
        assert ids[0] == ctx["handoff"] or inbox["tickets"][0]["priority"] == "urgente", "los urgentes no van primero"
        r = agent.post(f"/api/tickets/{ctx['handoff']}/assign", {"assignee": "me"})
        assert r.status_code == 200, r.status_code
        r = agent.post(f"/api/tickets/{ctx['handoff']}/status", {"status": "en_curso"})
        assert r.status_code == 200, f"cambio de estado: {r.status_code}"
        forbidden = ctx["claro"].http.get("/api/tickets")
        assert forbidden.status_code == 403, f"un cliente recibió {forbidden.status_code} en /api/tickets"
        return f"{inbox['total']} tickets abiertos; asignado a analista_1 y en curso; cliente → 403"

    @step("Un admin ve los SLO")
    def _():
        admin = Session(url).login("admin_1", password)
        slo = admin.http.get("/api/admin/slo")
        assert slo.status_code == 200, slo.status_code
        names = [x.get("name") or x.get("id") for x in slo.json().get("slos", [])]
        assert names, "sin SLO"
        assert admin.http.get("/api/admin/overview").status_code == 200 and admin.http.get("/api/admin/logs").status_code == 200
        assert ctx["agent"].http.get("/api/admin/slo").status_code == 403, "un agente entró al panel admin"
        return f"{len(names)} SLO; overview y logs responden; agente → 403"

    @step("El límite de peticiones responde 429")
    def _():
        s = Session(url).login("demo_revertido_2", password)      # sesión propia: no gasta el cupo de los demás usuarios
        codes = [s.http.get("/api/auth/me").status_code for _ in range(70)]
        assert 429 in codes, f"70 peticiones seguidas sin 429 ({set(codes)})"
        r = s.http.get("/api/auth/me")
        assert r.status_code == 429 and "retry-after" in r.headers, "429 sin Retry-After"
        return f"429 tras {codes.index(429)} peticiones en un minuto, con Retry-After"

    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="https://localhost:8443")
    ap.add_argument("--md", type=Path, help="escribe además una tabla Markdown")
    args = ap.parse_args()
    password = os.environ.get("DEMO_PASSWORD") or next(
        (line.split("=", 1)[1].strip() for line in (STATE / "env").read_text().splitlines() if line.startswith("DEMO_PASSWORD=")), "")
    results = run(args.url, password)
    passed = sum(ok for _, ok, _ in results)
    print(f"\n{passed}/{len(results)} pasos OK")
    if args.md:
        args.md.write_text("| Paso | Resultado | Detalle |\n|---|---|---|\n" + "".join(
            f"| {n} | {'OK' if ok else 'FALLA'} | {d} |\n" for n, ok, d in results), encoding="utf-8")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    sys.exit(main())
