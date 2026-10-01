"""Chat de terminal contra la API local, para probar el sistema sin el frontend.

    .venv/bin/python scripts/chat_cli.py [--url http://127.0.0.1:8000] [--usuario demo_cargo_claro_1] [--idioma es|pt]

- Elige un usuario demo de la lista (o con --usuario). La contraseña es DEMO_PASSWORD del .env; no se imprime.
- Maneja la cookie de sesión, el CSRF (cookie csrf_token + cabecera X-CSRF-Token) y una Idempotency-Key por turno.
- Muestra los bloques de forma legible y numera las opciones del paso: candidatas, "sí, es este", confirmar,
  cancelar, tarjetas, movimientos para reclamar y respuestas rápidas ("¿algo más?"). Escribe un número para elegir
  o texto libre para responder. En una lista de selección múltiple: "1,3" elige varios.
- Si la conversación se cerró (despedida o inactividad) y escribes algo, abre una nueva enlazada
  (previous_conversation_id) con el cargo en foco y reenvía tu mensaje: no ves el 409.
- Comandos:
  - /traza: pasos del último turno. Usa una sesión aparte de analista (analista_1), porque las trazas son de la consola.
  - /nuevo: otra conversación.
  - /humano: pedir una persona.
  - /usuario: cambiar de usuario.
  - /ayuda y /salir.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]

USERS = [  # escenario de cada usuario demo (ref.demo_customers, regla del ETL en data_pipeline/etl/demo_customers.py)
    ("demo_cargo_claro_1", "Cargo claro: un cargo reciente con comercio y monto únicos. Reclámalo."),
    ("demo_cargo_claro_2", "Cargo claro (otro cliente)."),
    ("demo_cargos_parecidos_1", "Cargos parecidos: dos cargos de monto muy similar. El sistema debería preguntar cuál es."),
    ("demo_cargos_parecidos_2", "Cargos parecidos (otro cliente)."),
    ("demo_fraude_alto_1", "Riesgo alto: un cargo con fraud_score alto. Debe escalar a fraude y ofrecer bloquear la tarjeta."),
    ("demo_fraude_alto_2", "Riesgo alto (otro cliente)."),
    ("demo_fuera_de_plazo_1", "Fuera de plazo: un cargo de hace más de 60 días. Debe escalar a una persona."),
    ("demo_fuera_de_plazo_2", "Fuera de plazo (otro cliente)."),
    ("demo_pendiente_1", "Pendiente: un cargo todavía pendiente. Debe informar, sin abrir reclamo."),
    ("demo_pendiente_2", "Pendiente (otro cliente)."),
    ("demo_revertido_1", "Revertido: un cargo ya revertido. Debe informar que no hay cargo vigente."),
    ("demo_revertido_2", "Revertido (otro cliente)."),
]
ANALYST = "analista_1"
TIP = "Tip: si no sabes qué cargo reclamar, empieza con «¿cuáles fueron mis últimos movimientos?»."

USE_COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def c(code: str, s: str) -> str:
    return f"\033[{code}m{s}\033[0m" if USE_COLOR else s


bold, dim, cyan, green, yellow, red, magenta = (lambda s, k=k: c(k, s) for k in ("1", "2", "36", "32", "33", "31", "35"))


class Session:
    """Cliente HTTP con cookie de sesión y CSRF."""

    def __init__(self, url: str):
        self.http = httpx.Client(base_url=url, timeout=180)

    def headers(self, idempotent: bool = False) -> dict:
        h = {"X-CSRF-Token": self.http.cookies.get("csrf_token", "")}
        if idempotent:
            h["Idempotency-Key"] = str(uuid.uuid4())
        return h

    def login(self, username: str, password: str, language: str | None = None) -> dict:
        self.http.cookies.clear()
        self.http.get("/api/auth/csrf").raise_for_status()
        body = {"username": username, "password": password} | ({"language": language} if language else {})
        r = self.http.post("/api/auth/login", json=body, headers=self.headers())
        if r.status_code != 200:
            raise SystemExit(f"login de {username} falló: {r.status_code} {r.text[:200]}")
        return r.json()


# ---------------------------------------------------------------- render
def tx_line(t: dict) -> str:
    """Usa los campos que el backend ya formatea según el idioma (monto, fecha y estado)."""
    return " · ".join(str(x) for x in (t.get("label") or t.get("merchant_name"), t.get("amount_label"), t.get("date_label"),
                                       t.get("status_label")) if x)


MULTI: dict = {}        # última lista de selección múltiple: {"ids": [...]} para "1,3"


def render(resp: dict) -> list[tuple[str, dict | None]]:
    """Imprime los bloques y devuelve las opciones numeradas del paso: [(etiqueta, acción)]."""
    options: list[tuple[str, dict | None]] = []
    MULTI.clear()
    state = resp.get("state")
    for b in resp.get("blocks", []):
        t = b["type"]
        if t == "text":
            print(f"{cyan('asistente')}  {b['text']}".replace("\n", "\n           "))
        elif t == "candidate_list":
            multi = b.get("multi_select")
            print(dim(f"           candidatas (vuelta {b.get('round')}/{b.get('max_rounds')})"
                      + (" · puedes elegir varias: escribe por ejemplo 1,2" if multi else "") + ":"))
            ids = [cand["transaction_id"] for cand in b["candidates"]]
            for cand in b["candidates"]:
                mark = " (sugerida)" if cand["transaction_id"] in (b.get("suggested") or []) else ""
                options.append((tx_line(cand) + mark, {"type": "select_candidate", "transaction_id": cand["transaction_id"]}))
            if multi:
                MULTI["ids"] = ids
                options.append((b.get("select_all_label") or "Todos estos", {"type": "select_candidates", "transaction_ids": ids}))
            if b.get("allow_none"):
                options.append(("Ninguno de estos", {"type": "reject"}))
        elif t == "transaction_card":
            tx = b["transaction"]
            print(f"           ┌ {bold(tx_line(tx))}\n           └ canal {tx.get('channel')}")
            if state == "confirmando_movimiento":
                options += [("Sí, es este", {"type": "select_candidate", "transaction_id": tx["transaction_id"]}),
                            ("No es este", {"type": "reject"})]
        elif t == "action_confirmation":
            print(f"           {yellow('confirmar ' + b['action'])}: {b['summary']}")
            if b.get("disclaimer"):
                print(dim(f"           {b['disclaimer']}"))
            options += [(f"Confirmar ({b['action']})", {"type": "confirm", "confirmation_token": b["confirmation_token"]}),
                        ("Cancelar", {"type": "reject"})]
        elif t == "result":
            ok = b["status"] == "success" and b.get("verified")
            mark = green("✔ verificado") if ok else red(f"✘ {b['status']} (verified={b.get('verified')})")
            print(f"           {mark} {b['action']} → {b.get('reference_id') or ''} {dim(json.dumps(b.get('details') or {}, ensure_ascii=False))}")
            for item in b.get("items") or []:
                ok_i = green("✔") if item.get("verified") else red("✘")
                print(f"             {ok_i} {item.get('reference_id')} · {item.get('label')}")
        elif t == "handoff_notice":
            print(f"           {magenta('handoff')} {b.get('handoff_id')} · motivo {b.get('reason_code')}")
            if b.get("message"):
                print(f"           {b['message']}")
        elif t == "notice":
            color = yellow if b.get("level") == "warning" else dim
            print(color(f"           [aviso {b.get('code')}] {b.get('text')}"))
        elif t == "error":
            print(red(f"           [error {b.get('code')}] {b.get('message')}"))
        elif t == "transaction_list":
            p = b.get("period") or {}
            print(dim(f"           movimientos {p.get('from')} → {p.get('to')} · {b.get('count')} en total"))
            for tot in b.get("totals") or []:
                print(dim(f"           total: {tot.get('total_label')} ({tot['count']})"))
            for tx in b.get("transactions") or []:
                if b.get("can_dispute"):
                    options.append((f"Reclamar: {tx_line(tx)}", {"type": "dispute_transaction", "transaction_id": tx["transaction_id"]}))
                else:
                    print(f"           · {tx_line(tx)}")
        elif t == "card_list":
            for card in b["cards"]:
                options.append((f"{card['label']} ({card['status']})", {"type": "select_card", "product_id": card["product_id"]}))
        elif t == "quick_replies":
            for opt in b["options"]:
                options.append((opt["label"], opt["action"]))
        elif t == "case_list":
            for cs in b["cases"]:
                tx = cs.get("transaction") or {}
                print(f"           · {cs['case_id']} · {cs['status']} · {cs.get('reason_code')} · {tx.get('label')} · {tx.get('amount_label')} · {tx.get('date_label')}")
        else:
            print(dim(f"           [{t}] {json.dumps(b, ensure_ascii=False)[:200]}"))
    for i, (label, _) in enumerate(options, 1):
        print(f"           {bold(str(i))}. {label}")
    print(dim(f"           estado: {state} · vuelta de aclaración {resp.get('clarification_round', 0)}"))
    return options


def show_trace(analyst: Session, turn_id: str | None) -> None:
    if not turn_id:
        print(dim("todavía no hay turnos en esta conversación"))
        return
    r = analyst.http.get(f"/api/traces/{turn_id}")
    if r.status_code == 401:
        print(red("la sesión de analista venció; vuelve a escribir /traza"))
        analyst.http.cookies.clear()
        return
    r.raise_for_status()
    tr = r.json()
    print(dim(f"traza {tr['turn_id']} · {tr['state_before']} → {tr['state_after']}"))
    print(dim(f"{'#':>3} {'nodo':28s} {'tipo':5s} {'implementación / modelo':34s} {'ms':>7} {'USD':>8}"))
    for s in tr["steps"]:
        payload = s.get("payload") or {}
        impl = s.get("model_id") or s.get("model") or s.get("implementation") or s.get("tool") or ""
        extra = []
        if payload.get("modo"):
            extra.append(f"modo={payload['modo']}:{payload.get('motivo')}")
        if payload.get("fallback"):
            extra.append(f"fallback={payload['fallback']}")
        if s.get("error"):
            extra.append(red(f"error={str(s['error'])[:60]}"))
        cost = f"{float(s['cost_usd']):.4f}" if s.get("cost_usd") is not None else ""
        print(f"{s['step_seq']:>3} {s['node'][:28]:28s} {s['kind']:5s} {str(impl)[:34]:34s} {s['latency_ms'] or 0:>7} {cost:>8} {' '.join(extra)}")
    t = tr["totals"]
    print(dim(f"total pasos {t['latency_ms']} ms (intent y extract corren en paralelo) · ${float(t['cost_usd']):.4f}"))


def pick_user() -> str:
    print(bold("Usuarios demo:"))
    for i, (u, desc) in enumerate(USERS, 1):
        print(f"  {i:2d}. {u:26s} {dim(desc)}")
    while True:
        a = input("Elige un número (o escribe un usuario): ").strip()
        if a.isdigit() and 1 <= int(a) <= len(USERS):
            return USERS[int(a) - 1][0]
        if a:
            return a


HELP = """Escribe texto para hablar con el asistente, o el número de una opción.
Comandos:
  /traza    pasos del último turno
  /nuevo    nueva conversación
  /humano   pedir una persona
  /usuario  cambiar de usuario
  /ayuda    esta ayuda
  /salir    terminar"""


def main() -> int:
    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser(prog="scripts/chat_cli.py")
    ap.add_argument("--url", default=os.environ.get("CHAT_API_URL", "http://127.0.0.1:8000"))
    ap.add_argument("--usuario")
    ap.add_argument("--idioma", choices=["es", "pt"], default="es")
    args = ap.parse_args()
    password = os.environ.get("DEMO_PASSWORD")
    if not password:
        raise SystemExit("falta DEMO_PASSWORD en .env")
    try:
        httpx.get(f"{args.url}/docs", timeout=5)
    except httpx.HTTPError:
        raise SystemExit(f"no hay API en {args.url}: levanta el backend primero (ver instrucciones)")

    customer, analyst = Session(args.url), Session(args.url)
    username = args.usuario or pick_user()

    def start(previous: str | None = None) -> tuple[str, dict]:
        body = {"language": args.idioma} | ({"previous_conversation_id": previous} if previous else {})
        r = customer.http.post("/api/conversations", json=body, headers=customer.headers(idempotent=True))
        if r.status_code != 201:
            raise SystemExit(f"no se pudo crear la conversación: {r.status_code} {r.text[:200]}")
        conv = r.json()
        print(dim(f"\nconversación {conv['conversation_id']} · hoy simulado {conv.get('session_date')} · "
                  f"datos hasta {(conv.get('data_as_of') or {}).get('max_transaction_date')}"))
        return conv["conversation_id"], conv

    info = customer.login(username, password, args.idioma)
    print(green(f"sesión de {username} ({info.get('display_name')}) · rol {info.get('role')}"))
    print(dim(HELP + "\n" + TIP))
    conv_id, first = start()
    options = render(first)
    last_turn: str | None = None

    while True:
        try:
            line = input(bold("tú › ")).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line:
            continue
        if line == "/salir":
            return 0
        if line == "/ayuda":
            print(HELP)
            continue
        if line == "/traza":
            if not analyst.http.cookies.get("session"):
                analyst.login(ANALYST, password)
            show_trace(analyst, last_turn)
            continue
        if line in ("/nuevo", "/usuario"):
            if line == "/usuario":
                username = pick_user()
                info = customer.login(username, password, args.idioma)
                print(green(f"sesión de {username} ({info.get('display_name')})"))
            conv_id, first = start()
            options, last_turn = render(first), None
            continue
        if line == "/humano":
            body = {"action": {"type": "request_human"}}
        elif MULTI and re.fullmatch(r"\s*\d+(\s*[,y ]\s*\d+)+\s*", line):         # "1,3" en una lista múltiple
            nums = [int(x) for x in re.findall(r"\d+", line)]
            ids = [MULTI["ids"][i - 1] for i in nums if 1 <= i <= len(MULTI["ids"])]
            print(dim(f"     → {len(ids)} cargos elegidos"))
            body = {"action": {"type": "select_candidates", "transaction_ids": ids}}
        elif line.isdigit() and 1 <= int(line) <= len(options):
            label, action = options[int(line) - 1]
            print(dim(f"     → {label}"))
            body = {"action": action}
        else:
            body = {"message": line}
        r = customer.http.post(f"/api/conversations/{conv_id}/turns", json=body, headers=customer.headers(idempotent=True))
        if r.status_code == 401:
            print(yellow("la sesión venció: vuelvo a iniciar sesión; repite el mensaje"))
            customer.login(username, password, args.idioma)
            continue
        err = (r.json().get("error") if r.status_code != 200 and r.headers.get("content-type", "").startswith("application/json") else None) or {}
        if err.get("code") == "conversation_closed" and "message" in body:
            # el cliente no ve un error: conversación nueva enlazada (hereda el cargo en foco) y se reenvía el mensaje
            reason = (err.get("details") or {}).get("reason")
            print(dim(f"     (la conversación anterior se cerró{' por inactividad' if reason == 'inactividad' else ''}; sigo en una nueva)"))
            conv_id, first = start(previous=conv_id)
            r = customer.http.post(f"/api/conversations/{conv_id}/turns", json=body, headers=customer.headers(idempotent=True))
            err = (r.json().get("error") if r.status_code != 200 else None) or {}
        if r.status_code != 200:
            hint = " · escribe /nuevo para empezar otra conversación" if err.get("code") == "conversation_closed" else ""
            print(red(f"[{r.status_code} {err.get('code', '')}] {err.get('message', r.text[:200])}{hint}"))
            continue
        resp = r.json()
        last_turn = resp.get("turn_id")
        options = render(resp)


if __name__ == "__main__":
    sys.exit(main())
