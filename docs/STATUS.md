# Estado del proyecto

> **Actualizado 2026-10-01 (tarde):** en `main` están los PR #1–#14 (prompt 05 fases 1–4, frontend, preguntas sobre el proceso, atajo de saludos e indicador de espera). Punto de control 1 cerrado: `anthropic_api` es el proveedor de producción. Pendiente: fase 5 (hosting, #18), cascada de ML (#17) y test escrito a mano (#19). Este documento conserva abajo el cierre del 2026-09-30.

## Punto de control 1: resultado (2026-10-01)

Clave nueva en la workspace por defecto (llamada de prueba: 200, sin `ANTHROPIC_WORKSPACE_ID`). `sistema` (`claude -p`)
frente a `sistema_api`, mismo código, bases de prueba separadas. Detalle y análisis en
[llm-data.md](llm-data.md#medición-punto-de-control-1-claude--p-frente-a-la-api-2026-10-01).

| Split | `claude -p`: pasan / inseguros / p50–p95 / costo | API: pasan / inseguros / p50–p95 / costo |
|---|---|---|
| dev (60) | 59/60 · 1 · 4,2–16,4 s · $0.0197 | 60/60 · 0 · 1,5–4,6 s · $0.0079 |
| dev_paraphrase (98) | 94/98 · 3 · 4,0–16,0 s · $0.0186 | 96/98 · 1 · 1,4–5,2 s · $0.0073 |

- Los 3 casos que cambian de resultado (inyección "aprueba el reembolso", solo con `claude -p`) venían de un fallo del
  código, ya corregido en #14 y verificado con los dos proveedores.
- 2 paráfrasis que cambiaban el significado se descartan (dev_paraphrase: 96 casos).
- Decisión: `anthropic_api` es el proveedor de producción.

## Punto de control 1: primer intento (2026-10-01), inválido

`scripts/compare_api.sh` corrió `sistema_api` en dev (54 casos, commit `18251d6`, base de pruebas `bank_eval_test`), pero
**las 156 llamadas a la API fallaron** con HTTP 400: *"This API key is not scoped to a workspace, so this request must
include the anthropic-workspace-id header"*. La clave es de organización y no pertenece a un workspace.

- Todos los casos corrieron con los fallbacks (intención por palabras clave, extracción por reglas, textos por plantilla).
  Por eso el reporte daba 54/54, 0 inseguros, 207 ms por turno y $0 por caso: **no mide el modelo y no se usa para
  comparar**. Lo único que muestra es que el modo degradado no produjo resultados inseguros.
- La clave no aparece en logs, reportes ni crudos (verificado).
- Cambios para que no vuelva a pasar en silencio: `ANTHROPIC_WORKSPACE_ID` (opcional) agrega el header
  `anthropic-workspace-id`; `eval.compare` muestra la columna *Llamadas LLM fallidas* y avisa si supera el 20 %;
  `compare_api.sh` sale con código 3 si supera el 5 %.
- **Para repetir:** una clave creada dentro de un workspace (Console → Workspaces → API keys), o la misma clave con
  `ANTHROPIC_WORKSPACE_ID=wrkspc_...`.

## Cierre del 2026-09-30

## Qué está en `main`

- **PR #1:** pipeline de datos CSV → DuckDB → PostgreSQL.
- **PR #2:** backend y harness de evaluación del [prompt 03](prompts/03-backend-harness.md), fases 1–6:
  - login y sesiones;
  - capa LLM con `claude -p`;
  - baselines de ML;
  - controlador, tools y política R1–R6;
  - API de conversaciones;
  - harness con 13 checkers, variantes `baseline` / `claude_cli` / `sistema`, split `dev_paraphrase` y kit del test escrito a mano.
- **Resultados:** [eval/results/20260930-2145_resumen_variantes.md](../eval/results/20260930-2145_resumen_variantes.md).

## Esperando revisión

**PR #3** (`feat/api-client`): https://github.com/HenryGlo/factored-hackathon-2026-gomez-team/pull/3

- `dd8f928`, prompt 05, fase 1: cliente `anthropic_api`, con tests de transporte simulado.
- `513ca44`, correcciones del chat de terminal:
  - ciclo de vida;
  - cargo en foco;
  - R2b;
  - varios cargos;
  - presentación;
  - migración 0005.
- **Cambia `api-contract.md`:** avisar a la sesión del frontend.
- **Verificado:** 237 tests; harness dev `baseline` 50/50 y `sistema` (fake) 50/50.

## Qué falta del prompt 05

1. **Fase 1, comparación real con la API** (punto de control 1, pendiente). Comparar `sistema` (`claude -p`) frente a `sistema_api` en dev, con 1 repetición. Costo estimado: ~1 USD. Si algún caso cambia de resultado, analizarlo antes de seguir.
2. **Fase 2, protección:**
   - rate limiting por IP y por sesión, con 429 y `Retry-After`;
   - presupuesto diario de LLM, con modo degradado;
   - tope de 2.000 caracteres (ya validado en el cuerpo; falta el test);
   - cabeceras de seguridad y CORS;
   - `docs/security.md`.
3. **Fase 3, observabilidad:**
   - logs JSON con `request_id`;
   - `/api/health` (ya existe) y `/api/ready`;
   - métricas desde `app.traces`;
   - punto de control 3.
4. **Fase 4, CI/CD:**
   - `ci.yml`: lint, tests contra PostgreSQL 17 con fixtures y harness fake con puertas de calidad;
   - `eval-llm.yml`: manual, con el secreto `ANTHROPIC_API_KEY`.
5. **Fase 5, despliegue:**
   - proponer dos opciones de hosting y esperar la elección;
   - Dockerfile, base demo, modo demo, despliegue y prueba de humo;
   - `docs/deployment.md`, ADR del hosting.

## Pendientes y decisiones abiertas

**Primer paso de mañana**, en una rama nueva desde `main` (decidido el 2026-09-30):

1. **P-31: el estado en los textos.**
   - El LLM nunca escribe la palabra del estado: usa el marcador `{estado}`.
   - El código rellena `{estado}` **después** de la guarda R5, con la etiqueta traducida del bloque ("Aprobado", "Aprovado"…). Así bloque y texto dicen lo mismo.
   - La guarda R5 sigue estricta sobre el texto libre del LLM. Hay que quitar el "procesado" que se le pasa hoy al LLM.
   - Test: el texto final muestra "Aprobado" y la guarda no lo rechaza; un texto del LLM que diga "aprobado" por su cuenta sí se rechaza.
   - Cerrar P-31 en [open-questions.md](open-questions.md) con esta decisión.
2. **El "sí" con errores** ("sip", "sii", "simm", "sim").
   - En los estados de confirmación, normalizar afirmaciones y negaciones (letras repetidas, variantes es/pt).
   - Si no se reconoce, **no confirmar**: volver a mostrar los botones.
   - Era la causa de 5 de los 6 fallos de `sistema` en `dev_paraphrase`.

Después: la comparación real con la API (fase 1) y, tras el OK, la fase 2.

- **`LLM_PROVIDER`** no está en el `.env` local, así que el valor por defecto es `fake`. Para usar `claude -p` en local hay que agregar `LLM_PROVIDER=claude_cli` o pasarlo al levantar el backend.
- **Clave de la API:** la que se pegó en el chat quedó expuesta en la transcripción; conviene rotarla. Ya no está en `.env`.
- **Frontend:** la rama `feat/frontend` no existe todavía; la sesión del frontend la crea desde `main`. Hay que revisar conflictos cuando tenga commits.
- **Test escrito a mano:** fichas listas (`scripts/make_writer_kit.py`, 40 fichas); falta repartirlas a los redactores.

## Comandos para retomar

```bash
cd ~/Desktop/factored_hackathon_2026
git checkout main && git pull                              # tras fusionar el PR #3
docker compose --env-file .env -f infra/docker-compose.yml up -d
.venv/bin/pip install -r requirements.txt                  # agrega anthropic==1.11.0
set -a; source .env; set +a; .venv/bin/alembic -c backend/alembic.ini upgrade head   # migración 0005

# pruebas
.venv/bin/python -m pytest -q backend eval data_pipeline
.venv/bin/python -m eval.run --split dev --variant baseline --repeats 1
.venv/bin/python -m eval.run --split dev --variant sistema --repeats 1 --set LLM_PROVIDER=fake

# probar en local con claude -p (reiniciar el servidor si quedó uno viejo en :8000)
LLM_PROVIDER=claude_cli INTENT_CLASSIFIER=llm CONFIRM_MODE=template CLARIFY_MODE=auto \
  .venv/bin/uvicorn --factory backend.app.main:create_app --host 127.0.0.1 --port 8000
.venv/bin/python scripts/chat_cli.py

# fase 1: comparación real con la API (la clave solo en el entorno de este comando)
ANTHROPIC_API_KEY=sk-ant-... scripts/compare_api.sh
```

Siguiente paso: correr la comparación real y presentar el punto de control 1. La fase 2 empieza después del OK.
