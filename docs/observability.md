# Logging y observabilidad

Estado: **[Decisión]** implementado en la fase 3 del [prompt 05](prompts/05-produccion.md) ([backend/app/observability/](../backend/app/observability/)).

## Logs estructurados

Una línea JSON por evento en stdout. La plataforma de hosting los recoge. `LOG_FORMAT=json` es el valor por defecto; `LOG_FORMAT=text` da una línea legible para desarrollo. El nivel se fija con `LOG_LEVEL` (`INFO` por defecto).

| Evento | Logger | Cuándo | Campos propios |
|---|---|---|---|
| `http_request` | `backend.access` | Cada petición `/api/*` | `method`, `route` (plantilla, p. ej. `/api/conversations/{conversation_id}/turns`), `status`, `latency_ms`; `warning` si es 5xx o 429 |
| `turn` | `backend.turns` | Cada turno de conversación | `input_kind`, `action`, `chars` (largo del mensaje, no el texto), `state_before`, `state_after`, `steps`, `llm_calls`, `llm_latency_ms`, `llm_cost_usd`, `models`, `fallbacks`, `tool_errors`, `blocks` (tipos) |
| `llm_call` | `backend.turns` | Cada llamada al LLM del turno | `node`, `provider`, `model`, `model_id`, `prompt_version`, `latency_ms`, `cost_usd`, `error`, `fallback` |
| `rate_limited`, `llm_budget_exceeded` | `backend.protection` | Límites y presupuesto ([security.md](security.md)) | regla o motivo y consumos |

**Contexto en todas las líneas de una petición** (vía `contextvars`):
- `request_id`;
- `session`: SHA-256 de la cookie, 16 caracteres; nunca la cookie;
- `conversation_id`;
- `turn_id` y `trace_id`. `trace_id` es igual a `turn_id` y sirve para `GET /api/traces/{turn_id}`.

**Nunca en los logs:**
- contraseñas, tokens de sesión, CSRF o confirmación, cookies, cabeceras de autorización ni claves de API;
- el texto del cliente (mensajes, afirmaciones).

Los campos con esos nombres se reemplazan por `[oculto]` (`redact`). El texto completo queda en `app.turns` y `app.traces`, con su propio control de acceso (consola de analista). Hay un test que verifica que la contraseña, la cookie, el CSRF y el texto no aparecen en la salida.

El access log de uvicorn está desactivado: duplicaría el nuestro y no lleva `request_id`.

## request_id

- La respuesta siempre trae `X-Request-ID`, para cruzar frontend, logs y trazas.
- Si la petición trae un `X-Request-ID` seguro (letras, números, `_` o `-`; de 8 a 64 caracteres), se usa ese, del frontend o del proxy. Si no, se genera uno.
- El frontend puede mostrarlo en los errores ("código de referencia") para soporte.

## Salud y preparación

| Ruta | Para | Responde |
|---|---|---|
| `GET /api/health` | Vida (*liveness*): el proceso responde. | `200 {"status": "ok"}` |
| `GET /api/ready` | Preparación (*readiness*): la base de lectura/escritura y la de solo lectura responden, y la configuración del LLM está completa. | `200 {"status": "ready", "checks": {...}, "llm_provider"}` o `503 not_ready`, con el chequeo que falló |

- **`/api/ready` no llama al LLM** (costaría):
  - con `anthropic_api` verifica que exista `ANTHROPIC_API_KEY`;
  - con `claude_cli`, que exista el binario `claude`.
- Ninguna de las dos rutas cuenta para los límites de peticiones.

## Métricas

`GET /api/metrics?days=7` (rol `analyst`), para el panel de administración futuro:

- `endpoints`: por método y ruta (plantilla): peticiones, errores 4xx y 5xx, 429 y latencia p50/p95. Viven en memoria y se reinician con el proceso; la muestra son las últimas 2.000 peticiones por ruta.
- `llm_daily`: vista `app.v_llm_daily` (migración 0006). Por día UTC, nodo, modelo y proveedor: llamadas, errores, fallbacks, costo y latencia p50/p95.
- `turns_daily`: vista `app.v_turn_daily`. Por día: turnos, latencia (suma de pasos, p50/p95), costo, llamadas al LLM y turnos con error.
  - La suma de pasos aproxima el tiempo del turno. Intent y extract corren en paralelo, así que suman los dos; el tiempo real por petición está en `endpoints`.

Las vistas también se pueden consultar con el usuario de la consola (`app_ro`).
