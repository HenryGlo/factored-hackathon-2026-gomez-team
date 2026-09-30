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

Pendiente: todavía no hay código. Aquí irán los pasos para: (1) descargar el dataset, (2) correr el ETL a PostgreSQL, (3) entrenar/cargar los modelos, (4) levantar backend y frontend, (5) correr el harness de evaluación. Las variables de entorno necesarias están listadas en [.env.example](.env.example).

## Equipo y roles

**[Decisión]** Roles (nombres: Pendiente, P-18):

| Rol | Responsabilidades | Carpetas principales |
|---|---|---|
| Data scientist | LLM (prompts, modelo por nodo), harness de evaluación, ranker | `ml/`, `eval/`, `backend/llm/`, `backend/nodes/` |
| Data analyst | Calidad de datos, análisis de demanda, ROI | `analytics/`, `data_pipeline/quality/`, `docs/data/` |
| Software developer | Backend, frontend, despliegue | `backend/`, `frontend/`, `infra/`, `data_pipeline/etl/` |

## Estado actual

- [x] Estructura de carpetas y documentación inicial.
- [ ] ETL a PostgreSQL.
- [ ] Generador de reclamos y set de test escrito a mano.
- [ ] Ranker, riesgo de fraude y baselines de intención.
- [ ] Backend (controlador, tools, política) y API.
- [ ] Frontend (chat y consola).
- [ ] Harness y ablaciones.
- [ ] Despliegue, slides y video. Ver [docs/submission.md](docs/submission.md).

## Documentación

- [Índice de docs](docs/README.md)
- [Arquitectura](docs/architecture.md) · [Flujo conversacional](docs/conversation-flow.md)
- [Contrato de API](docs/api-contract.md) · [Contrato de tools](docs/tools-contract.md)
- [Políticas R1–R6](docs/policies.md) · [Esquema de handoff](docs/handoff-schema.md)
- [Datos](docs/data/README.md) · [Modelos](docs/ml/README.md) · [Evaluación](docs/evaluation.md)
- [Decisiones (ADR)](docs/decisions/README.md) · [Entrega](docs/submission.md) · [Preguntas abiertas](docs/open-questions.md)
- [Cómo contribuir](CONTRIBUTING.md)
