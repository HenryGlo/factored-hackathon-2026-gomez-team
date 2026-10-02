# factored-hackathon-2026-gomez-team

> Repositorio del equipo para el **Factored AI & Data Hackathon 2026**.
> Estado: **solo estructura y documentación**. Todavía no hay código de la solución.

Convención de etiquetas usada en toda la documentación:

| Etiqueta | Significado |
|---|---|
| **[Oficial]** | Requisito tomado del material del reto (enunciado, kickoff, diccionario de datos). |
| **[Decisión]** | Decisión ya tomada por el equipo. |
| **[Propuesta]** | Diseño propuesto, sujeto a cambio durante la implementación. |
| **[Supuesto]** | Supuesto del equipo que falta confirmar. Cada uno se rastrea en [docs/open-questions.md](docs/open-questions.md). |

## El problema en una frase

**[Decisión]** Un cliente ve en su cuenta un cargo que no reconoce ("Tengo un cobro de $120 que no reconozco") y necesita identificarlo y, si corresponde, abrir un reclamo sin esperar a un agente, sin que el sistema actúe a ciegas.

## Qué hace la solución

**[Oficial]** El reto pide un sistema de atención al cliente bancario "AI-first" que entienda la conversación, use datos y herramientas de forma segura, complete un flujo de servicio y pase a una persona cuando haga falta, en español y portugués.

**[Decisión]** Elegimos el flujo de **disputas de cargos no reconocidos** ([ADR-0001](docs/decisions/0001-workflow-disputas.md)). El agente:

1. Entiende la queja del cliente y extrae monto, fecha, comercio y canal.
2. Busca y ordena las transacciones candidatas del cliente con un **ranker** (modelo de ML, no el LLM).
3. Si hay una candidata clara, la muestra para confirmar; si no, **aclara** (máximo 3 vueltas).
4. Aplica **políticas explícitas en código** (R1–R6) y un **riesgo de fraude calibrado**.
5. **Crea un reclamo** (con confirmación explícita del cliente y verificación posterior) o **escala** a una persona con un handoff estructurado.
6. **Nunca aprueba devoluciones.**

Más detalle en [docs/architecture.md](docs/architecture.md) y [docs/conversation-flow.md](docs/conversation-flow.md).

## Estructura del repositorio

| Carpeta | Contenido |
|---|---|
| [docs/](docs/README.md) | Arquitectura, flujo, contratos, políticas, datos, ML, evaluación, ADR y entrega. |
| [backend/](backend/README.md) | API FastAPI, controlador con máquina de estados, nodos, tools, política y persistencia. |
| [frontend/](frontend/README.md) | Chat del cliente y consola del banco. |
| [ml/](ml/README.md) | Ranker de transacciones, riesgo de fraude calibrado y clasificador de intención (baselines). |
| [data_pipeline/](data_pipeline/README.md) | ETL de los CSV a PostgreSQL, contratos de datos, validación y calidad. |
| [eval/](eval/README.md) | Harness de evaluación, casos, generador de reclamos, juez y resultados de ablaciones. |
| [analytics/](analytics/README.md) | Análisis de demanda, calidad de datos y ROI. |
| [data/](data/README.md) | **Solo documentación.** Los datos crudos y procesados no se versionan. |
| [infra/](infra/README.md) | Despliegue. |
| [scripts/](scripts/README.md) | Utilidades de desarrollo. |

Material previo (existe solo en local y **no se versiona** por ahora; ver [.gitignore](.gitignore)):

| Ruta | Qué es |
|---|---|
| `dashboard/` | Dashboard exploratorio en Streamlit + DuckDB (tiene su propio README). |
| `viability_check.py`, `viability_report.md` | Chequeo de viabilidad de los flujos candidatos; fuente de varios hallazgos de [docs/data/quality-report.md](docs/data/quality-report.md). |
| `dataset_eval.ipynb` | Notebook de exploración. |

Pendiente: decidir si ese material se mueve a `analytics/` (ver [docs/open-questions.md](docs/open-questions.md), P-15).

### Ajustes a la estructura propuesta

- **`data/`** ya contenía los PDFs del reto. El diccionario de datos incluye **credenciales de acceso al bucket**, así que [.gitignore](.gitignore) excluye todo `data/` salvo los `.md`. Nunca copiar esas credenciales a ningún archivo versionado.
- **`docs/data/`** y **`docs/ml/`** se agregan para separar la documentación de datos y de modelos del código.
- **`dataset/`** (descarga local del bucket) queda fuera del repo por [.gitignore](.gitignore).

## Cómo correrlo

### En local, desde cero, en menos de 10 minutos

Requisitos: Docker en marcha, Python 3.12 y Node 22. Nada más.

