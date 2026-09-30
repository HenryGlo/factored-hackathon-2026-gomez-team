# Contrato de API

> **[Propuesta]** Todo este documento es una propuesta. Los endpoints listados son **[Decisión]** del equipo; las formas de petición y respuesta pueden cambiar durante la implementación. Cualquier cambio se actualiza aquí en el mismo PR.

Base: `/api`. Formato: JSON. Fechas en ISO 8601. Montos como string decimal (`"120.00"`) para no perder precisión.

## Autenticación

**[Oficial]** Demostrar autenticación con una sesión de prueba confiable; un número de cliente solo no prueba identidad.

**[Propuesta]**

- `POST /api/session` emite un `session_token` opaco con vencimiento. Actúa como proveedor de identidad simulado sobre clientes de demo (sandbox documentado).
- Todas las demás llamadas envían `Authorization: Bearer <session_token>`.
- La sesión tiene un `role`: `customer` (chat) o `agent` (consola). Pendiente: cómo se autentica la consola (P-12).
- TTL de sesión: `SESSION_TTL_MINUTES`. Pendiente: valor (P-11).

## Endpoints

| Método | Ruta | Rol | Propósito |
|---|---|---|---|
| GET | `/api/demo/customers` | público (demo) | Lista de clientes de prueba para iniciar sesión. |
| POST | `/api/session` | público (demo) | Crea una sesión de prueba. |
| POST | `/api/conversations` | customer | Crea una conversación. |
| POST | `/api/conversations/{id}/turns` | customer | Envía un mensaje o una acción. |
| GET | `/api/conversations/{id}` | customer (dueño) / agent | Estado e historial de bloques. |
| GET | `/api/cases` | agent | Lista de reclamos creados por el sistema. |
| GET | `/api/cases/{id}` | agent | Detalle de un reclamo. |
| GET | `/api/handoffs` | agent | Lista de handoffs. |
| GET | `/api/handoffs/{id}` | agent | Detalle de un handoff. |
| GET | `/api/traces/{turn_id}` | agent | Traza de ejecución de un turno. |

### GET /api/demo/customers

Respuesta `200`:

```json
{
  "customers": [
    {"customer_id": "CLI-…", "display_name": "Nombre A.", "country": "México", "segment": "Plus", "scenario": "normal"}
  ]
}
```

`scenario` describe para qué sirve el cliente en la demo (`normal`, `ambiguo`, `requiere_humano`). Sin documento, email ni teléfono.

### POST /api/session

Petición:

```json
{"customer_id": "CLI-…", "role": "customer", "language": "es"}
```

Respuesta `201`:

```json
{"session_id": "ses_…", "session_token": "…", "role": "customer", "expires_at": "…", "customer": {"display_name": "Nombre A.", "country": "México"}}
```

### POST /api/conversations

Cabeceras: `Authorization`, `Idempotency-Key` (opcional).

Respuesta `201`:

```json
{"conversation_id": "conv_…", "state": "inicio", "blocks": [{"type": "text", "text": "Hola, ¿en qué te ayudo?"}]}
```

### POST /api/conversations/{id}/turns

Cabeceras: `Authorization`, `Idempotency-Key` (**obligatoria**).

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
| 401 | `session_expired` / `unauthorized` | Sesión vencida o ausente. |
| 404 | `not_found` | El recurso no existe **o no pertenece a la sesión** (no se distingue, para no filtrar existencia). |
| 409 | `idempotency_conflict` | Clave reutilizada con cuerpo distinto. |
| 409 | `invalid_state` | Acción no válida en el estado actual. |
| 429 | `rate_limited` | Límite de peticiones. Pendiente: límites (P-06). |
| 503 | `dependency_unavailable` | Falló el LLM o un tool tras reintentos; la respuesta incluye un fallback seguro. |

Errores dentro de la conversación (por ejemplo, fallo de un tool) se devuelven como `200` con un bloque `error` y, si aplica, `handoff_notice`.
