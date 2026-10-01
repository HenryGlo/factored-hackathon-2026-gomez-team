# Capa LLM: qué datos salen al modelo

Estado: **[Decisión]** implementado en [backend/app/llm/](../backend/app/llm/) (fase 2 del [prompt 03](prompts/03-backend-harness.md)). **[Supuesto]** P-05 sigue abierta: este comportamiento es la minimización que aplicamos mientras los organizadores no confirmen qué datos del dataset sintético se pueden enviar a un modelo externo.

## Principio

El LLM interpreta y redacta; nunca identifica al cliente ni ve IDs. Cada nodo recibe lo mínimo para su tarea:

- **Nunca salen:** `customer_id`, `display_name` ni ningún nombre del cliente, `product_number`, IDs internos (transacción, producto, reclamo, handoff, sesión, conversación), `is_fraud`, `fraud_score` crudo, coordenadas ni datos de contacto.
- **Candidatas:** van con referencias opacas (`c1`, `c2`…). El código guarda el mapa `ref → transaction_id` y nunca se lo pasa al modelo.
- **Números de reclamo o de atención:** van como marcadores (`{numero_reclamo}`) que el código rellena.
- **Texto del cliente:** va delimitado (`<mensaje_cliente>…</mensaje_cliente>`) y el prompt lo declara como dato, no como instrucción. Si el texto intenta cerrar la etiqueta, se neutraliza.
- **Salidas:** se validan con Pydantic. El texto que llega al cliente pasa una guarda R5: si promete o aprueba devoluciones ("reembolsado", "aprobado", "devolveremos"…), se rechaza.

## Campos por nodo

