#!/usr/bin/env bash
# preDeployCommand de Render: roles de la base (idempotente) y migraciones, antes de cada despliegue.
# Si algo falla, Render no publica la versión nueva y deja la anterior corriendo.
set -euo pipefail
cd "$(dirname "$0")/../.."
urls="$(python infra/render/db_urls.py --export)"   # si falta una variable, falla aquí (set -e) y no arranca con otra base
eval "$urls"
python infra/render/roles.py
python -m alembic -c backend/alembic.ini upgrade head
echo "migraciones al día"
# usuarios demo: solo si la carga del subconjunto demo ya corrió (scripts/render_load_demo.sh) y hay DEMO_PASSWORD
python - <<'PY'
import os, subprocess, sys
import psycopg
url = os.environ["ADMIN_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
with psycopg.connect(url) as c:
    n = c.execute("SELECT count(*) FROM ref.demo_customers").fetchone()[0]
if n and os.environ.get("DEMO_PASSWORD"):
    sys.exit(subprocess.run([sys.executable, "scripts/seed_demo_users.py"]).returncode)
print(f"usuarios demo: nada que hacer (clientes demo cargados: {n})")
PY
