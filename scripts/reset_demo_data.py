"""Deja las cuentas demo como recién creadas: borra lo que la app creó para ellas. No toca ref.* ni los usuarios.

    # 1. ver qué se borraría (no cambia nada)
    RENDER_ADMIN_DATABASE_URL="$(cat ~/.render_db_url)" .venv/bin/python scripts/reset_demo_data.py --confirm-database <nombre>
    # 2. borrarlo, en una sola transacción
    RENDER_ADMIN_DATABASE_URL="$(cat ~/.render_db_url)" .venv/bin/python scripts/reset_demo_data.py --confirm-database <nombre> --apply

Qué se borra, solo de los clientes demo (ref.demo_customers) y de los usuarios demo, agentes y admin:
- conversaciones, turnos, trazas, tokens de confirmación, reclamos, bloqueos de tarjeta, handoffs (tickets) con su historial
  y sus notas, feedback y consumo de voz;
- sesiones abiertas, claves de idempotencia y eventos de login (así ninguna cuenta queda bloqueada por intentos fallidos).
Qué NO se toca: los usuarios y su contraseña, ref.* (clientes, productos, movimientos), las conversaciones sintéticas
(`origin = 'synthetic'`) y la configuración.

La URL va solo por entorno (RENDER_ADMIN_DATABASE_URL o --database-url) y nunca se imprime. Exige --confirm-database con el
nombre exacto de la base, para no borrar en la base equivocada.
"""
from __future__ import annotations

import argparse
import os
import sys
from urllib.parse import urlsplit

import psycopg

DEMO = "SELECT customer_id FROM ref.demo_customers"
CONV = f"SELECT conversation_id FROM app.conversations WHERE customer_id IN ({DEMO}) AND origin <> 'synthetic'"
USERS = f"SELECT user_id FROM app.users WHERE customer_id IN ({DEMO}) OR role IN ('analyst', 'admin')"
SESS = f"SELECT session_id FROM app.sessions WHERE user_id IN ({USERS})"
HOF = f"SELECT handoff_id FROM app.handoffs WHERE conversation_id IN ({CONV})"
# orden: primero lo que depende de otra cosa
STEPS = [
    ("consumo de voz", f"DELETE FROM app.voice_usage WHERE conversation_id IN ({CONV}) OR session_id IN ({SESS})"),
    ("historial y notas de tickets", f"DELETE FROM app.ticket_events WHERE handoff_id IN ({HOF})"),
    ("feedback", f"DELETE FROM app.feedback WHERE conversation_id IN ({CONV})"),
    ("bloqueos de tarjeta", f"DELETE FROM app.card_status_overrides WHERE customer_id IN ({DEMO})"),
    ("reclamos", f"DELETE FROM app.dispute_cases WHERE conversation_id IN ({CONV}) OR customer_id IN ({DEMO})"),
    ("handoffs (tickets)", f"DELETE FROM app.handoffs WHERE handoff_id IN ({HOF})"),
    ("tokens de confirmación", f"DELETE FROM app.confirmation_tokens WHERE conversation_id IN ({CONV}) OR session_id IN ({SESS})"),
    ("trazas", f"DELETE FROM app.traces WHERE conversation_id IN ({CONV})"),
    ("enlaces entre conversaciones", f"UPDATE app.conversations SET previous_conversation_id = NULL WHERE previous_conversation_id IN ({CONV})"),
    ("turnos", f"DELETE FROM app.turns WHERE conversation_id IN ({CONV})"),
    ("conversaciones", f"DELETE FROM app.conversations WHERE conversation_id IN ({CONV})"),
    ("claves de idempotencia", f"DELETE FROM app.idempotency_keys WHERE session_id IN ({SESS})"),
    ("sesiones", f"DELETE FROM app.sessions WHERE session_id IN ({SESS})"),
    ("eventos de login", f"DELETE FROM app.login_events WHERE user_id IN ({USERS})"),
]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--database-url", default=os.environ.get("RENDER_ADMIN_DATABASE_URL"))
    ap.add_argument("--confirm-database", required=True, help="nombre exacto de la base de destino")
    ap.add_argument("--apply", action="store_true", help="borrar de verdad (sin esto solo cuenta)")
    a = ap.parse_args(argv)
    if not a.database_url:
        raise SystemExit("falta RENDER_ADMIN_DATABASE_URL (o --database-url)")
    url = a.database_url.replace("postgresql+psycopg://", "postgresql://")
    name = urlsplit(url).path.lstrip("/")
    if name != a.confirm_database:
        raise SystemExit("--confirm-database no coincide con el nombre de la base de la URL: no se hace nada")
    with psycopg.connect(url, connect_timeout=15) as c:
        demo = c.execute(f"SELECT count(*) FROM ({DEMO}) d").fetchone()[0]
        if not demo:
            raise SystemExit("la base no tiene clientes demo (ref.demo_customers vacía): no se hace nada")
        print(f"base {name}: {demo} clientes demo · {'BORRANDO' if a.apply else 'solo conteo (agrega --apply para borrar)'}")
        total = 0
        for label, sql in STEPS:
            if a.apply:
                n = c.execute(sql).rowcount
            else:
                n = c.execute("SELECT count(*) FROM (" + sql.replace("DELETE FROM", "SELECT 1 FROM", 1).replace(
                    "UPDATE app.conversations SET previous_conversation_id = NULL", "SELECT 1 FROM app.conversations", 1) + ") x").fetchone()[0]
            total += n
            print(f"  {n:>6}  {label}")
        if a.apply:
            c.commit()
            print(f"listo: {total} filas. Usuarios y datos del banco intactos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
