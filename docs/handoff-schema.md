# Esquema de handoff

> Campos: **[Propuesta]**. El principio de separar afirmaciones del cliente de hechos verificados es **[Decisión]**.

## Qué pide el reto

**[Oficial]** Dar al agente humano la solicitud, los hechos verificados, las acciones tomadas, la evidencia de soporte y las preguntas sin resolver. Transferir hechos verificados y preguntas abiertas **sin volcar la transcripción cruda**. Medir escalamientos perdidos e innecesarios.

## Principio

Todo lo que dice el cliente es una **afirmación**. Solo es **hecho verificado** lo que devolvió un tool, con referencia a la llamada que lo produjo. El LLM (Sonnet 5) redacta únicamente `summary`; el resto lo arma el controlador con datos estructurados.

## Campos

| Campo | Tipo | Obligatorio | Fuente | Descripción |
|---|---|---|---|---|
| `handoff_id` | string | sí | código | Identificador. |
| `created_at` | timestamp | sí | código | |
| `conversation_id` | string | sí | código | |
| `trace_turn_ids` | string[] | sí | código | Turnos para ver la traza completa. |
| `customer_ref` | object | sí | sesión | `customer_id`, `display_name`, `country`, `segment`. Sin documento ni datos de contacto. |
| `language` | `es` \| `pt` | sí | N1 | Idioma de la conversación. |
| `reason_code` | enum | sí | código | `fuera_de_plazo`, `riesgo_alto`, `aclaracion_agotada`, `pide_humano`, `fallo_tool`, `accion_no_verificada`, `acceso_no_autorizado`, `reposicion_tarjeta` (después de un `lock_card` verificado, si el cliente acepta), `cargo_pendiente_no_reconocido` (R2b: cola `fraude`, prioridad alta). |
| `queue` | enum | sí | código | `fraude` (riesgo alto o desconocido), `disputas` (plazo, aclaración agotada, acción no verificada), `tarjetas` (reposición), `general`. |
| `priority` | enum | sí | código | **[Supuesto]** `alta` si `riesgo_alto` o `acceso_no_autorizado`; `media` en otro caso (P-28). |
| `request` | string | sí | N1/N2 | La solicitud en una línea: "Disputa de un cargo no reconocido". |
| `customer_claims[]` | object[] | sí | LLM (extracción) | Afirmaciones del cliente: `{claim, turn_id}`. Ej.: "No reconoce un cobro de $120". |
| `verified_facts[]` | object[] | sí | tools | `{fact, value, source_tool, tool_call_id}`. Ej.: transacción, monto, moneda, fecha, estado, días desde el cargo, reclamo existente, banda de riesgo. |
| `candidate_transactions[]` | object[] | no | ranker | Si no se identificó la transacción: candidatas mostradas con score y rango. |
| `policy_evaluations[]` | object[] | sí | política | `{rule, result, evidence}`. |
| `actions_taken[]` | object[] | sí | tools | `{action, status, verified, reference_id}`. Vacío si no se hizo nada. |
| `open_questions[]` | string[] | sí | código + LLM | Lo que el humano debe resolver. Ej.: "¿Aplica excepción al plazo de 60 días?". |
| `summary` | string | sí | LLM (Sonnet 5) | Resumen de 3–5 líneas escrito a partir de los campos anteriores, sin agregar hechos. |
| `summary_model` | object | sí | código | `{model, prompt_version}`. |
| `status` | enum | sí | código | `pendiente`, `tomado`, `cerrado`. |

## Ejemplo

Valores ilustrativos, no filas reales del dataset.

```json
{
  "handoff_id": "hof_…",
  "conversation_id": "conv_…",
  "language": "pt",
  "reason_code": "fuera_de_plazo",
  "priority": "media",
  "request": "Disputa de un cargo no reconocido",
  "customer_claims": [
    {"claim": "No reconoce un cobro de 120", "turn_id": "turn_1"},
    {"claim": "Dice que fue hace unos dos meses y medio", "turn_id": "turn_1"}
  ],
  "verified_facts": [
    {"fact": "transacción confirmada por el cliente", "value": "TRX-…", "source_tool": "get_transaction", "tool_call_id": "tc_…"},
    {"fact": "monto", "value": "120.00 USD", "source_tool": "get_transaction", "tool_call_id": "tc_…"},
    {"fact": "días desde el cargo", "value": 75, "source_tool": "get_transaction", "tool_call_id": "tc_…"},
    {"fact": "reclamo existente", "value": null, "source_tool": "get_existing_case", "tool_call_id": "tc_…"}
  ],
  "policy_evaluations": [{"rule": "R1", "result": "escalar", "evidence": {"days_since": 75, "limit": 60}}],
  "actions_taken": [],
  "open_questions": ["¿Aplica una excepción al plazo de 60 días?"],
  "summary": "Cliente en portugués disputa un cargo de 120.00 USD de hace 75 días. …",
  "status": "pendiente"
}
```

## Qué no va en el handoff

- La transcripción completa (se accede por `trace_turn_ids` si hace falta).
- `is_fraud` del dataset (es la etiqueta, no un dato operativo).
- Documento de identidad, email, teléfono o dirección.
