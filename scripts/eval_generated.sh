#!/usr/bin/env bash
# Flujos de conversación generados a escala, con un solo comando (eval/generated/README.md).
#
#   scripts/eval_generated.sh                        # ENSAYO GRATIS: genera un lote si no hay, corre 200 flujos con LLM falso
#   scripts/eval_generated.sh --sample 1000          # más flujos, sigue gratis
#   scripts/eval_generated.sh --llm                  # con claude -p (variante sistema): consume tu cupo de Claude Code
#   scripts/eval_generated.sh --api --sample 1000    # con la API de Claude (variante sistema_api): ≈ $7, pide --yes sobre $2
#
# Opciones:
#   --sample N          flujos de la muestra estratificada por idioma y categoría (por defecto 200)
#   --new-batch         genera un lote nuevo aunque ya haya uno; --n N fija su tamaño (por defecto 5000)
#   --yes               confirma una corrida cara (API sobre $2, o más de 300 flujos con claude -p)
#   --database-url URL  base de evaluación donde corren los casos (su nombre debe contener "_test").
#                       Por defecto <servidor de TEST_DATABASE_URL>/bank_eval_test, la misma de scripts/final_eval.sh
#
# Qué hace
# - Los flujos y los resultados quedan en el esquema eval de la base LOCAL (ADMIN_DATABASE_URL): tablas eval.batches,
#   eval.generated_cases, eval.runs, eval.case_results y la vista eval.v_results. Nunca en la base desplegada.
# - Los casos corren contra el sistema real en proceso sobre la base de evaluación (*_test), que se vacía por caso.
# - Sin data/bank.duckdb (clon sin el dataset del reto) usa el dataset sintético en <servidor>/bank_eval_synth_test.
# - Requiere PostgreSQL arriba y el entorno creado: si falta, correr antes `scripts/dev_up.sh`.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
PRIMARY="$(cd "$(git rev-parse --git-common-dir)/.." && pwd)"
PY=.venv/bin/python; [[ -x "$PY" ]] || PY="$PRIMARY/.venv/bin/python"
[[ -x "$PY" ]] || { echo "falta el entorno de Python: correr primero scripts/dev_up.sh" >&2; exit 2; }

MODE=fake; SAMPLE=200; NEW=""; N=5000; YES=(); DBURL=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --llm) MODE=claude_cli ;;
    --api) MODE=anthropic_api ;;
    --sample) SAMPLE="$2"; shift ;;
    --new-batch) NEW=1 ;;
    --n) N="$2"; shift ;;
    --yes) YES=(--yes) ;;
    --database-url) DBURL="$2"; shift ;;
    *) echo "opción desconocida: $1" >&2; exit 2 ;;
  esac
  shift
done

[[ -n "${DUCKDB_PATH:-}" || -f data/bank.duckdb ]] || { [[ -f "$PRIMARY/data/bank.duckdb" ]] && export DUCKDB_PATH="$PRIMARY/data/bank.duckdb" RAW_DATA_DIR="$PRIMARY/dataset/data"; }
DB_NAME=bank_eval_test
if [[ -z "${DUCKDB_PATH:-}" && ! -f data/bank.duckdb ]]; then
  export EVAL_DATASET=synthetic; DB_NAME=bank_eval_synth_test
  echo "   no está data/bank.duckdb: se usa el dataset sintético ($DB_NAME)"
fi
if [[ -z "$DBURL" ]]; then
  base="$(grep -s '^TEST_DATABASE_URL=' "$PRIMARY/.env" | cut -d= -f2- | sed 's#/[^/]*$##')"
  [[ -n "$base" ]] || { echo "falta --database-url (o TEST_DATABASE_URL en .env): correr primero scripts/dev_up.sh" >&2; exit 2; }
  DBURL="$base/$DB_NAME"
fi
[[ "${DBURL##*/}" == *_test* ]] || { echo "la base de evaluación debe llamarse *_test* (recibí: ${DBURL##*/})" >&2; exit 2; }
export EVAL_DATABASE_URL="$DBURL" LOG_LEVEL=WARNING

case "$MODE" in
  fake)          RUN=(--variant sistema --set LLM_PROVIDER=fake); LABEL="LLM falso (reglas y plantillas): gratis" ;;
  claude_cli)    command -v claude >/dev/null || { echo "no se encontró la CLI claude en el PATH" >&2; exit 2; }
                 RUN=(--variant sistema); LABEL="claude -p (tu cupo de Claude Code)" ;;
  anthropic_api) if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
                   [[ -s "$HOME/.anthropic_key" ]] || { echo "falta ANTHROPIC_API_KEY (entorno o ~/.anthropic_key)" >&2; exit 2; }
                   ANTHROPIC_API_KEY="$(tr -d '[:space:]' < "$HOME/.anthropic_key")"; export ANTHROPIC_API_KEY
                 fi
                 RUN=(--variant sistema_api); LABEL="API de Claude" ;;
esac

"$PY" -m eval.generated status >/dev/null 2>&1 || { echo "no hay conexión con PostgreSQL (ADMIN_DATABASE_URL): correr primero scripts/dev_up.sh" >&2; exit 1; }
echo "== flujos generados · $LABEL · muestra de $SAMPLE · base de evaluación ${DBURL##*/}"
GEN=(--n "$N"); [[ -n "$NEW" ]] || GEN+=(--if-missing)
"$PY" -m eval.generated generate "${GEN[@]}"
"$PY" -m eval.generated run "${RUN[@]}" --sample "$SAMPLE" "${YES[@]}" | grep -v '^\[rep' || exit "${PIPESTATUS[0]}"
echo "Consultas: \`$PY -m eval.generated status\` y la vista eval.v_results (psql sobre ADMIN_DATABASE_URL)."
