#!/usr/bin/env bash
# Verificación previa al despliegue (docs/deployment.md, checklist del sábado). No despliega ni toca nada fuera del equipo.
#
#   scripts/predeploy_check.sh                # todo
#   scripts/predeploy_check.sh --skip-docker  # sin construir la imagen
#
# 1. render.yaml al día con infra/render/prod.env y variables documentadas.   2. Sin datos del dataset en el repo.
# 3. Escaneo de secretos de todo el historial (gitleaks).                      4. La imagen Docker de producción se construye.
# 5. El árbol está limpio y es el último main (aviso, no error).
set -uo pipefail
cd "$(dirname "$0")/.."
PRIMARY="$(cd "$(git rev-parse --git-common-dir)/.." && pwd)"
PY=.venv/bin/python; [[ -x "$PY" ]] || PY="$PRIMARY/.venv/bin/python"
rc=0

"$PY" scripts/predeploy_check.py || rc=1

if command -v gitleaks >/dev/null 2>&1; then
  if gitleaks git . --redact --no-banner --exit-code 1 >/dev/null 2>&1; then echo "✔ escaneo de secretos (gitleaks, historial completo)"
  else echo "✘ escaneo de secretos: gitleaks encontró algo (correr: gitleaks git . --redact)"; rc=1; fi
else
  echo "✘ escaneo de secretos: falta gitleaks (brew install gitleaks)"; rc=1
fi

if [[ "${1:-}" == "--skip-docker" ]]; then
  echo "– imagen Docker: omitida (--skip-docker)"
elif docker build -q -t disputas-backend:predeploy -f infra/render/backend.Dockerfile . >/dev/null 2>&1; then
  leaked="$(docker run --rm disputas-backend:predeploy sh -c 'ls -a | grep -E "^(\.env|data|dataset|eval|frontend|\.git)$" || true')"
  if [[ -z "$leaked" ]]; then echo "✔ la imagen Docker se construye y no lleva .env, datos, eval ni frontend"
  else echo "✘ la imagen Docker lleva lo que no debe: $leaked"; rc=1; fi
else
  echo "✘ la imagen Docker no se construye (docker build -f infra/render/backend.Dockerfile .)"; rc=1
fi

git fetch -q origin main 2>/dev/null || true
[[ -z "$(git status --porcelain --untracked-files=no)" ]] || echo "⚠ hay cambios sin commit en esta carpeta"
[[ "$(git rev-parse HEAD)" == "$(git rev-parse origin/main 2>/dev/null)" ]] || echo "⚠ esta carpeta no está en el último origin/main ($(git rev-parse --short HEAD) vs $(git rev-parse --short origin/main))"

[[ $rc == 0 ]] && echo "LISTO para desplegar (según estas comprobaciones)" || echo "NO desplegar: hay comprobaciones fallidas"
exit $rc
