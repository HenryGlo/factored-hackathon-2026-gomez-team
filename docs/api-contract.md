# Contrato de API

> **[Propuesta]** Todo este documento es una propuesta. Los endpoints listados son **[Decisión]** del equipo; las formas de petición y respuesta pueden cambiar durante la implementación. Cualquier cambio se actualiza aquí en el mismo PR.

Base: `/api`. Formato: JSON. Fechas en ISO 8601. Montos como string decimal (`"120.00"`) para no perder precisión.

## Autenticación

**[Oficial]** Demostrar autenticación con una sesión de prueba confiable; un número de cliente solo no prueba identidad.

**[Decisión]** Login con usuario y contraseña. Reemplaza la sesión de prueba sin contraseña (`POST /api/session` y `GET /api/demo/customers` ya no existen). Implementado en [backend/app/auth/](../backend/app/auth/).

- **Usuarios** en `app.users`, con contraseña en argon2id. Dos roles:
  - `customer`: cliente del banco, ligado a un `customer_id`.
  - `analyst`: persona de la consola del banco. No se llama `agent`, para no confundirla con el agente de IA en código y trazas.
  - Los usuarios demo los crea `scripts/seed_demo_users.py` ([postgres.md](data/postgres.md#usuarios-demo)). La contraseña demo está solo en `.env` (`DEMO_PASSWORD`).
- **Sesión:** cookie `session` httpOnly, `SameSite=Lax`, `Secure` en producción (`APP_ENV=production`). En la base solo se guarda el SHA-256 del token.
  - Vence tras `SESSION_IDLE_MINUTES` de inactividad (30 por defecto); cada petición válida desliza el vencimiento.
  - Nunca dura más de `SESSION_MAX_HOURS` (12).
- **CSRF (doble envío):** toda petición que cambia estado envía la cabecera `X-CSRF-Token` con el valor de la cookie `csrf_token`, que es legible por el frontend. Tras el login, ese token queda ligado a la sesión (se guarda su hash); un token de otra sesión no sirve. Antes del login se pide uno con `GET /api/auth/csrf`.
- **Identidad:** el `customer_id` de cualquier operación sale **siempre** de la sesión. Ningún endpoint lo acepta en el cuerpo ni en la URL, y los cuerpos rechazan campos desconocidos (`422`).
- **Límite de intentos:** un usuario con 5 fallos en 15 minutos queda bloqueado, aunque luego acierte la contraseña. Una IP con 20 fallos, también. En ambos casos se responde `429 rate_limited`.
  - Un login correcto reinicia el contador del usuario.
  - Todos los intentos quedan en `app.login_events`.
  - Los valores se configuran con `LOGIN_WINDOW_MINUTES`, `LOGIN_MAX_FAILURES_USER` y `LOGIN_MAX_FAILURES_IP`.
- **Consola:** exige rol `analyst` y lee con el usuario de base de datos de solo lectura (`CONSOLE_DATABASE_URL`, grupo `app_ro`).

## Endpoints

| Método | Ruta | Rol | Propósito |
|---|---|---|---|
| GET | `/api/auth/csrf` | público | Token CSRF previo al login. |
| POST | `/api/auth/login` | público | Inicia sesión (cookie `session` + `csrf_token`). |
| POST | `/api/auth/logout` | cualquiera con sesión | Revoca la sesión. |
| GET | `/api/auth/me` | cualquiera con sesión | Rol y nombre visible. |
| POST | `/api/conversations` | customer | Crea una conversación. |
| POST | `/api/conversations/{id}/turns` | customer | Envía un mensaje o una acción. |
| GET | `/api/conversations/{id}` | customer (dueño) / analyst | Estado e historial de bloques. |
| GET | `/api/cases` | analyst | Lista de reclamos creados por el sistema. |
| GET | `/api/cases/{id}` | analyst | Detalle de un reclamo. |
| GET | `/api/handoffs` | analyst | Lista de handoffs. |
| GET | `/api/handoffs/{id}` | analyst | Detalle de un handoff. |
| GET | `/api/traces/{turn_id}` | analyst | Traza de ejecución de un turno. |

**[Decisión]** Implementado (fases 1–5 del [prompt 03](prompts/03-backend-harness.md)) en [backend/app/conversations.py](../backend/app/conversations.py) y [backend/app/controller/](../backend/app/controller/). **Respuesta única por turno, sin SSE:** el turno se procesa completo. Con LLM real tarda varios segundos ([llm-data.md](llm-data.md)) y el frontend muestra un indicador mientras espera.

### GET /api/auth/csrf

Respuesta `200`: `{"csrf_token": "…"}`. También deja la cookie `csrf_token`.

### POST /api/auth/login

Cabecera: `X-CSRF-Token` igual a la cookie `csrf_token`.

Petición:

```json
{"username": "demo_cargo_claro_1", "password": "…", "language": "es"}
```

`language` (`es` | `pt`) es opcional. Cualquier otro campo (por ejemplo `customer_id`) → `422`.

Respuesta `200` (y cookies `session` y `csrf_token` nuevas):

```json
{"role": "customer", "display_name": "Nombre A.", "language": "es", "expires_at": "…", "idle_timeout_minutes": 30, "csrf_token": "…"}
```

Errores:

- `401 invalid_credentials`: mismo mensaje si el usuario no existe, si la contraseña es errónea o si el usuario está inactivo.
- `403 csrf_failed`.
- `429 rate_limited`, con cabecera `Retry-After`.

### POST /api/auth/logout

Cabecera `X-CSRF-Token`. Respuesta `204`: revoca la sesión y borra las cookies. Reusar el token después devuelve `401 unauthorized`.

### GET /api/auth/me

Respuesta `200`:

```json
{"role": "analyst", "display_name": "Analista 1", "language": null, "expires_at": "…", "idle_timeout_minutes": 30}
```

### POST /api/conversations

Cabeceras: cookie de sesión, `X-CSRF-Token`. Rol `customer`. Cuerpo opcional: `{"language": "es" | "pt"}`.

Respuesta `201`: `{conversation_id, state: "inicio", language, session_date, blocks: [text de saludo], data_as_of}`. `session_date` es el "hoy" de la conversación: `REFERENCE_DATE` o el último día con transacciones cargadas (P-08).

### POST /api/conversations/{id}/turns

Cabeceras: cookie de sesión, `X-CSRF-Token`, `Idempotency-Key` (**obligatoria**). Rol `customer`, dueño de la conversación.

Petición: un mensaje **o** una acción. Campos desconocidos (por ejemplo `customer_id`) → `422`.

```json
{"message": "Tengo un cobro de $120 que no reconozco"}
```

| Acción | Campos | Cuándo |
|---|---|---|
| `select_candidate` | `transaction_id` | Elegir una candidata mostrada. Con el mismo id en `confirmando_movimiento` = "sí, es este". |
| `dispute_transaction` | `transaction_id` | "No reconozco este cargo" desde un `transaction_list` mostrado. Pasa igual por política y confirmación. |
| `select_card` | `product_id` | Elegir la tarjeta a bloquear de un `card_list`. |
| `confirm` | `confirmation_token` | Ejecutar la acción de un `action_confirmation`. |
| `reject` | — | "No es ninguno", "no es este" o "no confirmo". |
| `request_human` | — | Pasar a una persona en cualquier estado. |

Un ID que no estaba entre las opciones mostradas en ese paso → `409 invalid_state`. El texto libre ("sí, confirmo") nunca ejecuta una acción con efecto (R4).

Respuesta `200`:

```json
{
  "turn_id": "turn_…",
  "conversation_id": "conv_…",
  "state": "confirmando_movimiento",
  "language": "es",
  "clarification_round": 0,
  "input": {"message": "…"},
  "blocks": [
    {"type": "text", "text": "¿Es este el movimiento al que te refieres? Super Ahorro por 423,23 USD el 08/06/2026."},
    {"type": "transaction_card", "transaction": {"transaction_id": "TRX-…", "date": "2026-06-08T12:50:17", "amount": "423.23", "currency": "USD",
     "merchant_name": "Super Ahorro", "label": "Super Ahorro", "channel": "POS", "type": "Purchase", "status": "Approved"}, "source": "get_transaction"}
  ],
  "data_as_of": {"data_as_of": "2026-06-17", "max_transaction_date": "2026-06-18T05:59:41"},
  "trace_id": "turn_…"
}
```

- `trace_id` es igual a `turn_id` (`GET /api/traces/{turn_id}`).
- El aviso de frescura al cliente usa `data_as_of.max_transaction_date` ([postgres.md](data/postgres.md#política-de-frescura)).
- Un reintento con la misma `Idempotency-Key` y el mismo cuerpo devuelve la misma respuesta con `"replayed": true`.
- Una conversación `cerrado` o `escalado` no acepta turnos: `409 conversation_closed`, y se crea otra (P-26).

### GET /api/conversations/{id}

Respuesta `200`: `{conversation_id, state, language, clarification_round, created_at, turns: [{turn_id, role, message | action, blocks}]}`.

### GET /api/cases y /api/cases/{id}

Respuesta `200` (detalle): `{case_id, customer_id, transaction_id, status, reason_code, customer_statement, policy_rules_applied, created_at, conversation_id, turn_id}`. La lista acepta filtros `status`, `created_from`, `created_to`, `limit`, `cursor`.

### GET /api/handoffs y /api/handoffs/{id}

Respuesta `200` (detalle): el objeto definido en [handoff-schema.md](handoff-schema.md).

### GET /api/traces/{turn_id}

Rol `analyst` (usuario de solo lectura). Respuesta `200`: `{turn_id, conversation_id, state_before, state_after, steps[], totals {latency_ms, cost_usd}}`. Cada paso:

| Campo | Contenido |
|---|---|
| `step_seq`, `node` | `entrada`, `intent`, `extract`, `fechas`, `tool:search_transactions`, `ranking`, `aclaracion`, `fraud_risk`, `politica`, `token_emitido`, `ejecutando`, `tool:create_dispute_case`, `verificacion`, `handoff_summary`, … |
| `kind` | `llm`, `ml` o `code` (tools, política y controlador son código). |
| `implementation` | Implementación y versión (`keyword@v1`, `rule@v3`, `raw_fraud_score@v1`, `threshold@v2`, `policy@v1`, `fake`/`claude_cli`). |
| `model`, `model_id`, `prompt_version` | Alias pedido, ID real y versión del prompt (pasos LLM). |
| `latency_ms`, `cost_usd`, `error` | Medición y error, si hubo. |
| `payload` | Entrada y salida del paso, y `fallback` si se usó plantilla o reglas. En los pasos `clarify` y `confirm`, además, `modo` (`llm` o `plantilla`) y `motivo` (tipo de aclaración o acción a confirmar). |
| `rules` | Reglas evaluadas `{id, resultado, motivo, evidencia}` (paso `politica`). |

**[Oficial]** La traza no incluye cadena de pensamiento oculta; solo entradas, salidas, fuentes, reglas y registros de ejecución.

## Catálogo de bloques de UI

**[Decisión]** La API devuelve una lista ordenada de bloques. El frontend solo renderiza; no decide.

| `type` | Campos | Cuándo |
|---|---|---|
| `text` | `text` | Cualquier respuesta en lenguaje natural. |
| `candidate_list` | `prompt`, `candidates[]` (`transaction_id`, `date`, `amount`, `currency`, `merchant_name` (o null), `label` (texto a mostrar, traducido), `channel`, `type`, `status`, `rank`), `allow_none`, `round`, `max_rounds` | Aclaración: varias candidatas, o el par de un cobro duplicado. |
| `transaction_list` | `period {from, to}`, `filters`, `count`, `totals[]` (`currency`, `count`, `total`), `transactions[]`, `can_dispute` | Consulta de movimientos (solo lectura). Totales y conteos calculados por el código. |
| `card_list` | `cards[]` (`product_id`, `label` "crédito ···1234", `product_type`, `status`) | Bloqueo: el cliente tiene varias tarjetas. |
| `case_list` | `cases[]` (`case_id`, `status`, `reason_code`, `created_at`, `transaction {label, amount, currency, date}`) | Estado de reclamos. |
| `transaction_card` | `transaction` (mismos campos que una candidata), `source` (`get_transaction`) | Confirmar un movimiento. |
| `action_confirmation` | `action` (`create_dispute_case` \| `lock_card` \| `create_handoff`), `summary`, `params`, `confirmation_token`, `expires_at`, `disclaimer` | Antes de toda acción con efecto. `create_handoff` = reposición de tarjeta tras un bloqueo. |
| `result` | `action`, `status` (`success` \| `failed`), `verified` (bool), `reference_id`, `details` | Después de actuar y verificar. |
| `handoff_notice` | `handoff_id`, `reason_code`, `message`, `next_step` | Escalamiento a persona. |
| `notice` | `level` (`info` \| `warning`), `code` (p. ej. `pending_transaction`, `existing_case`, `out_of_scope`, `no_refund_approval`), `text` | Información de política o alcance. |
| `error` | `code`, `message`, `retryable` | Errores visibles al cliente. |

Regla: un bloque `result` con `status: success` solo se emite si `verified: true`.

## Idempotency-Key

**[Propuesta]**

- Obligatoria en `POST /api/conversations/{id}/turns`; opcional en `POST /api/conversations`.
- Valor: UUID generado por el cliente por cada intento lógico (un reintento de red reusa la misma clave).
- El servidor guarda `(session_id, clave) → hash del cuerpo + respuesta` en `app.idempotency_keys` (24 h). La clave se reserva antes de procesar: un segundo envío mientras el primero sigue en curso → `409 idempotency_in_progress`, reintentable.
- Misma clave y mismo cuerpo → devuelve la respuesta guardada, sin re-ejecutar nodos ni tools.
- Misma clave y cuerpo distinto → `409 idempotency_conflict`.
- Objetivo: que un doble clic o un reintento no cree dos reclamos. La protección de negocio contra duplicados es aparte (R3).

## confirmation_token

**[Propuesta]**

- Lo emite el controlador dentro de un bloque `action_confirmation`, nunca el LLM.
- Opaco, de un solo uso, con vencimiento (`CONFIRMATION_TOKEN_TTL_SECONDS`, 300 s por defecto). Solo se guarda su hash (`app.confirmation_tokens`).
- Ligado a `session_id`, `conversation_id`, `action` y el hash de `params` (p. ej. `transaction_id`).
- El tool de escritura (`create_dispute_case`, `lock_card`, `create_handoff`) lo valida y lo consume en la misma transacción en que escribe. Si no coincide, venció, ya se usó, se anuló o es de otra sesión, falla con `invalid_confirmation` y no hay efecto.
- Se anula al emitir otro (cambio de movimiento, nueva confirmación) y al rechazar.
- Si la sesión venció a mitad de la confirmación, después del nuevo login el token viejo no sirve: el turno devuelve `error: invalid_confirmation` y un `action_confirmation` nuevo, con la política revalidada. La conversación se retoma sin ejecutar nada pendiente.
- Al confirmar se revalidan la pertenencia y las reglas (R1, R2, R3, R6) antes de actuar.
- Escribir "sí, confirmo" en texto libre no ejecuta la acción; el frontend envía la acción `confirm` con el token.

## Errores

| HTTP | `code` | Significado |
|---|---|---|
| 400 | `validation_error` | Cuerpo inválido. |
| 401 | `session_expired` / `unauthorized` | Sesión vencida por inactividad / ausente, inválida o revocada. |
| 401 | `invalid_credentials` | Login fallido (mensaje genérico). |
| 403 | `forbidden` | Rol incorrecto (p. ej. cliente en la consola). |
| 403 | `csrf_failed` | Falta la cabecera `X-CSRF-Token` o no coincide con la de la sesión. |
| 404 | `not_found` | El recurso no existe **o no pertenece a la sesión** (no se distingue, para no filtrar existencia). |
| 409 | `idempotency_conflict` | Clave reutilizada con cuerpo distinto. |
| 409 | `idempotency_in_progress` | La misma clave todavía se está procesando (doble clic). Reintentable. |
| 409 | `conversation_closed` | Turno en una conversación `cerrado` o `escalado`. |
| 409 | `invalid_state` | Acción no válida en el estado actual. |
| 429 | `rate_limited` | Demasiados intentos de login (usuario o IP). Límites de otras rutas: pendiente (P-06). |
| 503 | `dependency_unavailable` | Falló el LLM o un tool tras reintentos; la respuesta incluye un fallback seguro. |

Errores dentro de la conversación (por ejemplo, fallo de un tool) se devuelven como `200` con un bloque `error` y, si aplica, `handoff_notice`.
