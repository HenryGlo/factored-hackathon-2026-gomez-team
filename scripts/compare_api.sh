#!/usr/bin/env bash
# Comparación claude -p vs API de Claude (prompt 05, fase 1): sistema_api sobre dev (1 repetición) y tabla
# contra el último crudo de `sistema` (claude -p). Costo estimado: ~1 USD.
#
#   ANTHROPIC_API_KEY=sk-ant-... scripts/compare_api.sh
#
# La clave solo se lee del entorno de este comando; no se escribe en ningún archivo.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
  echo "falta ANTHROPIC_API_KEY en el entorno (p. ej. ANTHROPIC_API_KEY=... $0)" >&2
  exit 2
fi
.venv/bin/python -u -m eval.run --split dev --variant sistema_api --repeats 1 2>&1 | grep -vE "^INFO"
.venv/bin/python -m eval.compare --split dev sistema sistema_api
