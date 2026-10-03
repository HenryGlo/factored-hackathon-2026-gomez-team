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
| POST | `/api/conversations/{id}/feedback` | customer (dueño) | Valoración de la conversación ([detalle](#post-apiconversationsidfeedback)). |
| GET | `/api/feedback` | analyst | Valoraciones recibidas (consola y ciclo de mejora). |
| GET | `/api/conversations/{id}/phase` | customer (dueño) | Fase real del turno en curso, para el indicador de espera ([detalle](#get-apiconversationsidphase)). |
| GET | `/api/cases` | analyst | Lista de reclamos creados por el sistema. |
| GET | `/api/cases/{id}` | analyst | Detalle de un reclamo. |
| GET | `/api/handoffs` | analyst | Lista de handoffs. |
| GET | `/api/handoffs/{id}` | analyst | Detalle de un handoff. |
| GET | `/api/voice/config` | cualquiera con sesión | Si la voz está disponible y sus límites ([detalle](#apivoice)). |
| POST | `/api/voice/stt` | customer | Audio → transcripción (no envía nada al chat). |
| POST | `/api/voice/tts` | customer | Lee en voz alta un turno del asistente (audio en streaming). |
| GET | `/api/tickets` | analyst | Bandeja de tickets para agentes ([detalle](#apitickets)). |
| GET | `/api/tickets/{id}` | analyst | Detalle del ticket: handoff, estado, SLA e historial. |
| POST | `/api/tickets/{id}/assign` · `/status` · `/notes` | analyst | Asignar, cambiar de estado y agregar una nota interna. |
| GET | `/api/traces/{turn_id}` | analyst | Traza de ejecución de un turno. |
| GET | `/api/me/transactions` | customer | Mis movimientos: lectura directa, sin LLM ([detalle](#get-apimetransactions-y-apimecases)). |
| GET | `/api/me/cases` | customer | Mis reclamos. |
| GET | `/api/me/conversations` | customer | Mis conversaciones: lista paginada con resumen ([detalle](#get-apimeconversations)). |
| GET | `/api/me/conversations/{id}` | customer (dueño) | Una conversación propia en solo lectura. |
| GET | `/api/health` | público | Vida: el proceso responde. |
| GET | `/api/ready` | público | Preparación: base y configuración del LLM ([observability.md](observability.md)). `503` si algo falla. |
| GET | `/api/admin/overview` | admin | Panel: tiempos por endpoint y nodo, conversaciones recientes, resultados, costo y presupuesto ([detalle](#apiadmin-overview-slo-y-logs)). |
| GET | `/api/admin/slo` | admin | SLO con valor actual, presupuesto de error y violaciones. |
| GET | `/api/admin/logs` | admin | Logs recientes con filtros, sin textos sensibles. |
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
| `start_topic` | `topic`: `cargo_no_reconocido` \| `consulta_movimientos` \| `estado_reclamo` \| `bloquear_tarjeta` | Respuesta rápida de un tema (estado `inicio`): empieza ese flujo sin que el cliente escriba. Otro valor → 422. También en `aclarando`, después de un aviso `need_detail` o `no_match`: `consulta_movimientos` = "Ver mis últimos movimientos" (lista con `can_dispute`) y `cargo_no_reconocido` = **"Darte otro dato"** (vuelve a pedir el dato). |
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

- `via` (opcional en el cuerpo, `"text"` por defecto): `"voice"` cuando el mensaje es una transcripción revisada por el cliente. No cambia el flujo ni las guardas; queda en la traza.
- `trace_id` es igual a `turn_id` (`GET /api/traces/{turn_id}`).
- El aviso de frescura al cliente usa `data_as_of.max_transaction_date` ([postgres.md](data/postgres.md#política-de-frescura)).
- Un reintento con la misma `Idempotency-Key` y el mismo cuerpo devuelve la misma respuesta con `"replayed": true`.
- **Ciclo de vida (2026-10-01):** ningún resultado cierra la conversación (resolver, informar, escalar o abstenerse). Al terminar un flujo, el estado vuelve a `inicio` y la respuesta trae el texto "¿Hay algo más en lo que te pueda ayudar?" y un bloque `quick_replies`.
- **Cuándo se cierra (`cerrado`):** cuando el cliente se despide (texto o `end_conversation`) o tras `conversation_idle_minutes` (15) sin turnos. `escalado` ya no se usa; queda solo en conversaciones viejas.
- **Turno en una conversación cerrada:** `409 conversation_closed` con `details: {reason: "cliente" | "inactividad", conversation_id}`. El 409 es para la API; el frontend crea una conversación enlazada con `previous_conversation_id` y reenvía el mensaje.

### POST /api/conversations/{id}/feedback

**[Decisión]** 2026-10-01 (prompt 08, A2). "¿Te ayudé?" al terminar la conversación. Requiere sesión de cliente y `X-CSRF-Token`.

- Cuerpo: `{"rating": "up" | "down", "category": "no_me_entendio" | "respuesta_incorrecta" | "lento" | "otro" | null, "comment": string ≤ 500 | null}`.
- `201` → `{feedback_id, conversation_id, rating, category, created_at}`.
- **Una valoración por conversación.** Repetir responde `409 feedback_exists`: la primera queda como registro (la app solo puede
  insertar en `app.feedback`; no puede editar ni borrar). El frontend puede tratar ese 409 como "ya enviada".
- Conversación ajena o inexistente: `404`. Sin CSRF o con otro rol: `403`. Comentario de más de 500 caracteres o valores fuera
  de la lista: error de validación.
- Queda enlazada a la conversación y al último turno del asistente (`last_turn_id`, que lleva a sus trazas). El log registra el
  evento sin el comentario. El comentario es un dato del cliente: nunca se interpreta como instrucción.
- Límite: 10 por minuto por sesión (`feedback_session`).
- **`GET /api/feedback?rating=up|down&limit=50`** (analyst) → `[{feedback_id, conversation_id, last_turn_id, rating, category, comment, created_at}]`.

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

### /api/voice

**[Decisión]** 2026-10-01 (prompt 08, A3). Voz con ElevenLabs, con el backend como proxy: **el frontend nunca ve la clave**.
**Apagada por defecto** (`VOICE_ENABLED=false`); la clave y la voz van por entorno (`ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`).
Endpoints y modelos del proveedor verificados en su documentación el 2026-10-01
([STT](https://elevenlabs.io/docs/api-reference/speech-to-text/convert), modelo `scribe_v2`;
[TTS en streaming](https://elevenlabs.io/docs/api-reference/text-to-speech/stream), modelo `eleven_flash_v2_5` desde el 2026-10-03:
primer audio ≈ 0,26 s frente a ≈ 2,3 s de `eleven_multilingual_v2`). **Encendida** en prodlike y producción desde el 2026-10-03.

- **`GET /api/voice/config`** → `{enabled, reason, max_audio_bytes, max_tts_chars, audio_types, confirmations}`. `reason`:
  `voice_disabled` | `voice_not_configured` | `null`. Si `enabled` es `false`, el frontend no ofrece la voz (o explica el motivo).
- **`POST /api/voice/stt?language=es|pt`**: el cuerpo es el audio (`Content-Type: audio/webm`, `audio/ogg`, `audio/wav`,
  `audio/mpeg`, `audio/mp4`…), hasta 2 MB. Requiere `X-CSRF-Token`. → `{text, language_code, seconds, truncated, next}`.
  - **Solo transcribe.** El frontend muestra el texto, deja corregirlo y lo envía con `POST /api/conversations/{id}/turns`
    agregando `"via": "voice"`. Ese mensaje entra al **mismo flujo y las mismas guardas** que el texto escrito; `via` solo queda
    anotado en la traza. La voz no salta ninguna regla.
- **`POST /api/voice/tts`** `{"conversation_id", "turn_id"}` → `audio/mpeg` en streaming. Lee **ese turno del asistente**, hasta
  900 caracteres: los bloques `text` y `notice`, el `summary` de una confirmación (seguido de "Para confirmar, toca el botón
  Confirmar en la pantalla") y el `message` de un handoff, y **también las opciones**, para el modo manos libres: las candidatas
  ("La primera: Netflix, 15,99 USD, 3 jun 2026…" + "Dime cuál…"), hasta 5 movimientos de una lista y las respuestas rápidas
  ("Puedes decir: Ver mis últimos movimientos o Hablar con una persona"). No acepta
  texto libre: no sirve como sintetizador genérico. Turno ajeno o inexistente: `404`.
- **Elegir por voz (modo manos libres, decisión del líder 2026-10-03, opción A):** el texto dictado se envía como un turno normal
  y el backend entiende la elección **sin que el cliente toque nada**:
  - una respuesta rápida por su nombre ("ver mis movimientos", "una persona", "otro dato");
  - una candidata por posición, comercio o monto ("la segunda", "el de Netflix", "el de 120"); un movimiento de la lista que
    se acaba de mostrar, igual (abre el reclamo de ese cargo);
  - "los dos", "todos" y fechas ("el primero de junio") no cuentan como elegir una opción.
  En el frontend, el modo voz puede ser una pantalla sin selección manual (VAD + transcripción + respuesta hablada); **lo único
  que sigue necesitando un toque es el botón Confirmar**.
- **Confirmaciones:** abrir un reclamo o bloquear una tarjeta se confirma **siempre en pantalla, con el botón**. Decir "sí" por voz
  no ejecuta nada (R4), igual que escribirlo.
- **Errores (el chat sigue por texto; todos traen `details.fallback = "text"`):** `503 voice_disabled` / `voice_not_configured`;
  `429 voice_budget_exceeded` (presupuesto de voz por sesión o por día); `502 voice_unavailable` (el proveedor falló);
  `413 audio_too_large`; `415 unsupported_audio`; `429 rate_limited` (20 por minuto por sesión).
- **Presupuesto propio** (`backend/config/voice.toml`): 300 s de dictado y 6.000 caracteres leídos por sesión; 3.600 s y 100.000
  por día. El costo por día aparece en `/api/admin/overview` (`voice_cost_daily`), con precios supuestos por el equipo.
- **El audio no se guarda.** Se registra solo el consumo (segundos y caracteres). En la traza queda la transcripción que el
  cliente envió, como cualquier mensaje.
- El audio y el texto leído **salen a un tercero** (ElevenLabs): ver [llm-data.md](llm-data.md#voz-datos-que-salen-a-elevenlabs).

### /api/tickets

**[Decisión]** 2026-10-01 (prompt 08, A4). Los casos escalados (handoffs) son los tickets de los agentes de soporte. Rol: `analyst`
(es el rol del agente; el rol `admin` llega con A5). Prioridades, plazos y orden son **supuestos del equipo**
(`backend/config/tickets.toml`). Los `POST` requieren `X-CSRF-Token`.

- **`GET /api/tickets?status=&priority=&assignee=&sla=&open=&limit=`** → `{tickets: [...], total, by_status, sla_hours, assumption}`.
  - Filtros: `status` (`nuevo` | `en_curso` | `esperando_cliente` | `resuelto`), `priority` (`urgente` | `alta` | `media`),
    `assignee` (`me` | `unassigned` | nombre de usuario), `sla` (`a_tiempo` | `por_vencer` | `vencido` | `cumplido` | `incumplido`),
    `open=true` (sin los resueltos).
  - Orden: prioridad (urgente, alta, media) y, dentro de cada una, el más antiguo primero.
  - Cada ticket: `ticket_id` (el `handoff_id`), `reference_label` (`ATN-…`), `conversation_id`, `customer_id`, `language`,
    `reason_code`, `priority`, `queue`, `status`, `assignee` (`{user_id, username}` o `null`), `created_at`, `updated_at`,
    `first_response_at`, `resolved_at`, `age_minutes`, `summary` y `sla`: `{target_hours, due_at, state}`.
  - SLA objetivo: urgente 1 h, alta 4 h, media 24 h. `por_vencer` desde el 75 % del plazo; al resolver, `cumplido` o `incumplido`.
- **`GET /api/tickets/{id}`** → lo anterior más `handoff` (el objeto completo de [handoff-schema.md](handoff-schema.md): hechos
  verificados, lo que dijo el cliente, reglas evaluadas, preguntas abiertas, `trace_turn_ids`) y `events[]`
  (`{event_id, actor_username, kind, from_value, to_value, note, created_at}`).
- **`POST /api/tickets/{id}/assign`** `{"assignee": "me" | "<usuario agente>" | null}` → el ticket. Un usuario que no es agente activo: `400`.
- **`POST /api/tickets/{id}/status`** `{"status": …}` → el ticket. La primera salida de `nuevo` fija `first_response_at`; `resuelto`
  fija `resolved_at` (y volver a abrirlo lo borra).
- **`POST /api/tickets/{id}/notes`** `{"note": "…"}` (1–2.000 caracteres) → `201` con el ticket. Nota **interna**: solo la ven los
  agentes; nunca se muestra al cliente ni entra a un prompt.
- **Auditoría:** cada asignación, cambio de estado y nota escribe una fila en `app.ticket_events` (quién, cuándo, de qué a qué).
  La app solo puede insertar en esa tabla. `events[]` es ese registro.
- Errores: `403` cliente o sin CSRF; `404` ticket inexistente; validación para estados o campos fuera de la lista.

### GET /api/me/conversations

**[Decisión]** 2026-10-01 (prompt 08, A1). Historial del cliente, solo lectura y sin LLM.

- **`GET /api/me/conversations?limit=20&cursor=…&lang=es|pt`** → `{conversations: [...], next_cursor}`. De la más reciente a la más
  antigua. `limit` 1–50. `next_cursor` es opaco: se reenvía tal cual para la página siguiente; `null` en la última. Las
  conversaciones sin ningún mensaje del cliente no aparecen. Cada elemento:

  | Campo | Significado |
  |---|---|
  | `conversation_id`, `created_at`, `updated_at`, `closed_at` | Identificador y fechas (ISO 8601). |
  | `state`, `closed_reason` | Estado final (`inicio` = sigue abierta, `cerrado`) y motivo (`cliente`, `inactividad`). |
  | `language`, `intent` | Idioma y última intención registrada. |
  | `outcomes` | Lista con `reclamo`, `bloqueo`, `persona`, `informacion` o `sin_accion`. |
  | `references` | Referencias cortas para el cliente: `RCL-…` de los reclamos y `ATN-…` de los handoffs. |
  | `summary` | Resumen corto en el idioma pedido, **armado con hechos** de la base (reclamos, handoffs, bloqueos, intención) con plantillas: no es texto libre de un LLM. Ejemplo: "Reclamo RCL-3F9A1C por cargo no reconocido: Super Ahorro, 423,23 USD." |
  | `customer_turns`, `previous_conversation_id` | Mensajes del cliente y conversación de la que continúa. |

- **`GET /api/me/conversations/{id}?lang=…`** → los mismos campos más `turns[]` (`turn_id`, `seq`, `role`, `message`, `action`,
  `blocks`, `state_after`, `created_at`), con **los mismos bloques** que mostró el chat. Es de solo lectura: para seguir sobre
  ese tema, el frontend crea una conversación nueva con `previous_conversation_id`.
- **Solo las propias:** una conversación de otro cliente, inexistente o sin mensajes responde `404 not_found` (no se revela
  que existe). Rol distinto de `customer`: `403`.

### /api/admin: overview, SLO y logs

**[Decisión]** 2026-10-01 (prompt 08, A5). Rol **`admin`** (nuevo; usuario demo `admin_1`). El rol `analyst` es el agente de soporte:
ve la consola, los tickets y `/api/admin/metrics/*`, pero no estas tres rutas. El `admin` ve todo lo del `analyst`.

- **`GET /api/admin/overview?days=7`** →
  - `endpoints[]`: por método y ruta, `requests`, `errors_4xx`, `errors_5xx`, `rate_limited`, `latency_ms_p50`, `latency_ms_p95` (en memoria, desde que arrancó el proceso);
  - `nodes[]`: por nodo (LLM y tools), `calls`, `errors`, `p50_ms`, `p95_ms`, `cost_usd`;
  - `recent_conversations[]` (20): `conversation_id`, fechas, `state`, `language`, `intent`, `customer_turns`, `has_case`, `has_handoff`, `feedback` (`up` | `down` | null). Sin textos;
  - `outcomes`: lo mismo que `/api/admin/metrics/operations` (resolución automática, con aclaración, escalamiento, sin acción, con n/N);
  - `llm_cost_daily[]` (`day`, `calls`, `errors`, `cost_usd`) y `voice_cost_daily[]` (vacío hasta que la voz esté activa);
  - `budget`: `today_calls`, `today_cost_usd`, los límites diarios y la fracción consumida.
- **`GET /api/admin/slo`** → `{slos: [...], assumption}`. Objetivos en `backend/config/slo.toml` (supuestos del equipo). Cada SLO:
  `id`, `description`, `objective`, `target`, `current`, `met`, `error_budget` (`events`, `bad_events`, `allowed_bad_events`,
  `consumed`, `remaining_bad_events`) y `violations[]` con su hora (`at`) y el identificador (turno, ticket o ruta).
  - `turn_latency`: p95 del turno < 6 s, ventana de 7 días (95 % de los turnos).
  - `ticket_first_response`: primera respuesta de una persona en menos de 4 h (90 % de los tickets, 7 días).
  - `availability`: 99,5 % de respuestas sin 5xx, desde el arranque del proceso.
- **`GET /api/admin/logs?request_id=&conversation_id=&level=&route=&limit=100`** → `{events: [...], kept, note}`, del más nuevo al más
  viejo. Cada evento es la línea de log ya redactada (`ts`, `level`, `logger`, `event`, `request_id`, `conversation_id`, `turn_id`,
  `route`, `status`, `latency_ms`…). **Nunca** lleva contraseñas, tokens, cookies ni textos del cliente. Es un búfer en memoria
  del proceso (últimos 5.000 eventos): se pierde al reiniciar y no reemplaza a un agregador de logs. Guarda lo que deja pasar `LOG_LEVEL`
  (con `WARNING` no hay eventos `info`).

### GET /api/admin/metrics/*

**[Decisión]** 2026-10-01 (prompt 07, bloque 4). Para el panel de administración. Roles `analyst` y `admin`. Solo lectura, con el usuario de solo lectura de la base. Parámetro `days` (1–365).

- **`GET /api/admin/metrics/operations?days=30`** →
  `{days, conversations, resolved_automatically: {n, of, share}, resolved_after_clarification: {…}, escalated: {…}, no_action: {…}, handoffs: [{reason_code, priority, n}]}`.
  Una conversación cuenta como *escalada* si tiene un handoff (sin contar la reposición de tarjeta); *resuelta* si dejó un reclamo
  o un bloqueo, *con aclaración* si hubo un paso `clarify`; *sin acción* en otro caso (consultas, preguntas, abstenciones).
- **`GET /api/admin/metrics/latency?days=7`** → `{days, nodes: [{node, kind, calls, errors, p50_ms, p95_ms, cost_usd}]}` (nodos LLM y tools).
- **`GET /api/admin/metrics/roi?days=30`** → `{label, assumptions, estimate: {human_cost_per_case_usd, saving_per_case_usd, monthly_saving_usd, break_even_cases_per_month}, measured: {conversations, not_escalated_share, llm_cost_per_conversation_usd}}`.
  `label` dice que es una **estimación**; los supuestos salen de `backend/config/roi.toml`. El panel debe mostrar esa etiqueta.

### GET /api/demo/info

Público (sin sesión). Sirve para que el login muestre el aviso de entorno de demostración y las tarjetas de usuarios demo.

- Con `DEMO_MODE` apagado (valor por defecto): `{"demo_mode": false}` y nada más. El frontend no muestra aviso ni tarjetas.
- Con `DEMO_MODE=true`:

```json
{
  "demo_mode": true,
  "notice": {"es": "Entorno de demostración con datos ficticios. …", "pt": "Ambiente de demonstração com dados fictícios. …"},
  "password_hint": {"es": "La contraseña de los usuarios demo está en la documentación de entrega del equipo (no se muestra aquí).", "pt": "…"},
  "users": [
    {"username": "demo_cargo_claro_1", "role": "customer", "display_name": "Carmen R.", "scenario": "cargo_claro", "rank": 1,
     "description": {"es": "Cargo claro: un cargo reciente con comercio y monto únicos. Reclámalo de punta a punta.", "pt": "…"}},
    {"username": "analista_1", "role": "analyst", "display_name": "…", "scenario": null, "rank": null,
     "description": {"es": "Agente de soporte: bandeja de tickets y detalle de cada caso.", "pt": "…"}},
    {"username": "admin_1", "role": "admin", "display_name": "…", "scenario": null, "rank": null, "description": {"es": "…", "pt": "…"}}
  ]
}
```

- `users` trae solo usuarios demo activos: clientes (`scenario` ∈ `cargo_claro`, `cargos_parecidos`, `fraude_alto`, `fuera_de_plazo`, `pendiente`, `revertido`), luego agentes y admin. Orden: primero el `rank` 1 de cada escenario.
- **Nunca incluye la contraseña** ni `customer_id`. El frontend tampoco debe mostrarla: `password_hint` dice dónde está documentada.

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
| `quick_replies` | `options[]` (`label`, `action`) | Tras terminar un flujo: "Sí, otra consulta" (`new_request`) y "No, gracias" (`end_conversation`). El frontend envía la `action` tal cual. También aparece, con los temas (`start_topic`) y "Hablar con una persona" (`request_human`), cuando el cliente escribe dos veces seguidas sin un pedido (saludos, mensajes sin contenido, fuera de alcance repetido). |
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

### Estados "pide un dato" y "sin coincidencias" (issue #102)

Cuando el cliente quiere reclamar un cargo, el asistente **no muestra movimientos que no coincidan** con lo que dijo. Hay dos
respuestas que el frontend puede distinguir por el `code` del bloque `notice` (sin leer el texto). Las dos dejan la conversación
en `aclarando` y van seguidas de un bloque `quick_replies`.

| `notice.code` | Cuándo | Campos extra | `quick_replies` que lo acompañan |
|---|---|---|---|
| `need_detail` | El cliente no dio monto, comercio ni fecha. No se busca: se pide un dato. | — | "Ver mis últimos movimientos" (`start_topic` / `consulta_movimientos`), "Hablar con una persona" (`request_human`) |
| `no_match` | Se buscó con los criterios dados y ningún movimiento coincide. El texto lo dice con la fecha de los datos. | `criteria`: `{merchant, amount, date}` (lo que dio el cliente; `null` si no lo dio) y `data_as_of` (`YYYY-MM-DD`) | "Darte otro dato" (`start_topic` / `cargo_no_reconocido`), "Ver mis últimos movimientos", "Hablar con una persona" |

```json
{"type": "notice", "level": "info", "code": "no_match",
 "text": "No encontré cargos de Facebook en tus movimientos hasta el 18 jun 2026. Puede aparecer con otro nombre o no haberse registrado todavía.",
 "criteria": {"merchant": "Facebook", "amount": null, "date": null}, "data_as_of": "2026-06-18"}
```

- Con coincidencias, el `text` y el `prompt` de `candidate_list` dicen con qué coincidieron ("Encontré 2 cargos de Facebook", "…de cerca de 120,00 USD", "…del 16 jun 2026"). Nunca "parecidos".
- Tras "Ver mis últimos movimientos" el texto es "Estos son tus últimos movimientos. ¿Cuál no reconoces?" y la conversación vuelve a `inicio`, con la lista (`transaction_list`, `can_dispute: true`) y sin "¿algo más?".
- **`round` y `max_rounds` de `candidate_list` son internos:** no se muestran al cliente ("Intento 3 de 3"). Al agotarse los intentos, el asistente ofrece el traspaso (`handoff_notice`, motivo `aclaracion_agotada`); el handoff lleva qué datos dio el cliente y qué se buscó.

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
