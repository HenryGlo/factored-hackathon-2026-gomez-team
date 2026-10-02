#!/usr/bin/env bash
# Evaluación final con un solo comando (docs/evaluation.md, checklist del sábado en docs/deployment.md).
#
#   scripts/final_eval.sh                 # ENSAYO: split dev, LLM falso, sin API ni split test. Sirve para probar el script.
#   scripts/final_eval.sh --final         # CORRIDA FINAL: API de Claude; dev y dev_paraphrase + el split test congelado
#
# Opciones:
#   --database-url URL   base de evaluación (su nombre debe contener "_test"; nunca "bank" ni la de producción).
#                        Por defecto: <servidor de TEST_DATABASE_URL>/bank_eval_test
#   --url URL            antes de evaluar, corre la prueba de humo contra esa URL desplegada; si falla, no sigue
#   --variants "a b c"   variantes (por defecto: baseline claude_cli sistema_api sistema_cascade; en el ensayo: baseline sistema)
#   --repeats N          repeticiones por variante (por defecto 1)
#   --noisy              corrida final: agrega el split dev_noisy (dev con errores de tipeo; ≈ 118 casos más por variante)
#   --yes                no pide la confirmación escrita de la corrida final
#
# Qué garantiza
# - El ensayo NUNCA toca el split test ni la API: fuerza LLM_PROVIDER=fake en todas las variantes.
# - La corrida final usa anthropic_api en todas las variantes con LLM, exige ANTHROPIC_API_KEY (del entorno o de
#   ~/.anthropic_key; no se imprime) y corre el split test UNA vez, con --i-know-this-is-final (queda en eval/results/test_runs.log).
#   Si el test ya se corrió, se niega (el test está congelado).
# - El harness corre el MISMO commit en proceso contra una base de evaluación: no escribe en la base desplegada.
# - La tabla (n/N, inseguros, p50/p95, costo por caso) queda en eval/results/<fecha>_tabla_final.md, lista para las diapositivas.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
PRIMARY="$(cd "$(git rev-parse --git-common-dir)/.." && pwd)"
PY=.venv/bin/python; [[ -x "$PY" ]] || PY="$PRIMARY/.venv/bin/python"

FINAL=""; YES=""; NOISY=""; DBURL=""; URL=""; VARIANTS=""; REPEATS=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --final) FINAL=1 ;;
    --yes) YES=1 ;;
    --noisy) NOISY=1 ;;
    --database-url) DBURL="$2"; shift ;;
    --url) URL="$2"; shift ;;
    --variants) VARIANTS="$2"; shift ;;
    --repeats) REPEATS="$2"; shift ;;
    *) echo "opción desconocida: $1" >&2; exit 2 ;;
  esac
  shift
done

if [[ -z "$DBURL" ]]; then
  base="$(grep -s '^TEST_DATABASE_URL=' "$PRIMARY/.env" | cut -d= -f2- | sed 's#/[^/]*$##')"
  [[ -n "$base" ]] || { echo "falta --database-url (o TEST_DATABASE_URL en .env)" >&2; exit 2; }
  DBURL="$base/bank_eval_test"
fi
[[ "${DBURL##*/}" == *_test* ]] || { echo "la base de evaluación debe llamarse *_test* (recibí: ${DBURL##*/})" >&2; exit 2; }
export EVAL_DATABASE_URL="$DBURL" LOG_LEVEL=WARNING
[[ -n "${DUCKDB_PATH:-}" || -f data/bank.duckdb ]] || export DUCKDB_PATH="$PRIMARY/data/bank.duckdb" RAW_DATA_DIR="$PRIMARY/dataset/data"

STAMP="$(date +%Y%m%d-%H%M)"
if [[ -z "$FINAL" ]]; then
  MODE="ENSAYO (LLM falso, split dev; no es un resultado)"; SPLITS=(dev); PROVIDER=fake
  read -r -a VARS <<< "${VARIANTS:-baseline sistema}"
else
  MODE="CORRIDA FINAL (API de Claude)"; SPLITS=(dev dev_paraphrase); PROVIDER=anthropic_api
  [[ -z "$NOISY" ]] || SPLITS+=(dev_noisy)
  read -r -a VARS <<< "${VARIANTS:-baseline claude_cli sistema_api sistema_cascade}"
  if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
    [[ -s "$HOME/.anthropic_key" ]] || { echo "falta ANTHROPIC_API_KEY (entorno o ~/.anthropic_key)" >&2; exit 2; }
    ANTHROPIC_API_KEY="$(tr -d '[:space:]' < "$HOME/.anthropic_key")"; export ANTHROPIC_API_KEY
  fi
  n_test="$("$PY" -c 'from eval.cases.schema import load_cases; print(len(load_cases("test")))')"
  if [[ "$n_test" -gt 0 ]]; then
    if grep -qs . eval/results/test_runs.log; then
      echo "el split test ya se corrió (eval/results/test_runs.log): está congelado y no se repite." >&2; exit 2
    fi
    SPLITS+=(test)
  else
    echo "⚠ el split test está vacío (el test escrito a mano no se ha importado): se corre solo dev y dev_paraphrase"
  fi
  [[ -z "$(git status --porcelain --untracked-files=no)" ]] || { echo "hay cambios sin commit: la corrida final va sobre un commit limpio" >&2; exit 2; }
  if [[ -z "$YES" ]]; then
    echo "Vas a correr la evaluación final con la API real: variantes ${VARS[*]} sobre ${SPLITS[*]} (commit $(git rev-parse --short HEAD))."
    read -r -p "Escribe FINAL para continuar: " answer
    [[ "$answer" == "FINAL" ]] || { echo "cancelado"; exit 1; }
  fi
fi
echo "== $MODE · commit $(git rev-parse --short HEAD) · base ${DBURL##*/} · variantes: ${VARS[*]} · splits: ${SPLITS[*]}"

if [[ -n "$URL" ]]; then
  echo "== prueba de humo contra $URL"
  "$PY" scripts/prodlike_smoke.py --url "$URL" || { echo "el humo falló: no se evalúa" >&2; exit 1; }
fi

RAWS=()
for split in "${SPLITS[@]}"; do
  for v in "${VARS[@]}"; do
    args=(--split "$split" --variant "$v" --repeats "$REPEATS")
    [[ "$v" == baseline ]] || args+=(--set "LLM_PROVIDER=$PROVIDER")
    [[ "$split" == test ]] && args+=(--i-know-this-is-final)
    echo "-- $split · $v"
    out="$("$PY" -m eval.run "${args[@]}" 2>&1)" || { echo "$out" | tail -n 15 | sed -E 's#(://[^:/]+:)[^@]+@#\1***@#g' >&2; echo "falló $v en $split" >&2; exit 1; }
    raw="$(echo "$out" | sed -n 's/^crudo: *//p' | tail -n 1)"
    echo "   $(echo "$out" | grep -c '^\[rep') casos · $raw"
    RAWS+=("$raw")
  done
done

OUT="eval/results/${STAMP}_tabla_$([[ -n "$FINAL" ]] && echo final || echo ensayo).md"
NOTES=(--note "Modo: $MODE." --note "Commit $(git rev-parse --short HEAD), $(date +%Y-%m-%d\ %H:%M), ${REPEATS} repetición(es) por variante.")
[[ -n "$FINAL" ]] || NOTES+=(--note "Ensayo con LLM falso: comprueba que el comando funciona. Latencia y costo no significan nada aquí.")
echo
"$PY" scripts/final_eval_table.py "${RAWS[@]}" --out "$OUT" "${NOTES[@]}"
echo "tabla: $OUT"
