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

**[Propuesta]** Aquí también irán el punto de entrada de la aplicación FastAPI (crea la app, registra rutas y middlewares) y el archivo de dependencias de Python del backend.

## Entradas y salidas

- Entrada: peticiones HTTP del frontend ([docs/api-contract.md](../docs/api-contract.md)); datos en PostgreSQL cargados por [data_pipeline/](../data_pipeline/README.md); artefactos de modelos de [ml/](../ml/README.md).
- Salida: respuestas con bloques de UI; reclamos, handoffs y trazas en el esquema `app`.

## Dependencias

`data_pipeline/` (esquema y datos), `ml/` (ranker y riesgo), API de Claude, variables de [.env.example](../.env.example).

## Responsable sugerido

Software developer (API, controlador, tools, persistencia); data scientist (nodos LLM, prompts).