```bash
git clone <repo> && cd <repo>
# opcional: copiar el dataset del reto a dataset/data/ (no se versiona). Sin él se usa un dataset sintético.
scripts/dev_up.sh --reset-demo
```

Ese comando hace todo, y cada paso se salta si ya está hecho:

1. **`.env`**: si no existe, lo crea desde `.env.example` con contraseñas generadas ([scripts/bootstrap_env.py](scripts/bootstrap_env.py)). Nunca pisa uno existente.
2. **`.venv`**: lo crea e instala `requirements-dev.txt`.
3. **PostgreSQL 17** en Docker (puerto 5433) con los roles `app_rw` / `app_ro`, y las migraciones de Alembic.
4. **Datos** ([scripts/dev_data.py](scripts/dev_data.py)), solo si la base está vacía:
   - con el dataset del reto en `dataset/data/`: CSV → DuckDB → PostgreSQL (4,4 M de movimientos);
   - sin él: el dataset **sintético** de `eval/synthetic` (515 clientes ficticios `SYN-`), suficiente para recorrer todos los escenarios.
5. **Usuarios demo**: 12 clientes (2 por escenario), `analista_1`, `analista_2` y `admin_1`. La contraseña es `DEMO_PASSWORD` de `.env` (`grep DEMO_PASSWORD .env`).
6. **Backend** en http://127.0.0.1:8000 y **frontend** en http://localhost:5173.
   - Con la CLI de Claude instalada usa `claude -p`; sin ella arranca con `LLM_PROVIDER=fake` (reglas y plantillas).
   - `--reset-demo` deja la demo limpia: borra conversaciones, reclamos, handoffs y bloqueos de los clientes demo. No toca `ref.*` ni los usuarios.

Tiempos medidos el 2026-10-01 en un clon limpio (sin `.env`, `.venv`, `node_modules` ni volumen de PostgreSQL), en una MacBook con las cachés de pip, npm y la imagen `postgres:17` ya descargadas; la primera descarga suma lo que tarde la red:

| Caso | Hasta tener el frontend respondiendo |
|---|---|
| Sin dataset (sintético) | 53 s |
| Con el dataset del reto (construye la DuckDB y carga 4,4 M de movimientos) | 3 min 43 s |
| Arranques siguientes | ≈ 4 s |

Otras formas de arrancar:

```bash
scripts/dev_up.sh                     # día a día (no borra nada)
LLM_PROVIDER=fake scripts/dev_up.sh   # sin LLM (plantillas y reglas)
scripts/dev_up.sh --synthetic         # primera carga con el dataset sintético aunque exista el del reto
BACKEND_PORT=8011 FRONTEND_PORT=5199 POSTGRES_PORT=5599 COMPOSE_PROJECT_NAME=otra-copia scripts/dev_up.sh   # segunda copia aislada
```

Los pasos a mano (ETL, usuarios, migraciones) están en [docs/data/postgres.md](docs/data/postgres.md) y [backend/README.md](backend/README.md).

Abrir http://localhost:5173. Los usuarios demo y su escenario aparecen en el login. Cada pieza por separado:

- **Backend:** ver la tabla de proveedores de abajo y `backend/README.md`.
- **Frontend:** [frontend/README.md](frontend/README.md).
- **Chat de terminal:** `.venv/bin/python scripts/chat_cli.py`.

### Pruebas y evaluación

```bash
.venv/bin/ruff check backend eval scripts data_pipeline && .venv/bin/mypy backend/app
.venv/bin/python -m pytest -q backend data_pipeline eval/tests
.venv/bin/python -m eval.run --split dev --variant baseline --repeats 1                         # harness (docs/evaluation.md)
.venv/bin/python -m eval.run --split dev --variant sistema --repeats 1 --set LLM_PROVIDER=fake
```

**CI** ([.github/workflows/ci.yml](.github/workflows/ci.yml)) corre en cada PR y en cada push a `main`:

- **Backend, pipeline y harness:**
  - lint (ruff) y tipos (mypy);
  - tests contra PostgreSQL 17 con los fixtures `FXT-`;
  - harness de dev con `LLM_PROVIDER=fake` sobre el **dataset sintético** ([eval/synthetic/](eval/synthetic/generate.py)), nunca el real.
- **Puerta de calidad:** 0 resultados inseguros y ninguna regresión frente a [eval/ci_reference.json](eval/ci_reference.json). El reporte queda como artefacto.
- **Frontend:** eslint, tsc, vitest y build. Se activa solo si existe `frontend/package.json`.
- **Evaluación con la API real:** [eval-llm.yml](.github/workflows/eval-llm.yml), solo manual. Ver [docs/ci.md](docs/ci.md).

