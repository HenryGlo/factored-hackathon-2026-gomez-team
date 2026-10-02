#!/usr/bin/env bash
# Carga manual del subconjunto demo en la base de Render, desde un equipo que tiene el dataset (docs/deployment.md).
# El dataset no está en el repo ni en la imagen, así que esta carga no puede correr dentro de Render.
#
#   RENDER_ADMIN_DATABASE_URL="$(cat ~/.render_db_url)" scripts/render_load_demo.sh [N_CLIENTES]
#
# - RENDER_ADMIN_DATABASE_URL: "External Database URL" del panel de Render (usuario dueño). Solo por entorno: no se imprime
#   ni se escribe en ningún archivo. Antes hay que permitir la IP de este equipo en la base (Access Control) y quitarla al terminar.
# - Requiere que el primer despliegue ya haya corrido (crea los roles y las migraciones) y data/bank.duckdb construida
#   (`python -m data_pipeline.run full` en local).
# - N_CLIENTES: tamaño del subconjunto determinista (por defecto 200; incluye los clientes demo de cada escenario).
set -euo pipefail
cd "$(dirname "$0")/.."
: "${RENDER_ADMIN_DATABASE_URL:?falta RENDER_ADMIN_DATABASE_URL (External Database URL del panel de Render)}"
N="${1:-200}"
PY=.venv/bin/python
URL="$(ADMIN_DATABASE_URL="$RENDER_ADMIN_DATABASE_URL" APP_DB_USER=x APP_DB_PASSWORD=x CONSOLE_DB_USER=x CONSOLE_DB_PASSWORD=x \
  "$PY" -c 'import os,sys; sys.path.insert(0,"infra/render"); from db_urls import urls; print(urls(dict(os.environ))["ADMIN_DATABASE_URL"])')"
case "$URL" in *localhost*|*127.0.0.1*) echo "esa URL es local; este script es para la base de Render" >&2; exit 2;; esac
echo "== carga del subconjunto demo ($N clientes) en Render"
"$PY" -m data_pipeline.run full --skip-build --customers-sample "$N" --database-url "$URL"
if [[ -n "${DEMO_PASSWORD:-}" ]] || grep -q '^DEMO_PASSWORD=.' .env 2>/dev/null; then
  echo "== usuarios demo"
  "$PY" scripts/seed_demo_users.py --database-url "$URL"
else
  echo "sin DEMO_PASSWORD local: los usuarios demo los crea el siguiente despliegue en Render (predeploy)"
fi
echo "listo. Quita tu IP del Access Control de la base."
