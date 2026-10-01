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
| GET | `/api/conversations/{id}/phase` | customer (dueño) | Fase real del turno en curso, para el indicador de espera ([detalle](#get-apiconversationsidphase)). |
| GET | `/api/cases` | analyst | Lista de reclamos creados por el sistema. |
| GET | `/api/cases/{id}` | analyst | Detalle de un reclamo. |
| GET | `/api/handoffs` | analyst | Lista de handoffs. |
| GET | `/api/handoffs/{id}` | analyst | Detalle de un handoff. |
| GET | `/api/traces/{turn_id}` | analyst | Traza de ejecución de un turno. |
| GET | `/api/me/transactions` | customer | Mis movimientos: lectura directa, sin LLM ([detalle](#get-apimetransactions-y-apimecases)). |
| GET | `/api/me/cases` | customer | Mis reclamos. |
| GET | `/api/health` | público | Vida: el proceso responde. |
| GET | `/api/ready` | público | Preparación: base y configuración del LLM ([observability.md](observability.md)). `503` si algo falla. |
| GET | `/api/admin/metrics/operations` | analyst | Cómo terminaron las conversaciones del periodo ([detalle](#get-apiadminmetrics)). |
| GET | `/api/admin/metrics/latency` | analyst | Latencia, errores y costo por nodo. |
| GET | `/api/admin/metrics/roi` | analyst | ROI estimado con supuestos editables. |
| GET | `/api/metrics` | analyst | Latencia y errores por endpoint, llamadas y costo del LLM por día ([observability.md](observability.md#métricas)). |

**Toda respuesta** trae la cabecera `X-Request-ID`. Si la petición envía una válida (8–64 caracteres `[A-Za-z0-9_-]`), se respeta; si no, se genera. El frontend puede mostrarla como código de referencia en los errores.

**[Decisión]** Implementado (fases 1–5 del [prompt 03](prompts/03-backend-harness.md)) en [backend/app/conversations.py](../backend/app/conversations.py) y [backend/app/controller/](../backend/app/controller/). **Respuesta única por turno, sin SSE:** el turno se procesa completo. Con LLM real tarda varios segundos ([llm-data.md](llm-data.md)) y el frontend muestra un indicador con la fase real del turno ([`GET /api/conversations/{id}/phase`](#get-apiconversationsidphase)).

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

Cabeceras: cookie de sesión, `X-CSRF-Token`. Rol `customer`. Cuerpo opcional: `{"language": "es" | "pt", "previous_conversation_id": "conv_…"}`.

- `previous_conversation_id`: una conversación anterior del mismo cliente; si es de otro cliente, `404`.
  - La nueva hereda el cargo en foco y las últimas afirmaciones del cliente, además del idioma y del "hoy".
  - El frontend la usa cuando un mensaje llega a una conversación cerrada: crea una nueva enlazada y reenvía el mensaje, sin mostrar el error.

Respuesta `201`: `{conversation_id, state: "inicio", language, session_date, blocks: [text de saludo], data_as_of, previous_conversation_id, focus}`. `focus` (bool) indica si heredó un cargo en foco. `session_date` es el "hoy" de la conversación: `REFERENCE_DATE` o el último día con transacciones cargadas (P-08).

### POST /api/conversations/{id}/turns

Cabeceras: cookie de sesión, `X-CSRF-Token`, `Idempotency-Key` (**obligatoria**). Rol `customer`, dueño de la conversación.

Petición: un mensaje **o** una acción. Campos desconocidos (por ejemplo `customer_id`) → `422`.

```json
{"message": "Tengo un cobro de $120 que no reconozco"}
```

| Acción | Campos | Cuándo |
|---|---|---|
| `select_candidate` | `transaction_id` | Elegir una candidata mostrada. Con el mismo id en `confirmando_movimiento` = "sí, es este". |
| `select_candidates` | `transaction_ids` (2–10) | Elegir varias candidatas de una `candidate_list` con `multi_select` ("Todos estos" = todos los ids mostrados). Con un solo id equivale a `select_candidate`. |
| `new_request` | — | Respuesta rápida "Sí, otra consulta" (estado `inicio`). |
| `end_conversation` | — | Respuesta rápida "No, gracias": cierra la conversación (`closed_reason = cliente`). |
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
- **Ciclo de vida (2026-10-01):** ningún resultado cierra la conversación (resolver, informar, escalar o abstenerse). Al terminar un flujo, el estado vuelve a `inicio` y la respuesta trae el texto "¿Hay algo más en lo que te pueda ayudar?" y un bloque `quick_replies`.
- **Cuándo se cierra (`cerrado`):** cuando el cliente se despide (texto o `end_conversation`) o tras `conversation_idle_minutes` (15) sin turnos. `escalado` ya no se usa; queda solo en conversaciones viejas.
- **Turno en una conversación cerrada:** `409 conversation_closed` con `details: {reason: "cliente" | "inactividad", conversation_id}`. El 409 es para la API; el frontend crea una conversación enlazada con `previous_conversation_id` y reenvía el mensaje.

### GET /api/conversations/{id}/phase

**[Decisión]** 2026-10-01. El indicador de espera no adivina por tiempo: muestra la fase real del turno. Se eligió un **sondeo
corto** en vez de SSE: el turno sigue siendo una única respuesta `POST` (idempotente, sin conexiones largas que un proxy pueda
cortar), y si el sondeo falla el turno no se entera.

- Respuesta: `{"phase": "understanding" | "searching_transactions" | "checking_policy" | "writing" | null}`.
  - `understanding`: desde que llega el turno. `searching_transactions`: solo cuando el turno llama de verdad a la herramienta
    `search_transactions`. `checking_policy`: al evaluar R1–R6 sobre un movimiento. `writing`: al redactar con un nodo LLM.
  - `null`: no hay turno en curso, la conversación no es del cliente, o la consulta cayó en otra instancia (la fase vive en
    la memoria del proceso).
- El frontend sondea cada ~0,7 s solo mientras espera un turno. Texto por defecto, neutro: "Escribiendo…" / "Digitando…".
  Muestra "Buscando en tus movimientos…" / "Procurando nos seus lançamentos…" solo cuando llega `searching_transactions`.
  Si el sondeo falla (red, 429, 404), se queda el texto neutro.
- Límite propio `phase_session` (240/min por sesión); no consume los límites generales ([security.md](security.md)).

### GET /api/admin/metrics/*

**[Decisión]** 2026-10-01 (prompt 07, bloque 4). Para el panel de administración. Rol `analyst` (el rol `admin` llega con la parte A
del prompt 08). Solo lectura, con el usuario de solo lectura de la base. Parámetro `days` (1–365).

- **`GET /api/admin/metrics/operations?days=30`** →
  `{days, conversations, resolved_automatically: {n, of, share}, resolved_after_clarification: {…}, escalated: {…}, no_action: {…}, handoffs: [{reason_code, priority, n}]}`.
  Una conversación cuenta como *escalada* si tiene un handoff (sin contar la reposición de tarjeta); *resuelta* si dejó un reclamo
  o un bloqueo, *con aclaración* si hubo un paso `clarify`; *sin acción* en otro caso (consultas, preguntas, abstenciones).
- **`GET /api/admin/metrics/latency?days=7`** → `{days, nodes: [{node, kind, calls, errors, p50_ms, p95_ms, cost_usd}]}` (nodos LLM y tools).
- **`GET /api/admin/metrics/roi?days=30`** → `{label, assumptions, estimate: {human_cost_per_case_usd, saving_per_case_usd, monthly_saving_usd, break_even_cases_per_month}, measured: {conversations, not_escalated_share, llm_cost_per_conversation_usd}}`.
  `label` dice que es una **estimación**; los supuestos salen de `backend/config/roi.toml`. El panel debe mostrar esa etiqueta.

### GET /api/me/transactions y /api/me/cases

**[Decisión]** 2026-10-01, para las pantallas "Mis movimientos" y "Mis reclamos" (parte D del prompt 04). Solo lectura, sin LLM. El `customer_id` sale de la sesión.

- **`GET /api/me/transactions`:**
  - Parámetros opcionales: `from` y `to` (AAAA-MM-DD; por defecto, los últimos 30 días hasta `session_date`), `merchant` (texto), `status` (`Approved` | `Pending` | `Declined` | `Reversed`), `limit` (≤ 50) y `lang` (`es` | `pt`).
  - Respuesta: `{period {from, to}, session_date, filters, count, totals[] (currency, count, total, total_label), transactions[] (como candidate_list, con amount_label, date_label y status_label), data_as_of}`.
  - Errores: período inválido o mayor a un año → `400`.
- **`GET /api/me/cases?lang=`:** `{cases[] (case_id, status, reason_code, created_at, transaction {transaction_id, label, amount, currency, date, amount_label, date_label})}`.
- **"No reconozco este cargo" desde Mis movimientos:**
  1. `POST /api/conversations` con `{"dispute_transaction_id": "TRX-…"}`. El movimiento debe ser del cliente; si no, `404`.
  2. En esa conversación, la acción `dispute_transaction` con ese id. Pasa por política, confirmación y verificación igual que desde el chat.

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
| `candidate_list` | `prompt`, `candidates[]` (`transaction_id`, `date`, `amount`, `currency`, `merchant_name` (o null), `label` (texto a mostrar, traducido), `channel`, `type`, `status`, `rank`, y ya formateados según el idioma `amount_label` ("423,23 USD"), `date_label` ("8 jun 2026" / "8 jun. 2026") y `status_label` (es: Aprobado, Pendiente, Revertido, Rechazado; pt: Aprovado, Pendente, Revertido, Recusado)), `allow_none`, `round`, `max_rounds`; con varios cargos además `multi_select: true`, `suggested[]` (ids preseleccionados) y `select_all_label` | Aclaración: varias candidatas, o el par de un cobro duplicado. Con `multi_select`, el cliente elige varias (`select_candidates`). |
| (presentación) | — | El texto de una aclaración no repite la lista: la lista va solo en `candidate_list`. Montos y fechas usan el mismo formato en bloques y textos. `transaction_list.totals[]` trae `total_label`; `case_list[].transaction`, `amount_label` y `date_label`. |
| (referencias) | — | Reclamos y atenciones traen `reference_label`, una referencia corta para el cliente (`RCL-1A2B3C`, `ATN-…`). Va en `result` (y en `items[]`), `handoff_notice`, `case_list` y `GET /api/me/cases`. El frontend del cliente muestra `reference_label`; el ID interno (`reference_id`, `case_id`, `handoff_id`) queda para la consola y la trazabilidad. |
| `quick_replies` | `options[]` (`label`, `action`) | Tras terminar un flujo: "Sí, otra consulta" (`new_request`) y "No, gracias" (`end_conversation`). El frontend envía la `action` tal cual. |
| `transaction_list` | `period {from, to}`, `filters`, `count`, `totals[]` (`currency`, `count`, `total`), `transactions[]`, `can_dispute` | Consulta de movimientos (solo lectura). Totales y conteos calculados por el código. |
| `card_list` | `cards[]` (`product_id`, `label` "crédito ···1234", `product_type`, `status`) | Bloqueo: el cliente tiene varias tarjetas. |
| `case_list` | `cases[]` (`case_id`, `status`, `reason_code`, `created_at`, `transaction {label, amount, currency, date}`) | Estado de reclamos. |
| `transaction_card` | `transaction` (mismos campos que una candidata), `source` (`get_transaction`) | Confirmar un movimiento. |
| `action_confirmation` | `action` (`create_dispute_case` \| `lock_card` \| `create_handoff`), `summary`, `params`, `confirmation_token`, `expires_at`, `disclaimer` | Antes de toda acción con efecto. `create_handoff` = reposición de tarjeta tras un bloqueo. |
| `result` | `action`, `status` (`success` \| `partial` \| `failed`), `verified` (bool), `reference_id`, `details`; con varios reclamos, `items[]` (`transaction_id`, `reference_id`, `status`, `verified`, `label`) y `reference_id: null` | Después de actuar y verificar. Con varios cargos, un solo `result` que los resume; `verified` es true solo si todos se verificaron. |
| `handoff_notice` | `handoff_id`, `reason_code`, `message`, `next_step` | Escalamiento a persona. |
| `notice` | `level` (`info` \| `warning`), `code` (p. ej. `pending_transaction`, `existing_case`, `out_of_scope`, `no_refund_approval`), `text` | Información de política o alcance. Con `out_of_scope`, `text` es el texto aprobado de `faq.yaml` (`fuera_de_alcance`). |
| `link` | `label`, `url` | Enlace externo (hoy: la página inicial del banco, ficticia, `BANK_HOME_URL`, tras un `out_of_scope`). El frontend lo muestra como botón o enlace que abre en otra pestaña (`rel="noopener noreferrer"`). |
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
| 409 | `conversation_closed` | Turno en una conversación cerrada (despedida o inactividad). `details: {reason, conversation_id}`. El frontend no lo muestra: abre una conversación enlazada. |
| 409 | `invalid_state` | Acción no válida en el estado actual. |
| 422 | `message_too_long` | El mensaje supera 2.000 caracteres. `details: {max_chars, chars}`; el frontend muestra un aviso amable. |
| 429 | `rate_limited` | Demasiados intentos de login (usuario o IP) o demasiadas peticiones por IP o sesión ([security.md](security.md)). Cabecera `Retry-After` (segundos) y `details: {rule, retry_after_seconds}`. |
| 503 | `dependency_unavailable` | Falló el LLM o un tool tras reintentos; la respuesta incluye un fallback seguro. |

Errores dentro de la conversación (por ejemplo, fallo de un tool) se devuelven como `200` con un bloque `error` y, si aplica, `handoff_notice`.
