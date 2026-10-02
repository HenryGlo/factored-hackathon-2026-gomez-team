#!/usr/bin/env bash
# Prueba de humo del entorno prodlike (docs/prodlike.md). Requiere scripts/prodlike_up.sh corriendo.
#
#   scripts/prodlike_smoke.sh               # recorridos por HTTP a través del proxy (cliente, agente, admin, límite 429)
#   scripts/prodlike_smoke.sh --image       # además construye la IMAGEN de producción y la prueba con LLM_PROVIDER=fake
#   scripts/prodlike_smoke.sh --md out.md   # escribe la tabla de resultados en Markdown
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
PRIMARY="$(cd "$(git rev-parse --git-common-dir)/.." && pwd)"
STATE="${PRODLIKE_HOME:-$HOME/.factored-prodlike}"
[[ -f "$STATE/env" ]] || { echo "prodlike no está levantado: scripts/prodlike_up.sh" >&2; exit 1; }
PY="$PRIMARY/.venv/bin/python"; [[ -x "$PY" ]] || PY="$STATE/venv/bin/python"
HTTPS_PORT="${PRODLIKE_HTTPS_PORT:-8443}"; DB_PORT="${PRODLIKE_DB_PORT:-5544}"
IMAGE=""; ARGS=()
for a in "$@"; do if [[ "$a" == "--image" ]]; then IMAGE=1; else ARGS+=("$a"); fi; done

rc=0
if [[ -n "$IMAGE" ]]; then
  echo "== imagen de producción (infra/render/backend.Dockerfile) con LLM_PROVIDER=fake"
  docker build -q -t disputas-backend:prodlike -f infra/render/backend.Dockerfile . >/dev/null
  set -a; source "$STATE/env"; set +a
  docker rm -f prodlike-image-smoke >/dev/null 2>&1 || true
  # misma base prodlike, vista desde el contenedor; las contraseñas viajan por entorno, no por la línea de comandos
  ADMIN_DATABASE_URL="postgresql://bank_owner:${PRODLIKE_OWNER_PASSWORD}@host.docker.internal:${DB_PORT}/bank_prodlike" \
  docker run -d --name prodlike-image-smoke --add-host host.docker.internal:host-gateway -p 127.0.0.1:8101:8000 \
    --env-file infra/render/prod.env -e LLM_PROVIDER=fake -e ADMIN_DATABASE_URL -e APP_DB_PASSWORD -e CONSOLE_DB_PASSWORD \
    -e APP_DB_USER=bank_app -e CONSOLE_DB_USER=bank_console disputas-backend:prodlike >/dev/null
  ok=""
  for _ in $(seq 1 30); do curl -sf 127.0.0.1:8101/api/ready 2>/dev/null | grep -q '"status":"ready"' && { ok=1; break; }; sleep 1; done
  if [[ -n "$ok" ]]; then
    models="$(docker exec prodlike-image-smoke sh -c 'ls models/intent/*.joblib models/risk/*.json | wc -l' | tr -d ' ')"
    user="$(docker exec prodlike-image-smoke id -un)"
    size="$(docker image inspect disputas-backend:prodlike --format '{{.Size}}' | awk '{printf "%.0f MB", $1/1000000}')"
    echo "✔ Imagen de producción: /api/ready responde con la base prodlike; $models artefactos en models/; usuario $user; $size"
  else
    echo "✘ Imagen de producción: no respondió /api/ready"; docker logs prodlike-image-smoke 2>&1 | tail -n 15; rc=1
  fi
  docker rm -f prodlike-image-smoke >/dev/null 2>&1 || true
fi

"$PY" scripts/prodlike_smoke.py --url "https://localhost:${HTTPS_PORT}" ${ARGS[@]+"${ARGS[@]}"} || rc=1
exit $rc