### Proveedor LLM por entorno

| Entorno | `LLM_PROVIDER` | Modelos | Clave |
|---|---|---|---|
| Local (desarrollo) | `claude_cli`: `claude -p` con la suscripción de Claude Code | Alias por nodo (`haiku`, `sonnet`) | No hace falta |
| Tests y CI | `fake`: sin red; reglas y plantillas | — | No hace falta |
| Desplegado y workflow manual `eval-llm` | `anthropic_api`: SDK oficial `anthropic` | IDs fijos por nodo (`claude-haiku-4-5-20251001`, `claude-sonnet-5-5`) | `ANTHROPIC_API_KEY`, solo como secreto del hosting y de GitHub |

- **Dónde está la configuración:** [backend/config/llm.toml](backend/config/llm.toml) tiene los modelos de cada nodo por proveedor. Los precios para calcular el costo están en [backend/config/llm_pricing.toml](backend/config/llm_pricing.toml).
- **Si no se define `LLM_PROVIDER`:** se usa `fake`, el valor de `llm.toml`.
- **Cómo cambiar de proveedor:**
  - Define `LLM_PROVIDER` en `.env` o en el entorno, por ejemplo `LLM_PROVIDER=claude_cli`.
  - Para una corrida del harness, usa la variante: `baseline` usa `fake`, `sistema` usa `claude_cli` y `sistema_api` usa `anthropic_api`.
  - La API necesita `ANTHROPIC_API_KEY` en el entorno solo mientras dure esa corrida.
- **Detalle:** [docs/llm-data.md](docs/llm-data.md#proveedor-de-producción-api-de-claude-prompt-05-fase-1).

## Equipo y roles

**[Decisión]** Roles (nombres: Pendiente, P-18):

| Rol | Responsabilidades | Carpetas principales |
|---|---|---|
| Data scientist | LLM (prompts, modelo por nodo), harness de evaluación, ranker | `ml/`, `eval/`, `backend/llm/`, `backend/nodes/` |
| Data analyst | Calidad de datos, análisis de demanda, ROI | `analytics/`, `data_pipeline/quality/`, `docs/data/` |
| Software developer | Backend, frontend, despliegue | `backend/`, `frontend/`, `infra/`, `data_pipeline/etl/` |

## Estado actual

- [x] Estructura de carpetas y documentación inicial.
- [x] ETL CSV → DuckDB → PostgreSQL (completa, incremental por partición, cuarentena, linaje) y migraciones del esquema.
- [x] Backend: autenticación, controlador con máquina de estados, tools, política R1–R6 (+ R2b) y API de conversaciones.
- [x] Baselines de intención, ranker y riesgo; harness con 13 checkers, splits dev y dev_paraphrase, y kit del test escrito a mano.
- [x] Producción, fases 1–3 del prompt 05: cliente de la API de Claude, protección (límites, presupuesto de LLM, cabeceras, CORS) y observabilidad (logs JSON, `/api/ready`, `/api/metrics`).
- [x] Frontend: chat, mis movimientos, mis reclamos y consola del analista; preguntas sobre el proceso, atajo de saludos e indicador de espera real.
- [x] CI: lint, tipos, tests, harness sintético con puerta de calidad y frontend.
- [x] Comparación real `claude -p` frente a la API (punto de control 1): `anthropic_api` en producción ([llm-data.md](docs/llm-data.md)).
- [x] Prácticas de GitHub: issues, PR con plantilla, Conventional Commits, tags y Releases ([CHANGELOG](CHANGELOG.md), [CONTRIBUTING](CONTRIBUTING.md)).
- [ ] Test escrito a mano (redactores), entrenamiento de modelos (prompt 04, partes E–G).
- [ ] Despliegue, slides y video. Ver [docs/submission.md](docs/submission.md) y [docs/STATUS.md](docs/STATUS.md).

## Documentación

- [Índice de docs](docs/README.md)
- [Arquitectura](docs/architecture.md) · [Flujo conversacional](docs/conversation-flow.md)
- [Contrato de API](docs/api-contract.md) · [Contrato de tools](docs/tools-contract.md)
- [Políticas R1–R6](docs/policies.md) · [Esquema de handoff](docs/handoff-schema.md)
- [Datos](docs/data/README.md) · [Modelos](docs/ml/README.md) · [Evaluación](docs/evaluation.md)
- [Decisiones (ADR)](docs/decisions/README.md) · [Entrega](docs/submission.md) · [Preguntas abiertas](docs/open-questions.md)
- [Despliegue (Render)](docs/deployment.md) · [Seguridad](docs/security.md)
- [Cómo contribuir](CONTRIBUTING.md)
