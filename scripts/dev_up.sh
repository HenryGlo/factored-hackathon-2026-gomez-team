#!/usr/bin/env bash
# Entorno local completo con un comando: PostgreSQL (Docker), migraciones, backend en :8000 y frontend (Vite) en :5173.
#
#   scripts/dev_up.sh            # LLM_PROVIDER=claude_cli (claude -p) con la configuración del sistema
#   LLM_PROVIDER=fake scripts/dev_up.sh     # sin LLM (plantillas y reglas), p. ej. sin la CLI de Claude
#   scripts/dev_up.sh --seed     # además recrea los usuarios demo (DEMO_PASSWORD de .env)
#   scripts/dev_up.sh --reset-demo   # borra lo que la app creó para los clientes demo (conversaciones, reclamos, handoffs,
#                                    # bloqueos) para empezar una demo limpia. No toca ref.* ni los usuarios.
#
# Si ya hay algo escuchando en :8000 se reutiliza (no se levanta otro backend). Ctrl+C detiene lo que levantó el script.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="$ROOT/.venv/bin/python"
[[ -x "$PY" ]] || { echo "falta .venv: python -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2; exit 1; }
[[ -f .env ]] || { echo "falta .env: cp .env.example .env y completar" >&2; exit 1; }
LOGDIR="${TMPDIR:-/tmp}/disputas-dev"; mkdir -p "$LOGDIR"

echo "== PostgreSQL"
# Si ya hay un PostgreSQL del proyecto sano, no se toca: `up` desde otra carpeta (otro worktree) recrearía el contenedor
# (monta archivos por ruta absoluta) y cortaría las conexiones de otros procesos.
if docker ps --filter "name=factored-hackathon-postgres" --filter "health=healthy" --format '{{.Names}}' | grep -q postgres; then
  echo "   ya está corriendo; se reutiliza"
else
  docker compose --env-file .env -f infra/docker-compose.yml up -d >/dev/null
  for _ in $(seq 1 30); do
    docker compose --env-file .env -f infra/docker-compose.yml ps --format '{{.Health}}' 2>/dev/null | grep -q healthy && break
    sleep 1
  done
fi

echo "== migraciones"
( set -a; source .env; set +a; "$ROOT/.venv/bin/alembic" -c backend/alembic.ini upgrade head >/dev/null )
for arg in "$@"; do
  case "$arg" in
    --seed) "$PY" scripts/seed_demo_users.py ;;
    --reset-demo)
      echo "== limpiando datos de la app de los clientes demo"
      "$PY" - <<'PYEOF'
import os
import psycopg
from dotenv import load_dotenv
load_dotenv(".env")
url = os.environ["ADMIN_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
demo = "SELECT customer_id FROM ref.demo_customers"
conv = f"SELECT conversation_id FROM app.conversations WHERE customer_id IN ({demo})"
with psycopg.connect(url) as c:
    for sql in (f"DELETE FROM app.feedback WHERE customer_id IN ({demo})",
                f"DELETE FROM app.dispute_cases WHERE customer_id IN ({demo})",
                f"DELETE FROM app.card_status_overrides WHERE customer_id IN ({demo})",
                f"DELETE FROM app.handoffs WHERE customer_id IN ({demo})",
                f"DELETE FROM app.traces WHERE conversation_id IN ({conv})",
                f"DELETE FROM app.confirmation_tokens WHERE conversation_id IN ({conv})",
                f"UPDATE app.conversations SET previous_conversation_id = NULL WHERE previous_conversation_id IN ({conv})",
                f"DELETE FROM app.turns WHERE conversation_id IN ({conv})",
                f"DELETE FROM app.conversations WHERE customer_id IN ({demo})"):
        print(f"   {c.execute(sql).rowcount:>5}  {sql.split(' WHERE')[0]}")
PYEOF
      ;;
  esac
done

PIDS=()
cleanup() { for p in "${PIDS[@]:-}"; do kill "$p" 2>/dev/null || true; done; }
trap cleanup EXIT INT TERM

if lsof -tiTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "== backend: ya hay uno en :8000, se reutiliza"
else
  echo "== backend en :8000 (LLM_PROVIDER=${LLM_PROVIDER:-claude_cli}); log en $LOGDIR/backend.log"
  LLM_PROVIDER="${LLM_PROVIDER:-claude_cli}" INTENT_CLASSIFIER="${INTENT_CLASSIFIER:-llm}" CONFIRM_MODE="${CONFIRM_MODE:-template}" \
  CLARIFY_MODE="${CLARIFY_MODE:-auto}" LOG_FORMAT="${LOG_FORMAT:-text}" \
    "$ROOT/.venv/bin/uvicorn" --factory backend.app.main:create_app --host 127.0.0.1 --port 8000 > "$LOGDIR/backend.log" 2>&1 &
  PIDS+=($!)
  for _ in $(seq 1 30); do curl -sf 127.0.0.1:8000/api/health >/dev/null && break; sleep 1; done
  curl -s 127.0.0.1:8000/api/ready; echo
fi

echo "== frontend en http://localhost:5173"
cd frontend
[[ -d node_modules ]] || npm ci
npm run dev -- --host 127.0.0.1
