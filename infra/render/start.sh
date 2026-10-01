#!/usr/bin/env bash
# Arranque del backend en Render: URLs de la app derivadas (sin imprimirlas) y uvicorn en $PORT detrás del proxy de Render.
set -euo pipefail
cd "$(dirname "$0")/../.."
eval "$(python infra/render/db_urls.py --export)"
unset ADMIN_DATABASE_URL          # el proceso web no necesita al dueño de la base
exec uvicorn --factory backend.app.main:create_app --host 0.0.0.0 --port "${PORT:-8000}" \
  --proxy-headers --forwarded-allow-ips '*' --no-server-header
