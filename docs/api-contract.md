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

Implementado a la fecha (fase 1): `/api/auth/*` y `GET /api/cases`. El resto llega en las fases 4–5 del [prompt 03](prompts/03-backend-harness.md).

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

Cabeceras: cookie de sesión, `X-CSRF-Token`, `Idempotency-Key` (opcional).

Respuesta `201`:

```json
{"conversation_id": "conv_…", "state": "inicio", "blocks": [{"type": "text", "text": "Hola, ¿en qué te ayudo?"}]}
```

### POST /api/conversations/{id}/turns

Cabeceras: cookie de sesión, `X-CSRF-Token`, `Idempotency-Key` (**obligatoria**).

Petición: un mensaje **o** una acción.

```json
{"message": "Tengo un cobro de $120 que no reconozco"}
```

```json
{"action": {"type": "select_candidate", "transaction_id": "TRX-…"}}
{"action": {"type": "confirm", "confirmation_token": "ct_…"}}
{"action": {"type": "reject"}}
{"action": {"type": "request_human"}}
```

Respuesta `200`:

```json
{
  "turn_id": "turn_…",
  "conversation_id": "conv_…",
  "state": "confirmando_movimiento",
  "language": "es",
  "blocks": [
    {"type": "text", "text": "Encontré este cargo. ¿Es el que no reconoces?"},
    {"type": "transaction_card", "transaction": {"transaction_id": "TRX-…", "date": "…", "amount": "120.00", "currency": "USD", "merchant_name": "…", "channel": "App", "status": "Approved"}}
  ]
}
```

### GET /api/conversations/{id}

Respuesta `200`: `{conversation_id, state, language, clarification_round, created_at, turns: [{turn_id, role, message | action, blocks}]}`.

### GET /api/cases y /api/cases/{id}

Respuesta `200` (detalle): `{case_id, customer_id, transaction_id, status, reason_code, customer_statement, policy_rules_applied, created_at, conversation_id, turn_id}`. La lista acepta filtros `status`, `created_from`, `created_to`, `limit`, `cursor`.

### GET /api/handoffs y /api/handoffs/{id}

Respuesta `200` (detalle): el objeto definido en [handoff-schema.md](handoff-schema.md).

### GET /api/traces/{turn_id}

Respuesta `200`:

```json
{
  "turn_id": "turn_…",
  "state_before": "inicio",
  "state_after": "confirmando_movimiento",
  "steps": [
    {"node": "intencion", "kind": "llm", "model": "…", "prompt_version": "intent@v1", "latency_ms": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": "0", "output": {"intent": "disputa", "language": "es"}},
    {"node": "busqueda_ranking", "kind": "tool", "tool": "search_transactions", "args": {"amount": "120"}, "result_summary": {"n_candidates": 3, "top_score": 0.0}, "model_version": "ranker@…", "latency_ms": 0},
    {"node": "politica", "kind": "policy", "rules": [{"rule": "R1", "result": "pass", "evidence": {"days_since": 5}}]}
  ],
  "totals": {"latency_ms": 0, "cost_usd": "0"}
}
```

Los valores `0` son marcadores de forma, no mediciones. **[Oficial]** La traza no incluye cadena de pensamiento oculta; solo entradas, salidas, fuentes, reglas y registros de ejecución.

## Catálogo de bloques de UI

**[Decisión]** La API devuelve una lista ordenada de bloques. El frontend solo renderiza; no decide.

| `type` | Campos | Cuándo |
|---|---|---|
| `text` | `text` | Cualquier respuesta en lenguaje natural. |
| `candidate_list` | `prompt`, `candidates[]` (`transaction_id`, `date`, `amount`, `currency`, `merchant_name`, `channel`, `status`, `rank`), `allow_none`, `round`, `max_rounds` | Aclaración: varias candidatas. |
| `transaction_card` | `transaction` (mismos campos que una candidata), `source` (`get_transaction`) | Confirmar un movimiento. |
| `action_confirmation` | `action` (`create_dispute_case` \| `lock_card`), `summary`, `params`, `confirmation_token`, `expires_at`, `disclaimer` | Antes de toda acción con efecto. |
| `result` | `action`, `status` (`success` \| `failed`), `verified` (bool), `reference_id`, `details` | Después de actuar y verificar. |
| `handoff_notice` | `handoff_id`, `reason_code`, `message`, `next_step` | Escalamiento a persona. |
| `notice` | `level` (`info` \| `warning`), `code` (p. ej. `pending_transaction`, `existing_case`, `out_of_scope`, `no_refund_approval`), `text` | Información de política o alcance. |
| `error` | `code`, `message`, `retryable` | Errores visibles al cliente. |

Regla: un bloque `result` con `status: success` solo se emite si `verified: true`.

## Idempotency-Key

**[Propuesta]**

- Obligatoria en `POST /api/conversations/{id}/turns`; opcional en `POST /api/conversations`.
- Valor: UUID generado por el cliente por cada intento lógico (un reintento de red reusa la misma clave).
- El servidor guarda `(session_id, clave) → hash del cuerpo + respuesta` durante `IDEMPOTENCY_TTL_HOURS` (Pendiente: valor, P-11).
- Misma clave y mismo cuerpo → devuelve la respuesta guardada, sin re-ejecutar nodos ni tools.
- Misma clave y cuerpo distinto → `409 idempotency_conflict`.
- Objetivo: que un doble clic o un reintento no cree dos reclamos. La protección de negocio contra duplicados es aparte (R3).

## confirmation_token

**[Propuesta]**

- Lo emite el controlador dentro de un bloque `action_confirmation`, nunca el LLM.
- Opaco, de un solo uso, con vencimiento (`CONFIRMATION_TOKEN_TTL_SECONDS`; Pendiente: valor, P-11).
- Ligado a `session_id`, `conversation_id`, `action` y el hash de `params` (p. ej. `transaction_id`).
- El tool de escritura (`create_dispute_case`, `lock_card`) lo valida y lo consume. Si no coincide, venció o ya se usó, falla con `invalid_confirmation` y no hay efecto.
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
| 409 | `invalid_state` | Acción no válida en el estado actual. |
| 429 | `rate_limited` | Demasiados intentos de login (usuario o IP). Límites de otras rutas: pendiente (P-06). |
| 503 | `dependency_unavailable` | Falló el LLM o un tool tras reintentos; la respuesta incluye un fallback seguro. |

Errores dentro de la conversación (por ejemplo, fallo de un tool) se devuelven como `200` con un bloque `error` y, si aplica, `handoff_notice`.
