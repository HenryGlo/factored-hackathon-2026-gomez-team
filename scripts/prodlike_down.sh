#!/usr/bin/env bash
# Apaga el entorno prodlike (docs/prodlike.md). Los datos quedan en el volumen; con --purge se borran junto con los secretos locales.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
STATE="${PRODLIKE_HOME:-$HOME/.factored-prodlike}"
tmux kill-session -t factored-prodlike 2>/dev/null && echo "backend detenido" || echo "el backend no estaba corriendo"
export PRODLIKE_OWNER_PASSWORD=x PRODLIKE_DIST="$ROOT/frontend"      # compose los exige para interpretar el archivo
if [[ "${1:-}" == "--purge" ]]; then
  docker compose -f infra/prodlike/docker-compose.yml down -v 2>&1 | tail -n 1
  rm -f "$STATE/env" "$STATE/backend.log" "$STATE/commit"
  echo "contenedores, datos y secretos locales borrados"
else
  docker compose -f infra/prodlike/docker-compose.yml down 2>&1 | tail -n 1
  echo "contenedores detenidos (los datos quedan; --purge los borra)"
fi
