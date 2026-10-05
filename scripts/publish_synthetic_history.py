"""Lleva las conversaciones SINTÉTICAS de la base local a otra base (la de Render), para que la demo muestre el panel de
administración y la bandeja de agentes con volumen. Tres pasos; los dos primeros son locales.

    .venv/bin/python scripts/publish_synthetic_history.py lifecycle                 # 1. tickets con un ciclo de vida realista
    .venv/bin/python scripts/publish_synthetic_history.py export                    # 2. → data/synthetic_history.json.gz
    RENDER_ADMIN_DATABASE_URL="$(cat ~/.render_db_url)" \\
      .venv/bin/python scripts/publish_synthetic_history.py load --confirm-database <nombre de la base>   # 3. carga
    RENDER_ADMIN_DATABASE_URL=… .venv/bin/python scripts/publish_synthetic_history.py refresh --confirm-database <nombre>
    RENDER_ADMIN_DATABASE_URL=… .venv/bin/python scripts/publish_synthetic_history.py remove  --confirm-database <nombre>

Qué hace cada uno
- lifecycle: los tickets sembrados por seed_synthetic_history.py quedan todos «nuevos» y sin atender, así que con el tiempo se ven
  vencidos. Aquí cada uno recibe una primera respuesta dentro del plazo, una nota y una resolución, a nombre de los agentes de
  demostración; unos pocos se resuelven tarde (un servicio real no es perfecto). Por defecto no queda ninguno abierto: así la
  muestra no se estropea sola si nadie la mira durante días. `--open N` deja N abiertos (la mitad en curso, la mitad nuevos) para
  una demostración en vivo; esos hay que refrescarlos (`refresh`) antes de mostrarlos.
- export: escribe las conversaciones sintéticas con todo lo que cuelga de ellas (turnos, trazas, reclamos, traspasos, historial,
  bloqueos, valoraciones y sus usuarios `sint_…`, desactivados). El archivo queda en data/ (fuera de git).
- load: inserta el archivo en la base de destino en una sola transacción y corre las fechas para que la conversación más
  reciente sea de hace unos minutos (los tickets abiertos, si los hay, quedan recién creados).
- refresh: vuelve a correr todas las fechas sintéticas hasta hoy. Los paneles miran los últimos 7 o 30 días: si pasa el tiempo
  y la muestra se ve vacía, correr esto.
- remove: borra de la base de destino todo lo sintético.

Qué garantiza
- Todo sigue marcado (`app.conversations.origin = 'synthetic'`): la analítica lo separa y los tickets llevan la etiqueta.
- load / refresh / remove exigen `--confirm-database` con el nombre exacto de la base de destino, y la URL solo llega por la
  variable de entorno (no se imprime). load se niega si el destino ya tiene conversaciones sintéticas (usar remove antes).
- Solo escribe filas sintéticas: no toca clientes demo, conversaciones reales ni datos de referencia. Los clientes y movimientos
  de estas conversaciones son del dataset local; si el destino tiene otro subconjunto, «comercios con más reclamos» no los cuenta.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import random
import sys
import tomllib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

import psycopg
from dotenv import dotenv_values
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

REPO = Path(__file__).resolve().parents[1]
DEFAULT_FILE = REPO / "data" / "synthetic_history.json.gz"
SLA_HOURS = tomllib.loads((REPO / "backend" / "config" / "tickets.toml").read_text(encoding="utf-8"))["sla_hours"]
OPEN_TICKETS = 0                                  # por defecto todos resueltos: un ticket abierto se vence solo con las horas
LATE_TICKETS = 3                                  # resueltos fuera de plazo, entre los de hace más de una semana
SYNTH = "SELECT conversation_id FROM app.conversations WHERE origin = 'synthetic'"
# orden de inserción (claves foráneas) → condición que elige las filas sintéticas
TABLES = [
    ("users", "username LIKE 'sint\\_%%'"),
    ("sessions", "user_id IN (SELECT user_id FROM app.users WHERE username LIKE 'sint\\_%%')"),
    ("conversations", "origin = 'synthetic'"),
    ("turns", f"conversation_id IN ({SYNTH})"),
    ("confirmation_tokens", f"conversation_id IN ({SYNTH})"),
    ("traces", f"conversation_id IN ({SYNTH})"),
    ("handoffs", f"conversation_id IN ({SYNTH})"),
    ("ticket_events", f"handoff_id IN (SELECT handoff_id FROM app.handoffs WHERE conversation_id IN ({SYNTH}))"),
    ("dispute_cases", f"conversation_id IN ({SYNTH})"),
    ("card_status_overrides", f"conversation_id IN ({SYNTH})"),
    ("feedback", f"conversation_id IN ({SYNTH})"),
]
ORDER_BY = {"turns": "conversation_id, seq", "traces": "created_at, turn_id, step_seq", "ticket_events": "event_id", "conversations": "created_at"}
# columnas de fecha que se corren juntas al cargar (por conversación)
DATED = {"conversations": ("created_at", "updated_at", "closed_at"), "turns": ("created_at",), "traces": ("created_at",),
         "handoffs": ("created_at", "updated_at", "first_response_at", "resolved_at"),
         "dispute_cases": ("created_at", "updated_at", "confirmed_at"), "card_status_overrides": ("created_at",), "feedback": ("created_at",)}
NOTES = {
    "riesgo_alto": "Llamé al cliente: confirma que no hizo la compra. La tarjeta queda bloqueada y el caso pasa a investigación de fraude.",
    "riesgo_desconocido": "Revisé el movimiento con el cliente; no lo reconoce. Abrí el reclamo y recomendé reponer la tarjeta.",
    "fuera_de_plazo": "El cargo supera el plazo del canal digital. Tomé la declaración del cliente y abrí la gestión por excepción.",
    "pide_humano": "Hablé con el cliente y resolví su consulta. No hizo falta abrir un reclamo.",
    "aclaracion_agotada": "Ubiqué el movimiento con el cliente por teléfono (lo recordaba con otro monto) y registré el reclamo.",
    "reposicion_tarjeta": "Solicité la reposición de la tarjeta; llega en 5 días hábiles a la dirección registrada.",
    "cargo_pendiente_no_reconocido": "El cargo sigue pendiente. Quedó en seguimiento del equipo de fraude y la tarjeta, bloqueada por precaución.",
}


def plain(url: str) -> str:
    for prefix in ("postgresql+psycopg://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix):]
    return url


def local_db() -> psycopg.Connection:
    env = {**dotenv_values(REPO / ".env"), **os.environ}
    url = env.get("ADMIN_DATABASE_URL")
    if not url:
        raise SystemExit("falta ADMIN_DATABASE_URL (.env): correr primero scripts/dev_up.sh")
    if (urlsplit(plain(url)).hostname or "") not in ("localhost", "127.0.0.1", "::1", "postgres", "db"):
        raise SystemExit("lifecycle y export trabajan sobre la base LOCAL; ADMIN_DATABASE_URL no lo es")
    return psycopg.connect(plain(url), row_factory=dict_row)


def target_db(env_var: str, confirm: str | None) -> psycopg.Connection:
    url = os.environ.get(env_var)
    if not url:
        raise SystemExit(f"falta {env_var} en el entorno (la URL de la base de destino; no se imprime)")
    name = urlsplit(plain(url)).path.lstrip("/")
    if confirm != name:
        raise SystemExit(f"para escribir en la base de destino, repetir con --confirm-database y su nombre exacto (termina en …{name[-4:]})")
    return psycopg.connect(plain(url), row_factory=dict_row, connect_timeout=20)


# ------------------------------------------------------------------ 1. ciclo de vida
def lifecycle(conn, seed: int = 20261004, open_tickets: int = OPEN_TICKETS) -> dict:
    rng = random.Random(seed)
    agents = conn.execute("SELECT user_id, username FROM app.users WHERE role = 'analyst' AND is_active ORDER BY username").fetchall()
    if not agents:
        raise SystemExit("no hay agentes (rol analyst) activos: correr scripts/seed_demo_users.py")
    tickets = conn.execute(f"""SELECT handoff_id, reason_code, priority, created_at FROM app.handoffs
                               WHERE conversation_id IN ({SYNTH}) ORDER BY created_at DESC, handoff_id""").fetchall()
    if not tickets:
        raise SystemExit("no hay tickets sintéticos: correr primero scripts/seed_synthetic_history.py")
    ids = [t["handoff_id"] for t in tickets]
    conn.execute("DELETE FROM app.ticket_events WHERE handoff_id = ANY(%s)", (ids,))
    stay_open = [t["handoff_id"] for t in tickets if t["priority"] != "urgente"][:open_tickets]       # los más recientes
    week_ago = max(t["created_at"] for t in tickets) - timedelta(days=8)
    late = {t["handoff_id"] for t in [t for t in tickets if t["created_at"] < week_ago and t["priority"] == "media"][:LATE_TICKETS]}

    def event(hid, agent, kind, old, new, at, note=None):
        conn.execute("""INSERT INTO app.ticket_events (handoff_id, actor_user_id, actor_username, kind, from_value, to_value, note, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""", (hid, agent["user_id"], agent["username"], kind, old, new, note, at))

    stats = {"resueltos": 0, "resueltos_tarde": 0, "en_curso": 0, "nuevos": 0}
    for i, t in enumerate(tickets):
        hid, created, sla = t["handoff_id"], t["created_at"], float(SLA_HOURS.get(t["priority"], SLA_HOURS["media"]))
        agent = agents[i % len(agents)]
        first = created + timedelta(hours=min(0.5 * sla, 3.5) * rng.uniform(0.15, 1.0))                 # siempre dentro de 4 h (SLO)
        if hid in stay_open and stay_open.index(hid) % 2 == 1:                                           # nuevo, sin asignar
            conn.execute("""UPDATE app.handoffs SET ticket_status = 'nuevo', status = 'pendiente', assigned_to = NULL,
                            first_response_at = NULL, resolved_at = NULL, updated_at = created_at WHERE handoff_id = %s""", (hid,))
            stats["nuevos"] += 1
            continue
        event(hid, agent, "asignacion", None, agent["username"], first - timedelta(minutes=rng.randint(1, 4)))
        event(hid, agent, "estado", "nuevo", "en_curso", first)
        if hid in stay_open:                                                                              # en curso, ya atendido
            conn.execute("""UPDATE app.handoffs SET ticket_status = 'en_curso', status = 'tomado', assigned_to = %s,
                            first_response_at = %s, resolved_at = NULL, updated_at = %s WHERE handoff_id = %s""", (agent["user_id"], first, first, hid))
            stats["en_curso"] += 1
            continue
        resolved = created + timedelta(hours=sla * (rng.uniform(1.15, 1.5) if hid in late else rng.uniform(0.4, 0.9)))
        resolved = max(resolved, first + timedelta(minutes=10))
        event(hid, agent, "nota", None, None, first + (resolved - first) * rng.uniform(0.3, 0.8), NOTES.get(t["reason_code"], NOTES["pide_humano"]))
        event(hid, agent, "estado", "en_curso", "resuelto", resolved)
        conn.execute("""UPDATE app.handoffs SET ticket_status = 'resuelto', status = 'cerrado', assigned_to = %s,
                        first_response_at = %s, resolved_at = %s, updated_at = %s WHERE handoff_id = %s""", (agent["user_id"], first, resolved, resolved, hid))
        stats["resueltos_tarde" if hid in late else "resueltos"] += 1
    conn.commit()
    return stats


# ------------------------------------------------------------------ 2. exportar
def export(conn, path: Path) -> dict:
    data: dict = {"exported_at": datetime.now(timezone.utc).isoformat(), "tables": {}, "staff": {},
                  "schema_version": conn.execute("SELECT version_num FROM alembic_version").fetchone()["version_num"]}
    for table, where in TABLES:
        order = ORDER_BY.get(table, "1")
        data["tables"][table] = conn.execute(f"SELECT * FROM app.{table} WHERE {where} ORDER BY {order}").fetchall()   # noqa: S608 (constantes)
    staff_ids = {h["assigned_to"] for h in data["tables"]["handoffs"] if h["assigned_to"]} | {e["actor_user_id"] for e in data["tables"]["ticket_events"]}
    for r in conn.execute("SELECT user_id, username FROM app.users WHERE user_id = ANY(%s)", (list(staff_ids),)).fetchall():
        data["staff"][r["user_id"]] = r["username"]                # en el destino, los agentes tienen otro user_id: se busca por nombre
    if not data["tables"]["conversations"]:
        raise SystemExit("no hay conversaciones sintéticas que exportar")
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, default=str)
    return {t: len(rows) for t, rows in data["tables"].items()}


# ------------------------------------------------------------------ 3. cargar, refrescar, quitar
def columns(conn, table: str) -> dict[str, dict]:
    rows = conn.execute("""SELECT column_name, data_type, column_default, is_identity FROM information_schema.columns
                           WHERE table_schema = 'app' AND table_name = %s""", (table,)).fetchall()
    return {r["column_name"]: r for r in rows}


def synthetic_count(conn) -> int:
    has = conn.execute("""SELECT 1 FROM information_schema.columns WHERE table_schema = 'app' AND table_name = 'conversations'
                          AND column_name = 'origin'""").fetchone()
    if not has:
        raise SystemExit("la base de destino no tiene app.conversations.origin: desplegar primero la versión con la migración 0012")
    return conn.execute("SELECT count(*) AS n FROM app.conversations WHERE origin = 'synthetic'").fetchone()["n"]


def refresh(conn, seed: int = 20261004) -> dict:
    """Corre todas las fechas sintéticas para que la conversación más reciente sea de hace 15 minutos, y deja los tickets abiertos
    recién creados: en curso, con 10–40 % de su plazo consumido; nuevos (sin respuesta), de hace menos de 2 h (el objetivo de
    primera respuesta es de 4 h)."""
    rng = random.Random(seed)
    now = datetime.now(timezone.utc)
    all_ids = [r["conversation_id"] for r in conn.execute(SYNTH).fetchall()]
    if not all_ids:
        return {"conversaciones": 0, "tickets_abiertos": 0}
    newest = conn.execute(f"SELECT max(created_at) AS m FROM app.conversations WHERE conversation_id IN ({SYNTH})").fetchone()["m"]
    shift_conversations(conn, all_ids, now - timedelta(minutes=15) - newest)
    tickets = conn.execute(f"""SELECT handoff_id, conversation_id, priority, ticket_status, created_at FROM app.handoffs
                               WHERE conversation_id IN ({SYNTH}) AND ticket_status <> 'resuelto' ORDER BY handoff_id""").fetchall()
    for t in tickets:
        sla = float(SLA_HOURS.get(t["priority"], SLA_HOURS["media"]))
        age = timedelta(hours=min(sla * 0.4, 2.0) * rng.uniform(0.2, 1.0)) if t["ticket_status"] == "nuevo" else timedelta(hours=sla * rng.uniform(0.1, 0.4))
        shift_conversations(conn, [t["conversation_id"]], (now - age) - t["created_at"])
    return {"conversaciones": len(all_ids), "tickets_abiertos": len(tickets)}


def shift_conversations(conn, conversation_ids: list[str], delta: timedelta) -> None:
    p = {"d": delta, "ids": conversation_ids}
    for table, cols in DATED.items():
        sets = ", ".join(f"{c} = {c} + %(d)s" for c in cols)
        conn.execute(f"UPDATE app.{table} SET {sets} WHERE conversation_id = ANY(%(ids)s)", p)
    conn.execute("""UPDATE app.ticket_events SET created_at = created_at + %(d)s
                    WHERE handoff_id IN (SELECT handoff_id FROM app.handoffs WHERE conversation_id = ANY(%(ids)s))""", p)


def load(conn, path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        data = json.load(f)
    if synthetic_count(conn):
        raise SystemExit("el destino ya tiene conversaciones sintéticas: correr antes `remove` (o `refresh` si solo hay que actualizar fechas)")
    ids = [c["conversation_id"] for c in data["tables"]["conversations"]]
    clash = conn.execute("SELECT count(*) AS n FROM app.conversations WHERE conversation_id = ANY(%s)", (ids,)).fetchone()["n"]
    if clash:
        raise SystemExit(f"{clash} conversaciones del archivo ya existen en el destino: no se carga nada")
    staff = {}                                    # user_id local → user_id del destino, por nombre de usuario
    for local_id, username in data["staff"].items():
        row = conn.execute("SELECT user_id FROM app.users WHERE username = %s AND role IN ('analyst', 'admin')", (username,)).fetchone()
        if row is None:
            raise SystemExit(f"en el destino no existe el agente «{username}»: crear los usuarios demo antes (scripts/seed_demo_users.py)")
        staff[local_id] = row["user_id"]
    counts = {}
    for table, _ in TABLES:
        rows = data["tables"][table]
        cols = columns(conn, table)
        auto = {c for c, m in cols.items() if m["is_identity"] == "YES" or (m["column_default"] or "").startswith("nextval")}
        if not rows:
            counts[table] = 0
            continue
        missing = [c for c in rows[0] if c not in cols]
        if missing:
            raise SystemExit(f"app.{table} del destino no tiene las columnas {missing}: desplegar primero la misma versión del esquema")
        use = [c for c in rows[0] if c not in auto]
        out = []
        for r in rows:
            r = dict(r)
            if table == "handoffs" and r.get("assigned_to"):
                r["assigned_to"] = staff[r["assigned_to"]]
            if table == "ticket_events":
                r["actor_user_id"] = staff[r["actor_user_id"]]
            if table == "sessions":
                r["revoked_at"] = r.get("revoked_at") or r["created_at"]       # sesiones de usuarios sintéticos: nunca válidas
            if table == "users":
                r["is_active"] = False
            out.append([Jsonb(r[c]) if cols[c]["data_type"] in ("json", "jsonb") and r[c] is not None else r[c] for c in use])
        with conn.cursor() as cur:
            cur.executemany(f"INSERT INTO app.{table} ({', '.join(use)}) VALUES ({', '.join(['%s'] * len(use))})", out)
        counts[table] = len(out)
    counts["tickets_abiertos"] = refresh(conn)["tickets_abiertos"]            # fechas hasta hoy: la más reciente, hace 15 minutos
    conn.commit()
    return counts


def remove(conn) -> int:
    sys.path.insert(0, str(REPO / "scripts"))
    from seed_synthetic_history import reset
    synthetic_count(conn)
    n = reset(conn)
    conn.commit()
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    lc = sub.add_parser("lifecycle", help="tickets sintéticos locales con primera respuesta, nota y resolución")
    lc.add_argument("--open", type=int, default=OPEN_TICKETS, dest="open_tickets", help="tickets que quedan abiertos (por defecto 0; hay que refrescarlos)")
    e = sub.add_parser("export", help="escribe las conversaciones sintéticas locales en un archivo")
    e.add_argument("--file", type=Path, default=DEFAULT_FILE)
    for name, text_ in (("load", "carga el archivo en la base de destino"), ("refresh", "corre las fechas sintéticas del destino hasta hoy"),
                        ("remove", "borra lo sintético del destino")):
        s = sub.add_parser(name, help=text_)
        s.add_argument("--target-env", default="RENDER_ADMIN_DATABASE_URL", help="variable de entorno con la URL del dueño de la base de destino")
        s.add_argument("--confirm-database", help="nombre exacto de la base de destino")
        if name == "load":
            s.add_argument("--file", type=Path, default=DEFAULT_FILE)
    a = ap.parse_args(argv)
    if a.cmd == "lifecycle":
        with local_db() as conn:
            print("tickets sintéticos locales:", ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in lifecycle(conn, open_tickets=a.open_tickets).items()))
    elif a.cmd == "export":
        with local_db() as conn:
            counts = export(conn, a.file)
        print(f"exportado a {a.file}: " + ", ".join(f"{n} {t}" for t, n in counts.items()))
    else:
        with target_db(a.target_env, a.confirm_database) as conn:
            if a.cmd == "load":
                counts = load(conn, a.file)
                print("cargado en el destino: " + ", ".join(f"{n} {t}" for t, n in counts.items()))
            elif a.cmd == "refresh":
                r = refresh(conn)
                conn.commit()
                print(f"{r['conversaciones']} conversaciones sintéticas con fechas hasta hoy; {r['tickets_abiertos']} tickets abiertos como recién creados")
            else:
                print(f"borradas {remove(conn)} conversaciones sintéticas del destino")
    return 0


if __name__ == "__main__":
    sys.exit(main())
