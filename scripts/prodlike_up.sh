#!/usr/bin/env bash
# Entorno "prodlike": el sistema completo en local, lo más parecido a producción (docs/prodlike.md).
#
#   scripts/prodlike_up.sh          # toma lo último de origin/main y lo levanta
#   scripts/prodlike_up.sh --here   # usa el código de esta carpeta tal como está (para probar una rama)
#   scripts/prodlike_down.sh        # lo apaga (los datos quedan; --purge los borra)
#
# - Código: origin/main en un worktree propio (../factored-prodlike). Cada corrida toma lo último que se fusionó.
# - PostgreSQL propio (contenedor factored-prodlike, base bank_prodlike, puerto 5544), con los MISMOS scripts que Render:
#   infra/render/predeploy.sh (roles + migraciones + usuarios demo) y la carga del subconjunto demo de 200 clientes.
# - Backend con el arranque de producción (infra/render/start.sh) y la configuración de infra/render/prod.env, conectado
#   con el usuario de la app. Único cambio: LLM_PROVIDER=claude_cli (hoy no hay crédito de API).
# - Frontend: build de producción servido por Caddy en un solo origen con TLS; /api va al backend.
# - No toca el entorno de desarrollo (tmux factored-dev, base "bank", puertos 8000/5173/5174).
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
PRIMARY="$(cd "$(git -C "$HERE" rev-parse --git-common-dir)/.." && pwd)"      # carpeta principal del repo (tiene .venv y el dataset)
STATE="${PRODLIKE_HOME:-$HOME/.factored-prodlike}"; mkdir -p "$STATE"; chmod 700 "$STATE"
DB_PORT="${PRODLIKE_DB_PORT:-5544}"; BACKEND_PORT="${PRODLIKE_BACKEND_PORT:-8100}"; HTTPS_PORT="${PRODLIKE_HTTPS_PORT:-8443}"
SESSION=factored-prodlike

if [[ "${1:-}" != "--here" && -z "${PRODLIKE_INNER:-}" ]]; then
  WT="$(dirname "$PRIMARY")/factored-prodlike"
  echo "== código: origin/main"
  git -C "$PRIMARY" fetch -q origin main
  if [[ -d "$WT" ]]; then git -C "$WT" checkout -q --detach origin/main; else git -C "$PRIMARY" worktree add -q --detach "$WT" origin/main; fi
  echo "   $(git -C "$WT" log --oneline -1)"
  PRODLIKE_INNER=1 exec "$WT/scripts/prodlike_up.sh"
fi
ROOT="$HERE"; cd "$ROOT"
for bin in docker tmux npm; do command -v "$bin" >/dev/null 2>&1 || { echo "falta $bin" >&2; exit 1; }; done

# ---- entorno de Python: el de la carpeta principal; si no existe, uno propio
if [[ -x "$PRIMARY/.venv/bin/python" ]]; then VENV="$PRIMARY/.venv"; else VENV="$STATE/venv"; [[ -x "$VENV/bin/python" ]] || python3 -m venv "$VENV"; fi
"$VENV/bin/pip" install -q --disable-pip-version-check -r requirements.txt
export PATH="$VENV/bin:$PATH"

# ---- secretos locales del entorno (fuera del repo, permisos 600). Nunca se imprimen.
if [[ ! -f "$STATE/env" ]]; then
  demo="$(grep -s '^DEMO_PASSWORD=' "$PRIMARY/.env" | cut -d= -f2- || true)"
  python - "$STATE/env" "$demo" <<'PY'
import secrets, sys
path, demo = sys.argv[1], sys.argv[2]
vals = {"PRODLIKE_OWNER_PASSWORD": secrets.token_urlsafe(24), "APP_DB_PASSWORD": secrets.token_urlsafe(24),
        "CONSOLE_DB_PASSWORD": secrets.token_urlsafe(24), "DEMO_PASSWORD": demo or secrets.token_urlsafe(12)}
open(path, "w").write("".join(f"{k}={v}\n" for k, v in vals.items()))
PY
  chmod 600 "$STATE/env"
fi
set -a; source "$STATE/env"; source infra/render/prod.env; set +a
export APP_DB_USER=bank_app CONSOLE_DB_USER=bank_console
export ADMIN_DATABASE_URL="postgresql://bank_owner:${PRODLIKE_OWNER_PASSWORD}@127.0.0.1:${DB_PORT}/bank_prodlike"
export LLM_PROVIDER="${PRODLIKE_LLM_PROVIDER:-claude_cli}"      # producción: anthropic_api (docs/prodlike.md)

LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)"
SITES="https://localhost:${HTTPS_PORT}"; [[ -n "$LAN_IP" ]] && SITES="$SITES, https://${LAN_IP}:${HTTPS_PORT}"
export PRODLIKE_SITES="$SITES" PRODLIKE_DB_PORT="$DB_PORT" PRODLIKE_BACKEND_PORT="$BACKEND_PORT" PRODLIKE_HTTPS_PORT="$HTTPS_PORT"
export PRODLIKE_DIST="$ROOT/frontend/dist"
export PRODLIKE_DEFAULT_SNI="${LAN_IP:-localhost}"
COMPOSE=(docker compose -f infra/prodlike/docker-compose.yml)

