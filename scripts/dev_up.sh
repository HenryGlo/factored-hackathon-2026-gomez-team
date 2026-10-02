#!/usr/bin/env bash
# Entorno local completo con un comando: PostgreSQL (Docker), migraciones, backend en :8000 y frontend (Vite) en :5173.
#
#   scripts/dev_up.sh            # LLM_PROVIDER=claude_cli (claude -p) con la configuración del sistema
#   LLM_PROVIDER=fake scripts/dev_up.sh     # sin LLM (plantillas y reglas), p. ej. sin la CLI de Claude
#   scripts/dev_up.sh --synthetic   # primera vez sin el dataset del reto: carga el dataset sintético (clientes ficticios)
#   scripts/dev_up.sh --seed     # además recrea los usuarios demo (DEMO_PASSWORD de .env)
#   scripts/dev_up.sh --reset-demo   # borra lo que la app creó para los clientes demo (conversaciones, reclamos, handoffs,
#                                    # bloqueos) para empezar una demo limpia. No toca ref.* ni los usuarios.
#
# Desde cero no hace falta nada más que Docker, Python 3.12 y Node: si faltan .env, .venv, los datos o los usuarios demo,
# el script los crea (scripts/bootstrap_env.py, scripts/dev_data.py). Si no está el dataset del reto, usa el sintético.
# Si ya hay algo escuchando en :8000 se reutiliza (no se levanta otro backend). Ctrl+C detiene lo que levantó el script.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="$ROOT/.venv/bin/python"
# Desde cero, sin pasos manuales: .env con contraseñas generadas, entorno virtual y dependencias.
if [[ ! -f .env ]]; then
  echo "== .env"
  python3 scripts/bootstrap_env.py
fi
if [[ ! -x "$PY" ]]; then
  echo "== entorno virtual (.venv) y dependencias (1–2 minutos la primera vez)"
  python3 -m venv .venv
  "$ROOT/.venv/bin/pip" install -q --disable-pip-version-check -r requirements-dev.txt
fi
LOGDIR="${TMPDIR:-/tmp}/disputas-dev"; mkdir -p "$LOGDIR"
# Puertos y proyecto de Compose configurables, para levantar una segunda copia aislada (p. ej. probar un clon limpio).
BACKEND_PORT="${BACKEND_PORT:-8000}"; FRONTEND_PORT="${FRONTEND_PORT:-5173}"
PROJECT="${COMPOSE_PROJECT_NAME:-factored-hackathon}"
command -v docker >/dev/null 2>&1 || { echo "falta Docker (se usa para PostgreSQL)" >&2; exit 1; }
command -v npm >/dev/null 2>&1 || { echo "falta Node/npm (frontend)" >&2; exit 1; }

echo "== PostgreSQL"
# Si ya hay un PostgreSQL del proyecto sano, no se toca: `up` desde otra carpeta (otro worktree) recrearía el contenedor
# (monta archivos por ruta absoluta) y cortaría las conexiones de otros procesos.
if docker ps --filter "name=${PROJECT}-postgres" --filter "health=healthy" --format '{{.Names}}' | grep -q postgres; then
  echo "   ya está corriendo; se reutiliza"
else
  docker compose -p "$PROJECT" --env-file .env -f infra/docker-compose.yml up -d >/dev/null
  for _ in $(seq 1 30); do
    docker compose -p "$PROJECT" --env-file .env -f infra/docker-compose.yml ps --format '{{.Health}}' 2>/dev/null | grep -q healthy && break
    sleep 1
  done
  sleep 2   # el primer arranque reinicia el servidor tras crear los roles (init/01-roles.sh)
fi

echo "== migraciones"
( set -a; source .env; set +a; "$ROOT/.venv/bin/alembic" -c backend/alembic.ini upgrade head >/dev/null )
echo "== datos y usuarios demo"
SYNTH=""; for arg in "$@"; do [[ "$arg" == "--synthetic" ]] && SYNTH="--synthetic"; done
"$PY" scripts/dev_data.py $SYNTH
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
    for sql in (f"DELETE FROM app.voice_usage WHERE customer_id IN ({demo})",
                f"DELETE FROM app.ticket_events WHERE handoff_id IN (SELECT handoff_id FROM app.handoffs WHERE customer_id IN ({demo}))",
                f"DELETE FROM app.feedback WHERE customer_id IN ({demo})",
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

if lsof -tiTCP:"$BACKEND_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "== backend: ya hay uno en :$BACKEND_PORT, se reutiliza"
else
  # sin la CLI de Claude instalada, el backend arranca sin LLM (reglas y plantillas) en vez de fallar en cada turno
  if [[ -z "${LLM_PROVIDER:-}" ]] && ! command -v claude >/dev/null 2>&1; then
    echo "   no se encontró la CLI de Claude: se usa LLM_PROVIDER=fake (reglas y plantillas)"
    export LLM_PROVIDER=fake
  fi
  echo "== backend en :$BACKEND_PORT (LLM_PROVIDER=${LLM_PROVIDER:-claude_cli}); log en $LOGDIR/backend.log"
  LLM_PROVIDER="${LLM_PROVIDER:-claude_cli}" INTENT_CLASSIFIER="${INTENT_CLASSIFIER:-llm}" CONFIRM_MODE="${CONFIRM_MODE:-template}" \
  CLARIFY_MODE="${CLARIFY_MODE:-auto}" LOG_FORMAT="${LOG_FORMAT:-text}" \
    "$ROOT/.venv/bin/uvicorn" --factory backend.app.main:create_app --host 127.0.0.1 --port "$BACKEND_PORT" > "$LOGDIR/backend.log" 2>&1 &
  PIDS+=($!)
  for _ in $(seq 1 30); do curl -sf "127.0.0.1:$BACKEND_PORT/api/health" >/dev/null && break; sleep 1; done
  curl -sf "127.0.0.1:$BACKEND_PORT/api/ready" || { echo "el backend no arrancó; últimas líneas de $LOGDIR/backend.log:" >&2; tail -n 20 "$LOGDIR/backend.log" >&2; exit 1; }
  echo
fi

echo "== frontend en http://localhost:$FRONTEND_PORT"
cd frontend
[[ -d node_modules ]] || npm ci
# en segundo plano + wait: así un TERM al script también detiene a Vite (no solo Ctrl+C)
VITE_API_PROXY="http://127.0.0.1:$BACKEND_PORT" node_modules/.bin/vite --host 127.0.0.1 --port "$FRONTEND_PORT" --strictPort &
PIDS+=($!)
wait "$!"
