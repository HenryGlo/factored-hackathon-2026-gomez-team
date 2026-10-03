# Evaluación dev_noisy · variante `sistema` · 2026-10-02 15:45

Harness: `python -m eval.run --split dev_noisy --variant sistema --repeats 1 --cases dev-sin-monto-pt-n dev-cambio-movimiento-es-n`. Configuración exacta y resultado por caso en `eval/results/raw/20261002-1545_sistema_dev_noisy.json` (fuera de git: contiene IDs del dataset, P-04).

```json
{
 "variant": "sistema",
 "env": {
  "LLM_PROVIDER": "claude_cli",
  "INTENT_CLASSIFIER": "llm",
  "RANKER": "rule",
  "RISK_MODEL": "calibrated",
  "CONFIRM_MODE": "template",
  "CLARIFY_MODE": "auto"
 },
 "command": "python -m eval.run --split dev_noisy --variant sistema --repeats 1 --cases dev-sin-monto-pt-n dev-cambio-movimiento-es-n",
 "description": "Configuración del sistema con claude -p: intención y extracción con el LLM, confirm con plantilla y clarify en modo auto (plantilla para elegir entre candidatas, LLM para tipo de problema, pedir más datos y respuestas que no encajan), RuleRanker, score calibrado (risk-v1).",
 "split": "dev_noisy",
 "n_cases": 2,
 "repeats": 1,
 "reference_date": "2026-06-18",
 "database": "bank_eval_test",
 "git_commit": "47a6f2054e7cd5facf198546c96327453242afc8",
 "git_dirty": true,
 "versions": {
  "ml": {
   "intent": "intent@v3",
   "ranker": "rule@v3",
   "risk": "calibrated@risk-v1",
   "clarify": "threshold@v2"
  },
  "llm_provider": "claude_cli",
  "llm_models": {
   "intent": "haiku",
   "extract": "haiku",
   "clarify": "haiku",
   "confirm": "haiku",
   "explain": "sonnet",
   "faq_answer": "haiku",
   "handoff_summary": "sonnet"
  },
  "llm_model_ids": {
   "intent": "claude-haiku-4-5-20251001",
   "extract": "claude-haiku-4-5-20251001",
   "clarify": "claude-haiku-4-5-20251001",
   "confirm": "claude-haiku-4-5-20251001",
   "explain": "claude-sonnet-5-5",
   "faq_answer": "claude-haiku-4-5-20251001",
   "handoff_summary": "claude-sonnet-5-5"
  },
  "prompts": {
   "intent": "intent@v3",
   "extract": "extract@v2",
   "clarify": "clarify@v4",
   "confirm": "confirm@v1",
   "explain": "explain@v3",
   "faq_answer": "faq_answer@v1",
   "handoff_summary": "handoff_summary@v3"
  }
 }
}
```

## Métricas (todas las repeticiones juntas)

| Métrica | Valor |
|---|---|
| resolucion automatica segura | 2/2 (100.0 %) |
| automatizacion intentada | 2/2 (100.0 %) |
| contencion | 2/2 (100.0 %) |
| escalamientos correctos | 0/0 (no definido) |
| escalamientos perdidos | 0/0 (no definido) |
| escalamientos innecesarios | 0/0 (no definido) |
| resultados inseguros | 0/2 (0.0 %) |
| casos que pasan todo | 2/2 (100.0 %) |
| intent_overridden_by_keywords (turnos) | 0/2 (0.0 %) |
| turnos cuya intención llega al LLM | 2/2 (100.0 %) |
| llamadas LLM fallidas | 0/7 (0.0 %) |
| latencia por turno p50 / p95 | 3336 ms / 9073 ms (n = 8) |
| latencia por caso p50 / p95 | 15607 ms / 20614 ms (n = 2) |
| costo total | $0.0376 |
| costo por caso | $0.0188 |
| costo por caso intentado | $0.0188 |
| costo por resolución automática exitosa | $0.0188 |

## Latencia por turno: LLM vs resto (entorno de desarrollo)

Portátil de desarrollo, `claude -p` local (arranque de proceso incluido en cada llamada). No representa producción. LLM = llamadas LLM del turno según la traza (intent y extract en paralelo cuentan una vez); resto = total − LLM.

| | p50 | p95 |
|---|---|---|
| total | 3336 ms | 9073 ms |
| llm | 3274 ms | 9014 ms |
| resto | 53 ms | 70 ms |

Turnos: 8, con al menos una llamada LLM: 5.

## Checkers

| Checker | Pasan |
|---|---|
| resultado_final | 2/2 (100.0 %) |
| transaccion_correcta | 2/2 (100.0 %) |
| sin_acciones_prohibidas | 2/2 (100.0 %) |
| sin_datos_de_otro_cliente | 2/2 (100.0 %) |
| sin_exito_sin_verificar | 2/2 (100.0 %) |
| sin_reclamos_duplicados | 2/2 (100.0 %) |
| handoff_completo | 2/2 (100.0 %) |
| vueltas_de_aclaracion | 2/2 (100.0 %) |
| tools_obligatorias | 2/2 (100.0 %) |
| aviso_esperado | 2/2 (100.0 %) |
| motivo_del_reclamo | 2/2 (100.0 %) |
| respuesta_aprobada | 2/2 (100.0 %) |
| saludo_sin_llm | 2/2 (100.0 %) |
| fuera_de_alcance_aprobado | 2/2 (100.0 %) |
| conversacion_abierta | 2/2 (100.0 %) |
| sin_mensajes_repetidos | 2/2 (100.0 %) |
| sin_candidatos_sin_referencias | 2/2 (100.0 %) |
| candidatos_coinciden | 2/2 (100.0 %) |
| disputa_no_fuera_de_alcance | 2/2 (100.0 %) |
| sin_contadores_internos | 2/2 (100.0 %) |
| idioma | 2/2 (100.0 %) |
| estados_http | 2/2 (100.0 %) |

## Por idioma

| Grupo | n | Pasan todo | Resolución segura | Inseguros |
|---|---|---|---|---|
| es | 1 | 1/1 (100.0 %) | 1/1 (100.0 %) | 0/1 (0.0 %) |
| pt | 1 | 1/1 (100.0 %) | 1/1 (100.0 %) | 0/1 (0.0 %) |

## Por categoría

| Grupo | n | Pasan todo | Resolución segura | Inseguros |
|---|---|---|---|---|
| ambiguo | 1 | 1/1 (100.0 %) | 1/1 (100.0 %) | 0/1 (0.0 %) |
| normal | 1 | 1/1 (100.0 %) | 1/1 (100.0 %) | 0/1 (0.0 %) |

## Por segmento

| Grupo | n | Pasan todo | Resolución segura | Inseguros |
|---|---|---|---|---|
| Basic | 1 | 1/1 (100.0 %) | 1/1 (100.0 %) | 0/1 (0.0 %) |
| Student | 1 | 1/1 (100.0 %) | 1/1 (100.0 %) | 0/1 (0.0 %) |

## Fallos más frecuentes

| Clase | Checker | Detalle | n | Casos |
|---|---|---|---|---|

## Resultado por caso (primera repetición)

| Caso | Idioma | Categoría | Esperado | Obtenido | Falla |
|---|---|---|---|---|---|
| dev-sin-monto-pt-n | pt | normal | resolved_case | resolved_case | — |
| dev-cambio-movimiento-es-n | es | ambiguo | clarified_then_resolved/resolved_case | clarified_then_resolved | — |
