"""Crea (o actualiza) los usuarios demo: un cliente por fila de ref.demo_customers y 2 analistas.

    .venv/bin/python scripts/seed_demo_users.py [--database-url URL]

- Clientes: los de ref.demo_customers, que el ETL elige con una regla determinista por escenario
  (data_pipeline/etl/demo_customers.py). SQL usado (documentado en docs/data/postgres.md):

      SELECT d.customer_id, d.scenario, d.scenario_rank
      FROM ref.demo_customers d JOIN ref.customers c USING (customer_id)
      ORDER BY d.scenario, d.scenario_rank;

  Usuario = demo_<escenario>_<rank> (p. ej. demo_cargo_claro_1). No contiene el customer_id.
- Analistas: analista_1 y analista_2.
- La contraseña se lee de DEMO_PASSWORD (.env). Nunca se imprime ni se escribe en el repo.
- Idempotente: si el usuario existe se actualizan rol, cliente y nombre; la contraseña solo se
  vuelve a hashear si cambió. Los usuarios demo_* cuyo escenario ya no está en ref.demo_customers
  (p. ej. tras recargar con otro subconjunto) quedan inactivos.

Se conecta con ADMIN_DATABASE_URL (operación de administración, como el ETL).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.security import hash_password, new_id, verify_password  # noqa: E402

DEMO_SQL = """
SELECT d.customer_id, d.scenario, d.scenario_rank
FROM ref.demo_customers d JOIN ref.customers c USING (customer_id)
ORDER BY d.scenario, d.scenario_rank"""
ANALYSTS = [("analista_1", "Analista 1"), ("analista_2", "Analista 2")]
MIN_PASSWORD = 12


def upsert(cur, username: str, password: str, role: str, customer_id: str | None, display_name: str | None) -> str:
    row = cur.execute("SELECT user_id, password_hash FROM app.users WHERE lower(username) = lower(%s)", (username,)).fetchone()
    if row is None:
        cur.execute("""INSERT INTO app.users (user_id, username, password_hash, role, customer_id, display_name)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (new_id("usr"), username, hash_password(password), role, customer_id, display_name))
        return "creado"
    user_id, current = row
    new_hash = current if verify_password(password, current) else hash_password(password)
    cur.execute("""UPDATE app.users SET password_hash = %s, role = %s, customer_id = %s, display_name = %s,
                   is_active = true, updated_at = now() WHERE user_id = %s""",
                (new_hash, role, customer_id, display_name, user_id))
    return "actualizado" + ("" if new_hash == current else " (contraseña nueva)")


def main() -> int:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    ap = argparse.ArgumentParser()
    ap.add_argument("--database-url", default=os.environ.get("ADMIN_DATABASE_URL"))
    args = ap.parse_args()
    password = os.environ.get("DEMO_PASSWORD", "")
    if len(password) < MIN_PASSWORD:
        sys.exit(f"DEMO_PASSWORD debe estar en .env y tener al menos {MIN_PASSWORD} caracteres")
    if not args.database_url:
        sys.exit("falta ADMIN_DATABASE_URL")
    with psycopg.connect(args.database_url.replace("postgresql+psycopg://", "postgresql://")) as conn, conn.cursor() as cur:
        demo = cur.execute(DEMO_SQL).fetchall()
        if not demo:
            sys.exit("ref.demo_customers está vacía: correr antes `python -m data_pipeline.run full`")
        seen = []
        for customer_id, scenario, rank in demo:
            username = f"demo_{scenario}_{rank}"
            seen.append(username)
            print(f"{username:32s} {scenario:18s} {upsert(cur, username, password, 'customer', customer_id, None)}")
        for username, name in ANALYSTS:
            print(f"{username:32s} {'analyst':18s} {upsert(cur, username, password, 'analyst', None, name)}")
        stale = cur.execute("""UPDATE app.users SET is_active = false, updated_at = now()
                               WHERE role = 'customer' AND username LIKE 'demo\\_%%' AND is_active
                                 AND NOT (username = ANY(%s)) RETURNING username""", (seen,)).fetchall()
        for (u,) in stale:
            print(f"{u:32s} {'—':18s} desactivado (su escenario ya no está en ref.demo_customers)")
        conn.commit()
    print(f"{len(demo)} clientes demo y {len(ANALYSTS)} analistas. Contraseña: DEMO_PASSWORD de .env.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
