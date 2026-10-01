# CI/CD

Estado: **[Decisión]** fase 4 del [prompt 05](prompts/05-produccion.md). Workflows en [.github/workflows/](../.github/workflows/).

## ci.yml: en cada PR y en cada push a `main`

| Job | Pasos | Falla si |
|---|---|---|
| **Backend, pipeline y harness** | `ruff check` → `mypy backend/app` → `pytest` (backend, pipeline, harness) contra un PostgreSQL 17 del runner → harness de dev (`baseline` y `sistema` con `LLM_PROVIDER=fake`) → puerta de calidad | Lint, tipos o tests fallan; el harness tiene algún resultado inseguro; la tasa de "pasan todo" baja frente a la referencia de `main` |
| **Frontend** | `npm ci` → `eslint` → `tsc` → `vitest` → `vite build` | Cualquiera de los pasos. Sin `frontend/package.json`, termina en verde sin hacer nada |

**Datos de CI:** nunca se usa el dataset real.
- Los tests usan los fixtures `FXT-` de `data_pipeline/fixtures/`.
- El harness usa el **dataset sintético** de [eval/synthetic/generate.py](../eval/synthetic/generate.py):
  - 515 clientes ficticios con IDs `SYN-`, determinista.
  - Pasa por el pipeline real con sus contratos (0 advertencias).
  - Cada selector de `eval/cases/selectors.py` tiene al menos 40 filas, así los 54 casos de dev se pueden correr.
- Sirve para detectar **regresiones**, no para medir la calidad absoluta. Esa se mide con el dataset real en local y con el split test.

**Puerta de calidad** ([eval/ci_gate.py](../eval/ci_gate.py)):
- Compara el último resultado de cada variante con [eval/ci_reference.json](../eval/ci_reference.json), versionado en `main`.
- Falla con 1 o más resultados inseguros, o si la tasa baja.
- Cuando un cambio **sube** la tasa, se actualiza la referencia en el mismo PR:

```bash
EVAL_DATABASE_URL=<servidor>/bank_eval_ci_test EVAL_DATASET=synthetic python -m eval.run --split dev --variant baseline --repeats 1
EVAL_DATABASE_URL=<servidor>/bank_eval_ci_test EVAL_DATASET=synthetic python -m eval.run --split dev --variant sistema --repeats 1 --set LLM_PROVIDER=fake
EVAL_DATASET=synthetic python -m eval.ci_gate --split dev baseline "sistema+llm_provider-fake" --update
```

**Artefactos:** el reporte y el JSON crudo del harness (`harness-dev-synthetic`, 14 días). Solo contienen IDs sintéticos.

**Secretos:** `ci.yml` no usa ninguno. Las credenciales de PostgreSQL son de una base efímera del runner.

## eval-llm.yml: manual, con la API real

Corre el split dev con la variante `sistema_api` (`LLM_PROVIDER=anthropic_api`) sobre el dataset sintético y sube el reporte (`eval-llm-dev`, 30 días).
- Nunca corre en PRs ni en pushes: solo con **Run workflow** (`workflow_dispatch`).
- Costo estimado: ~1 USD por repetición.

### Configurar `ANTHROPIC_API_KEY` (una vez)

El job usa el *environment* `eval-llm`. Recomendado: el secreto vive solo ahí, y opcionalmente con aprobación manual.

1. **Crear el environment:** GitHub → *Settings* → *Environments* → *New environment* → `eval-llm`.
   - Opcional: *Required reviewers*, para que cada corrida pida aprobación.
   - Opcional: *Deployment branches* → solo `main`.
2. **Cargar el secreto:** dentro del environment, *Add environment secret* → nombre `ANTHROPIC_API_KEY`, valor = la clave nueva.
   - Con la CLI, sin dejar la clave en el historial del shell: `gh secret set ANTHROPIC_API_KEY --env eval-llm --repo HenryGlo/factored-hackathon-2026-gomez-team` y pegarla cuando la pida.
3. **Correr:** *Actions* → *Eval LLM (manual)* → *Run workflow* (repeticiones: 1), o `gh workflow run eval-llm.yml -f repeats=1`.

La clave nunca se imprime: GitHub enmascara los secretos en los logs. Conviene tener además un límite de gasto en la consola de Anthropic.

## Despliegue automático

Pendiente de la fase 5. Se desplegará desde `main` solo si `ci.yml` pasa ([deployment.md](deployment.md), cuando exista).
