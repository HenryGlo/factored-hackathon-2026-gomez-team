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
| `persistence/models.py`, `migrations/` | Esquemas `ref`, `ops` y `app`; migraciones 0001–0003. |
| `tests/` | Pruebas de la fase 1 contra `bank_test`. |

```bash
.venv/bin/alembic -c backend/alembic.ini upgrade head         # migraciones (ADMIN_DATABASE_URL)
.venv/bin/python scripts/seed_demo_users.py                   # usuarios demo (DEMO_PASSWORD de .env)
.venv/bin/uvicorn --factory backend.app.main:create_app --reload
.venv/bin/pytest backend/tests -q                              # solo contra bases *_test
```

## Entradas y salidas

- Entrada: peticiones HTTP del frontend ([docs/api-contract.md](../docs/api-contract.md)); datos en PostgreSQL cargados por [data_pipeline/](../data_pipeline/README.md); artefactos de modelos de [ml/](../ml/README.md).
- Salida: respuestas con bloques de UI; reclamos, handoffs y trazas en el esquema `app`.

## Dependencias

`data_pipeline/` (esquema y datos), `ml/` (ranker y riesgo), API de Claude, variables de [.env.example](../.env.example).

## Responsable sugerido

Software developer (API, controlador, tools, persistencia); data scientist (nodos LLM, prompts).
