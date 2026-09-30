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
| `clarify` | haiku | Idioma, vuelta N/3, atributo discriminante (`fecha`, `monto`, `comercio`, `tipo_problema`) y, por candidata del **propio** cliente: `ref`, comercio, monto, moneda, fecha y estado traducido (`procesado`, `pendiente`, `rechazado`, `revertido`). | IDs, canal, producto, ciudad, riesgo. |
| `confirm` | haiku | Idioma, acción (`confirmar_movimiento`, `confirmar_reclamo`, `confirmar_bloqueo`), `reason_code` y la lista de marcadores disponibles. | **Ningún dato del movimiento**: redacta con `{comercio}`, `{monto}`, `{fecha}`, `{tarjeta}` y el código los rellena después. Un marcador inventado se rechaza. |
| `explain` | sonnet | Idioma, resultado, reglas activadas (id, resultado, motivo), hechos verificados imprescindibles (comercio, monto, moneda, fecha, estado) y marcadores (`{numero_reclamo}`). | IDs, número de reclamo real, datos de otros movimientos. |
| `handoff_summary` | sonnet | Idioma del cliente, motivo de escalamiento, hechos verificados imprescindibles, reglas evaluadas, acciones tomadas y las afirmaciones del cliente delimitadas. | IDs y nombre del cliente. Esos los agrega el código al objeto de handoff, fuera del LLM. |

## Contexto que agrega el CLI

`claude -p` corre en una carpeta temporal vacía, con `--tools ""`, `--disallowedTools "mcp__*"`, `--strict-mcp-config` y `--setting-sources ""`. Así no entran el `CLAUDE.md` del repo, servidores MCP, memorias ni ajustes del usuario.

- **Medido:** 514 tokens de entrada con un system prompt de una línea, frente a 1.171 sin `--strict-mcp-config --setting-sources ""`.
- **Lo que no se puede quitar sin `--bare`:** el CLI agrega un recordatorio de entorno con sistema operativo, fecha y **el email de la cuenta de Claude**. No es un dato del dataset, pero sale en cada llamada. `--bare` no se usa porque exige API key y no usa la suscripción.
- **Despliegue:** un cliente de la API de Claude (misma interfaz `LLMClient`) no tendría ese contexto.

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
