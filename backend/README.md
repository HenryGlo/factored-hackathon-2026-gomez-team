# backend/

## Propósito

**[Decisión]** Servicio FastAPI que expone la API, orquesta la conversación con una máquina de estados, ejecuta tools con permisos por sesión y aplica las políticas en código. Arquitectura: [docs/architecture.md](../docs/architecture.md).

## Subcarpetas

| Carpeta | Contenido |
|---|---|
| [api/](api/README.md) | Endpoints, autenticación de sesión, idempotencia, esquemas de bloques. |
| [controller/](controller/README.md) | Máquina de estados y orquestación de nodos. |
| [nodes/](nodes/README.md) | Nodos del flujo (intención, extracción, aclaración, confirmación, explicación, handoff). |
| [tools/](tools/README.md) | Tools de lectura y escritura con permisos por sesión. |
| [policy/](policy/README.md) | Reglas R1–R6. |
| [persistence/](persistence/README.md) | Acceso a PostgreSQL y esquema `app`. |
| [llm/](llm/README.md) | Cliente de Claude, prompts versionados, salidas estructuradas. |
| [tests/](tests/README.md) | Pruebas unitarias y de integración del backend. |

**[Decisión]** El código vive en `backend/app/` (paquete Python); las subcarpetas de arriba documentan cada componente. Avance según [docs/prompts/03-backend-harness.md](../docs/prompts/03-backend-harness.md):

| Ruta | Estado |
|---|---|
| `app/main.py`, `app/config.py`, `app/db.py`, `app/errors.py`, `app/security.py` | Fase 1: app FastAPI, configuración (.env), motores `app_rw` y `app_ro`, errores del contrato, argon2 y tokens. |
| `app/auth/` | Fase 1: login, logout, `me`, CSRF, límite de intentos, dependencias de sesión y rol. |
| `app/console/` | Fase 1: `GET /api/cases` (rol `analyst`, usuario de solo lectura). |
| `app/llm/`, `prompts/`, `config/llm.toml`, `app/dates.py` | Fase 2: capa LLM (`claude -p` y falso), 6 nodos versionados, fechas relativas. |
| `app/ml/`, `config/ml.toml` | Fase 3: interfaces `IntentClassifier`, `Ranker`, `RiskModel`, `ClarifyPolicy` con baselines (palabras clave, RuleRanker, fraud_score/100, umbrales). |
| `app/policy/`, `config/policy.toml` | Fase 4: R1–R6 como funciones puras (supuestos). |
| `app/tools/` | Fase 4: tools con permisos por sesión, tokens de confirmación y fallos inyectables. |
| `app/controller/` | Fase 4: máquina de estados, bloques es/pt, trazas. |
| `app/conversations.py` | Fase 5: API de conversaciones, turnos y consola. |
| `persistence/models.py`, `migrations/` | Esquemas `ref`, `ops` y `app`; migraciones 0001–0003. |
| `tests/` | Pruebas de las fases 1–5 (las de base de datos, contra `bank_test`). |

```bash
.venv/bin/alembic -c backend/alembic.ini upgrade head         # migraciones (ADMIN_DATABASE_URL)
.venv/bin/python scripts/seed_demo_users.py                   # usuarios demo (DEMO_PASSWORD de .env)
LLM_PROVIDER=fake .venv/bin/uvicorn --factory backend.app.main:create_app --reload   # claude_cli para el LLM real
.venv/bin/pytest backend/tests -q                              # solo contra bases *_test
```

## Entradas y salidas

- Entrada: peticiones HTTP del frontend ([docs/api-contract.md](../docs/api-contract.md)); datos en PostgreSQL cargados por [data_pipeline/](../data_pipeline/README.md); artefactos de modelos de [ml/](../ml/README.md).
- Salida: respuestas con bloques de UI; reclamos, handoffs y trazas en el esquema `app`.

## Dependencias

`data_pipeline/` (esquema y datos), `ml/` (ranker y riesgo), API de Claude, variables de [.env.example](../.env.example).

## Responsable sugerido

Software developer (API, controlador, tools, persistencia); data scientist (nodos LLM, prompts).