echo "== PostgreSQL (bank_prodlike en :$DB_PORT)"
mkdir -p "$PRODLIKE_DIST"
"${COMPOSE[@]}" up -d postgres >/dev/null 2>&1
for _ in $(seq 1 40); do [[ "$("${COMPOSE[@]}" ps postgres --format '{{.Health}}' 2>/dev/null)" == healthy ]] && break; sleep 1; done

echo "== roles y migraciones (infra/render/predeploy.sh, el mismo de Render)"
bash infra/render/predeploy.sh | sed 's/^/   /'

n="$(python - <<'PY'
import os, psycopg
with psycopg.connect(os.environ["ADMIN_DATABASE_URL"]) as c:
    print(c.execute("SELECT count(*) FROM ref.demo_customers").fetchone()[0])
PY
)"
if [[ "$n" == 0 ]]; then
  if [[ -f "$PRIMARY/data/bank.duckdb" ]]; then
    echo "== datos: subconjunto demo de 200 clientes (la misma carga que scripts/render_load_demo.sh)"
    python -m data_pipeline.run full --skip-build --customers-sample 200 --duckdb "$PRIMARY/data/bank.duckdb" \
      --source "$PRIMARY/dataset/data" --database-url "${ADMIN_DATABASE_URL/postgresql:/postgresql+psycopg:}" 2>&1 | tail -n 2 | cut -c1-160 | sed 's/^/   /'
  else
    echo "== datos: no está data/bank.duckdb → dataset sintético"
    python scripts/dev_data.py --synthetic --database-url "${ADMIN_DATABASE_URL/postgresql:/postgresql+psycopg:}" | tail -n 1
  fi
  bash infra/render/predeploy.sh | tail -n 1 | sed 's/^/   /'       # ahora sí crea los usuarios demo
else
  echo "== datos: ya cargados ($n clientes demo)"
fi

echo "== frontend: build de producción"
( cd frontend && { [[ -d node_modules && node_modules -nt package-lock.json ]] || npm ci --silent; } && npm run build --silent 2>&1 | tail -n 3 | sed 's/^/   /' )

echo "== backend (infra/render/start.sh) en :$BACKEND_PORT, LLM_PROVIDER=$LLM_PROVIDER; log en $STATE/backend.log"
tmux kill-session -t "$SESSION" 2>/dev/null || true
for _ in $(seq 1 10); do lsof -tiTCP:"$BACKEND_PORT" -sTCP:LISTEN >/dev/null 2>&1 || break; sleep 1; done
# tmux no hereda el entorno de este script (lo da su servidor): se le pasa completo y explícito, sin el .env de desarrollo.
# start.sh deriva las URLs de la app y quita la del dueño.
python - "$STATE/run.env" <<'PY'
import os, shlex, sys
keep = [l.split("=", 1)[0] for l in open("infra/render/prod.env") if "=" in l and not l.startswith("#")]
keep += ["ADMIN_DATABASE_URL", "APP_DB_USER", "APP_DB_PASSWORD", "CONSOLE_DB_USER", "CONSOLE_DB_PASSWORD", "DEMO_PASSWORD", "PATH"]
fd = os.open(sys.argv[1], os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
os.write(fd, "".join(f"export {k}={shlex.quote(os.environ[k])}\n" for k in dict.fromkeys(keep)).encode())
os.close(fd)
PY
tmux new-session -d -s "$SESSION" -c "$ROOT" "source '$STATE/run.env' && PORT=$BACKEND_PORT bash infra/render/start.sh 2>&1 | tee '$STATE/backend.log'"

echo "== proxy (Caddy) en :$HTTPS_PORT"
"${COMPOSE[@]}" up -d --force-recreate proxy >/dev/null 2>&1
ok=""
for _ in $(seq 1 40); do curl -skf "https://localhost:${HTTPS_PORT}/api/ready" >/dev/null && { ok=1; break; }; sleep 1; done
# que no quede duda de a qué base y con qué proveedor arrancó
curl -sk "https://localhost:${HTTPS_PORT}/api/ready" | grep -q "\"llm_provider\":\"$LLM_PROVIDER\"" || ok=""
[[ -n "$ok" ]] || { echo "el backend no respondió; últimas líneas de $STATE/backend.log:" >&2; tail -n 20 "$STATE/backend.log" >&2; exit 1; }
git -C "$ROOT" log --oneline -1 > "$STATE/commit"

IPAD="(sin red local detectada)"; [[ -n "$LAN_IP" ]] && IPAD="https://${LAN_IP}:${HTTPS_PORT}"
cat <<MSG

Prodlike arriba · commit $(cat "$STATE/commit")
  Mac:   https://localhost:${HTTPS_PORT}
  iPad:  $IPAD   (misma red wifi; acepta el aviso del certificado local)
  Estado: $(curl -sk "https://localhost:${HTTPS_PORT}/api/ready")

Usuarios demo (contraseña: DEMO_PASSWORD en $STATE/env — no se imprime):
  demo_cargo_claro_1        cliente con un cargo claro: reclámalo de punta a punta
  demo_cargos_parecidos_1   cliente con dos cargos parecidos: el asistente pregunta cuál
  demo_fraude_alto_1        cliente con un cargo de riesgo alto: escala a fraude como ticket
  analista_1                agente de soporte: bandeja de tickets
  admin_1                   administrador: SLO, métricas y logs

Prueba de humo: scripts/prodlike_smoke.sh     Apagar: scripts/prodlike_down.sh     Guía: docs/prodlike.md
MSG