| Nodo | Modelo por defecto | Qué recibe | Qué NO recibe |
|---|---|---|---|
| `intent` | haiku | Solo el texto del cliente, delimitado. | Nada más: ni historial, ni datos de la cuenta. |
| `extract` | haiku | Solo el texto del cliente, delimitado. | Fecha de la sesión (el LLM no calcula fechas: [dates.py](../backend/app/dates.py) resuelve `date_hint`). |
| `clarify` | haiku | Solo cuando lo redacta el LLM ([modos](conversation-flow.md#modos-de-confirm-y-clarify)). Idioma, vuelta N/3, atributo discriminante (`fecha`, `monto`, `comercio`, `tipo_problema`, `mas_datos`, `reformular`), `dias_buscados` si aplica y, por candidata del **propio** cliente: `ref`, comercio, monto, moneda, fecha y estado traducido (`procesado`, `pendiente`, `rechazado`, `revertido`). | IDs, canal, producto, ciudad, riesgo. |
| `confirm` | haiku | Solo con `CONFIRM_MODE=llm` (el sistema usa plantilla). Idioma, acción (`confirmar_movimiento`, `confirmar_reclamo`, `confirmar_bloqueo`), `reason_code` y la lista de marcadores disponibles. | **Ningún dato del movimiento**: redacta con `{comercio}`, `{monto}`, `{fecha}`, `{tarjeta}` y el código los rellena después. Un marcador inventado se rechaza. |
| `faq_answer` | haiku | Idioma, tema, la respuesta aprobada del tema y los hechos del caso en foco **solo como marcadores** (`{numero_reclamo}`, `{comercio}`, `{monto}`, `{fecha}`, `{estado}`, `{tarjeta}`). | El texto del cliente, IDs y cualquier valor real: el código rellena los marcadores después de la guarda R5. |
| `explain` | sonnet | Idioma, resultado, reglas activadas (id, resultado, motivo), hechos verificados imprescindibles (comercio, monto, moneda, fecha, estado) y marcadores (`{numero_reclamo}`). | IDs, número de reclamo real, datos de otros movimientos. |
| `handoff_summary` | sonnet | Idioma del cliente, motivo de escalamiento, hechos verificados imprescindibles, reglas evaluadas, acciones tomadas y las afirmaciones del cliente delimitadas. | IDs y nombre del cliente. Esos los agrega el código al objeto de handoff, fuera del LLM. |

## Contexto que agrega el CLI

`claude -p` corre en una carpeta temporal vacía, con `--tools ""`, `--disallowedTools "mcp__*"`, `--strict-mcp-config` y `--setting-sources ""`. Así no entran el `CLAUDE.md` del repo, servidores MCP, memorias ni ajustes del usuario.

- **Medido:** 514 tokens de entrada con un system prompt de una línea, frente a 1.171 sin `--strict-mcp-config --setting-sources ""`.
- **Lo que no se puede quitar sin `--bare`:** el CLI agrega un recordatorio de entorno con sistema operativo, fecha y **el email de la cuenta de Claude**. No es un dato del dataset, pero sale en cada llamada. `--bare` no se usa porque exige API key y no usa la suscripción.
- **Despliegue:** el cliente de la API de Claude (abajo) no agrega ese contexto: solo viajan el system prompt del nodo, el esquema y la entrada minimizada.

## Proveedor de producción: API de Claude (prompt 05, fase 1)

**[Decisión]** [backend/app/llm/anthropic_api.py](../backend/app/llm/anthropic_api.py), con `LLM_PROVIDER=anthropic_api`. Usa el SDK oficial `anthropic` 1.11.0 (asíncrono) y la misma interfaz `LLMClient`.

- **IDs fijos por nodo** en [backend/config/llm.toml](../backend/config/llm.toml): `claude-haiku-4-5-20251001` y `claude-sonnet-5-5`. Son los IDs reales medidos en las trazas de `claude -p`. Con la API no se usan alias; un override `MODEL_<NODO>=haiku|sonnet` se traduce con la tabla `[model_ids]`.
- **Salida estructurada:** `output_config.format` con `json_schema`, según la [documentación](https://platform.claude.com/docs/en/build-with-claude/structured-outputs) consultada el 2026-09-30.
  - El esquema sale del modelo Pydantic del nodo con `anthropic.transform_schema`. Los límites que la API no aplica (`minLength`, `maxLength`, `maximum`…) quedan como texto en la descripción, y Pydantic los valida después.
  - Los enums se comparan sin distinguir mayúsculas.
  - `stop_reason` `refusal` o `max_tokens` cuenta como salida inválida.
- **Prompt caching:** el system prompt de cada nodo va con `cache_control: ephemeral`.
  - **Medido:** los prompts de los nodos con Haiku tienen unos 1.400–1.650 tokens de entrada, por debajo del mínimo cacheable de Haiku 4.5 (4.096). La API no los cachea (`cache_*_input_tokens = 0`) y no da error.
  - En Sonnet 5.5 el mínimo es 512.
  - La traza guarda `usage` (incluidos los tokens de caché) y el `request_id` de cada llamada.
- **Reintentos y errores:**
  - `LLM_TIMEOUT_SECONDS` es el timeout por intento. `LLM_RETRIES` es el `max_retries` del SDK: 429, 529, 5xx y red, con backoff y `retry-after`.
  - Agotados los intentos: `LLMTimeout` o `LLMUnavailable`. Los errores de cuenta (401, 403, 400) no se reintentan.
  - Una salida que no cumple el esquema se reintenta una vez y después es `LLMInvalidOutput`.
  - En todos los casos el controlador usa el fallback de plantillas y reglas.
- **Costo:** por llamada, desde `usage` y [backend/config/llm_pricing.toml](../backend/config/llm_pricing.toml).
  - Fuente: [precios de la API](https://platform.claude.com/docs/en/about-claude/pricing), consultada el 2026-09-30.
  - Haiku 4.5: $1 de entrada, $1.25 de escritura en caché (5 min), $0.10 de lectura de caché y $5 de salida por MTok.
  - Sonnet 5.5: $2, $2.50, $0.20 y $10 por MTok.
- **Estado del movimiento (P-31):**
  - Los nodos no reciben la palabra del estado, sino un marcador: `{estado}` en explain y handoff_summary, `{estado_c1}`… en clarify.
  - El código lo reemplaza **después** de la guarda R5, con la etiqueta del bloque ("Aprobado", "Pendiente"…).
  - Así el texto coincide con el bloque y la guarda no se afloja.
- **Clave:** `ANTHROPIC_API_KEY`, solo por entorno (o `.env`, fuera de git). Nunca en configuración versionada ni en trazas.

## Medición: punto de control 2 (2026-09-30, Claude Code 2.1.286)

Un ejemplo por nodo con `LLM_PROVIDER=claude_cli`, en serie. Script: [scripts/llm_smoke.py](../scripts/llm_smoke.py). Las candidatas de ejemplo son ilustrativas, no filas del dataset.

| Nodo | Caso | Modelo pedido → real | Latencia | Costo | Intentos |
|---|---|---|---|---|---|
| intent | es | haiku → `claude-haiku-4-5-20251001` | 9577 ms | $0.0060 | 1 |
| intent | pt | haiku → `claude-haiku-4-5-20251001` | 5276 ms | $0.0045 | 1 |
| intent | es (inyección) | haiku → `claude-haiku-4-5-20251001` | 6984 ms | $0.0048 | 1 |
| extract | es | haiku → `claude-haiku-4-5-20251001` | 5591 ms | $0.0041 | 1 |
| extract | pt | haiku → `claude-haiku-4-5-20251001` | 6034 ms | $0.0045 | 1 |
| clarify | pt | haiku → `claude-haiku-4-5-20251001` | 11578 ms | $0.0068 | 1 |
| confirm | es | haiku → `claude-haiku-4-5-20251001` | 7367 ms | $0.0046 | 1 |
| explain | es | sonnet → `claude-sonnet-5-5` | 3503 ms | $0.0076 | 1 |
| handoff_summary | pt | sonnet → `claude-sonnet-5-5` | 5162 ms | $0.0108 | 1 |

- **Latencia:** es de reloj de pared e incluye el arranque del proceso `claude` (~3 s); la mediana fue 6,0 s por llamada.
- **Costo:** es el `total_cost_usd` que informa el CLI (precio de lista), con un total de $0,054.
- **Implicación:** un turno con intent + extract en serie costaría ~11–15 s solo en LLM. En la fase 4 conviene correrlos en paralelo, y la ablación dirá si el clasificador entrenado evita llamar a `intent`.
