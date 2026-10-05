"""Siembra conversaciones SINTÉTICAS en la base local para que la analítica del administrador y el panel del agente tengan
volumen. Solo en una base local; nunca en la desplegada.

    .venv/bin/python scripts/seed_synthetic_history.py --n 300            # 300 conversaciones repartidas en 30 días, sin LLM
    .venv/bin/python scripts/seed_synthetic_history.py --n 100 --llm      # con el LLM configurado (claude -p o la API): cuesta
    .venv/bin/python scripts/seed_synthetic_history.py --reset            # borra TODO lo sintético

Qué hace
- Toma flujos del generador combinatorio (eval/generated/generator.py): variantes de los casos de dev con otro cliente,
  saludos y ruido, en español y portugués.
- Corre cada flujo contra el sistema real en proceso (API, controlador, tools, política) sobre la base local, con un
  usuario `sint_…` creado para un cliente del dataset que cumple el escenario. Quedan las mismas filas que deja una
  conversación de verdad: turnos, trazas, reclamos, traspasos y bloqueos.
- Marca la conversación con `origin = 'synthetic'`, reparte las fechas en los últimos `--days` días y agrega una valoración
  a una parte (sin comentario).

Qué garantiza
- Nunca usa los clientes de demostración (ref.demo_customers): sus escenarios quedan intactos.
- Todo lo sembrado se puede separar (`origin`) y borrar (`--reset`). El administrador ve una etiqueta y un filtro.
- No siembra en un servidor que no sea local (EVAL_STORE_ALLOW_REMOTE no aplica aquí: no hay excepción).
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import random
import secrets
import sys
import uuid
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

import psycopg
from dotenv import dotenv_values
from psycopg.rows import dict_row

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "postgres", "db"}
# tablas con conversation_id y sus columnas de fecha, para repartir las conversaciones en el tiempo
DATED = {"conversations": ("created_at", "updated_at", "closed_at"), "turns": ("created_at",), "traces": ("created_at",),
         "handoffs": ("created_at", "updated_at"), "dispute_cases": ("created_at", "updated_at", "confirmed_at"),
         "card_status_overrides": ("created_at",), "feedback": ("created_at",)}


def plain(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://")


def local_env() -> dict[str, str]:
    env = {**dotenv_values(REPO / ".env"), **os.environ}
    for key in ("ADMIN_DATABASE_URL", "DATABASE_URL", "CONSOLE_DATABASE_URL"):
        if not env.get(key):
            raise SystemExit(f"falta {key} (.env): correr primero scripts/dev_up.sh")
        host = urlsplit(plain(env[key])).hostname or "localhost"
        if host not in LOCAL_HOSTS:
            raise SystemExit(f"las conversaciones sintéticas solo se siembran en una base local; {key} apunta a {host}")
    return env


def reset(conn) -> int:
    ids = [r["conversation_id"] for r in conn.execute("SELECT conversation_id FROM app.conversations WHERE origin = 'synthetic'").fetchall()]
    users = [r["user_id"] for r in conn.execute("SELECT user_id FROM app.users WHERE username LIKE 'sint\\_%'").fetchall()]
    p = {"ids": ids, "users": users}
    for sql in ("DELETE FROM app.ticket_events WHERE handoff_id IN (SELECT handoff_id FROM app.handoffs WHERE conversation_id = ANY(%(ids)s))",
                "DELETE FROM app.feedback WHERE conversation_id = ANY(%(ids)s)",
                "DELETE FROM app.dispute_cases WHERE conversation_id = ANY(%(ids)s)",
                "DELETE FROM app.card_status_overrides WHERE conversation_id = ANY(%(ids)s)",
                "DELETE FROM app.handoffs WHERE conversation_id = ANY(%(ids)s)",
                "DELETE FROM app.traces WHERE conversation_id = ANY(%(ids)s)",
                "DELETE FROM app.confirmation_tokens WHERE conversation_id = ANY(%(ids)s)",
                "UPDATE app.conversations SET previous_conversation_id = NULL WHERE previous_conversation_id = ANY(%(ids)s)",
                "DELETE FROM app.turns WHERE conversation_id = ANY(%(ids)s)",
                "DELETE FROM app.conversations WHERE conversation_id = ANY(%(ids)s)",
                "DELETE FROM app.idempotency_keys WHERE session_id IN (SELECT session_id FROM app.sessions WHERE user_id = ANY(%(users)s))",
                "DELETE FROM app.sessions WHERE user_id = ANY(%(users)s)",
                "DELETE FROM app.login_events WHERE user_id = ANY(%(users)s)",
                "DELETE FROM app.users WHERE user_id = ANY(%(users)s)"):
        conn.execute(sql, p)
    return len(ids)


def seed(n: int, days: int, seed_value: int, use_llm: bool, env: dict[str, str]) -> dict:
    os.environ.update({"RATE_LIMITS_ENABLED": "false", "LOG_LEVEL": os.environ.get("LOG_LEVEL", "WARNING")})
    if not use_llm:
        os.environ["LLM_PROVIDER"] = "fake"
    os.environ.setdefault("CONFIRM_MODE", "template")
    os.environ.setdefault("CLARIFY_MODE", "auto")

    from fastapi.testclient import TestClient
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from backend.app.config import Settings
    from backend.app.main import create_app
    from backend.app.security import hash_password
    from data_pipeline.run import migrate
    from eval.cases.selectors import SELECTORS, resolve
    from eval.generated.generator import generate
    from eval.harness.runner import CaseRunner, _as_date, tx_vars

    admin_url = env["ADMIN_DATABASE_URL"]
    migrate(admin_url)
    admin = psycopg.connect(plain(admin_url), autocommit=True, row_factory=dict_row)
    ref_date = admin.execute("SELECT max(transaction_date)::date AS d FROM ref.transactions").fetchone()["d"]
    if ref_date is None:
        raise SystemExit("la base no tiene transacciones: correr primero scripts/dev_up.sh")
    demo = {r["customer_id"] for r in admin.execute("SELECT customer_id FROM ref.demo_customers").fetchall()}
    app = create_app(Settings(database_url=env["DATABASE_URL"], console_database_url=env["CONSOLE_DATABASE_URL"], reference_date=ref_date, _env_file=None))
    urls = {"admin": admin_url}
    runner = CaseRunner(app, urls, ref_date)
    rng = random.Random(seed_value)
    # solo guiones de mensajes y botones: sin fallos inyectados, sesiones vencidas ni peticiones de otros roles
    flows = [g for g in generate(n * 3, seed_value) if all(s.message is not None or s.action is not None or s.new_conversation for s in g.case.steps)]

    counts: dict = {}                            # filas de cada selector por fecha: se cuentan una vez

    async def pick(case, sd):
        eng = create_async_engine(admin_url)
        try:
            async with eng.connect() as c:
                if (case.selector, sd) not in counts:
                    counts[(case.selector, sd)] = (await c.execute(text(f"SELECT count(*) FROM ({SELECTORS[case.selector]}) s"), {"r": sd})).scalar_one()
                rows = counts[(case.selector, sd)]
                if not rows:
                    return None
                return await resolve(c, case.selector, case.pick % rows, sd)
        finally:
            await eng.dispose()

    stats = {"conversations": 0, "skipped_demo": 0, "skipped_error": 0, "feedback": 0}
    with TestClient(app) as client:
        for g in flows:
            if stats["conversations"] >= n:
                break
            case = g.case
            sd = case.session_date or ref_date
            try:
                resolved = asyncio.run(pick(case, sd))
            except Exception:                    # noqa: BLE001 — un selector sin filas en este dataset no detiene la siembra
                resolved = None
            if resolved is None:
                stats["skipped_error"] += 1
                continue
            if resolved["customer_id"] in demo:
                stats["skipped_demo"] += 1
                continue
            if case.today_after and isinstance(resolved.get(case.today_after), dict):
                sd = _as_date(resolved[case.today_after]["transaction_date"]) + timedelta(days=1)
            username = "sint_" + hashlib.sha256(f"{seed_value}:{case.case_id}".encode()).hexdigest()[:16]
            password = secrets.token_urlsafe(16)
            pw_hash = hash_password(password)
            if not admin.execute("UPDATE app.users SET password_hash = %s, is_active = true WHERE username = %s", (pw_hash, username)).rowcount:
                admin.execute("INSERT INTO app.users (user_id, username, password_hash, role, customer_id) VALUES (%s, %s, %s, 'customer', %s)",
                              (f"usr_{uuid.uuid4().hex[:20]}", username, pw_hash, resolved["customer_id"]))
            vars_ = {**tx_vars(resolved.get("target"), sd), **tx_vars(resolved.get("second"), sd, "second_"), "foreign_customer": "CLI-ZZZZ9999ZZZZ"}
            app.state.controller.reference_date = sd
            app.state.faults = set()
            client.cookies.clear()
            state = {"conv": None, "old_token": None, "last": None, "password": password, "convs": []}

            def login():
                client.get("/api/auth/csrf")
                r = client.post("/api/auth/login", json={"username": username, "password": password},
                                headers={"X-CSRF-Token": client.cookies.get("csrf_token", "")})
                assert r.status_code == 200, r.text

            def new_conv(link: bool = False):
                body = {"language": case.language}
                if link and state.get("conv"):
                    body["previous_conversation_id"] = state["conv"]
                r = client.post("/api/conversations", json=body,
                                headers={"X-CSRF-Token": client.cookies.get("csrf_token", ""), "Idempotency-Key": str(uuid.uuid4())})
                assert r.status_code == 201, r.text
                state["conv"] = r.json()["conversation_id"]
                state["convs"].append(state["conv"])

            try:
                login()
                new_conv()
                for i, step in enumerate(case.steps):
                    rec = runner._step(client, case, step, i, vars_, resolved, state, login, new_conv, username)
                    if rec and rec.kind in ("message", "action") and rec.status != 200:
                        break
            except Exception:                    # noqa: BLE001 — una conversación a medias también es historia válida
                stats["skipped_error"] += 1
            finally:
                # el usuario sintético no puede iniciar sesión después: nadie entra a esas cuentas
                admin.execute("UPDATE app.users SET is_active = false WHERE username = %s", (username,))
            ids = state["convs"]
            if not ids:
                continue
            delta = timedelta(days=rng.random() * days, minutes=rng.randrange(0, 600))
            admin.execute("UPDATE app.conversations SET origin = 'synthetic' WHERE conversation_id = ANY(%s)", (ids,))
            if rng.random() < 0.3:               # valoración en ~30 %: más 👎 cuando terminó en una persona o sin acción
                conv = admin.execute("""SELECT c.conversation_id, c.customer_id, c.session_id,
                                               EXISTS (SELECT 1 FROM app.dispute_cases d WHERE d.conversation_id = c.conversation_id) AS has_case,
                                               (SELECT turn_id FROM app.turns t WHERE t.conversation_id = c.conversation_id AND t.role = 'assistant' ORDER BY seq DESC LIMIT 1) AS last_turn
                                        FROM app.conversations c WHERE c.conversation_id = %s""", (ids[-1],)).fetchone()
                down = rng.random() < (0.12 if conv["has_case"] else 0.4)
                admin.execute("""INSERT INTO app.feedback (feedback_id, conversation_id, customer_id, session_id, last_turn_id, rating, category)
                                 VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (conversation_id) DO NOTHING""",
                              (f"fb_{uuid.uuid4().hex[:20]}", conv["conversation_id"], conv["customer_id"], conv["session_id"], conv["last_turn"],
                               "down" if down else "up", rng.choice(["no_me_entendio", "respuesta_incorrecta", "lento", "otro"]) if down else None))
                stats["feedback"] += 1
            for table, cols in DATED.items():
                sets = ", ".join(f"{c} = {c} - %(d)s" for c in cols)
                admin.execute(f"UPDATE app.{table} SET {sets} WHERE conversation_id = ANY(%(ids)s)", {"d": delta, "ids": ids})
            admin.execute("""UPDATE app.ticket_events SET created_at = created_at - %(d)s
                             WHERE handoff_id IN (SELECT handoff_id FROM app.handoffs WHERE conversation_id = ANY(%(ids)s))""", {"d": delta, "ids": ids})
            stats["conversations"] += len(ids)
            if stats["conversations"] % 25 < len(ids):
                print(f"   {stats['conversations']} conversaciones…", flush=True)
    admin.close()
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=300, help="conversaciones a sembrar (por defecto 300)")
    ap.add_argument("--days", type=int, default=30, help="se reparten en los últimos N días (por defecto 30)")
    ap.add_argument("--seed", type=int, default=20261003)
    ap.add_argument("--llm", action="store_true", help="usa el LLM configurado en vez del falso (cuesta tokens o cupo)")
    ap.add_argument("--reset", action="store_true", help="borra todas las conversaciones sintéticas y sus usuarios sint_")
    a = ap.parse_args(argv)
    env = local_env()
    if a.reset:
        from data_pipeline.run import migrate
        migrate(env["ADMIN_DATABASE_URL"])
        with psycopg.connect(plain(env["ADMIN_DATABASE_URL"]), row_factory=dict_row) as conn:
            print(f"borradas {reset(conn)} conversaciones sintéticas")
        return 0
    stats = seed(a.n, a.days, a.seed, a.llm, env)
    print(f"sembradas {stats['conversations']} conversaciones sintéticas ({stats['feedback']} con valoración) en los últimos {a.days} días; "
          f"omitidas: {stats['skipped_demo']} por ser clientes demo, {stats['skipped_error']} por error o selector sin filas. "
          "Borrarlas: scripts/seed_synthetic_history.py --reset")
    return 0


if __name__ == "__main__":
    sys.exit(main())
