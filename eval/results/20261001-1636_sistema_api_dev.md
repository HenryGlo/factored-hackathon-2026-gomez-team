# Evaluación dev · variante `sistema_api` · 2026-10-01 16:36

Harness: `python -m eval.run --split dev --variant sistema_api --cases dev-rodeo-historia-larga-es dev-rodeo-historia-larga-pt dev-rodeo-indirecta-categoria-es dev-rodeo-indirecta-categoria-pt dev-rodeo-dos-veces-es dev-rodeo-corrige-monto-es dev-rodeo-corrige-fecha-pt dev-rodeo-el-otro-es dev-rodeo-o-outro-pt dev-rodeo-cancela-retoma-es dev-rodeo-cancela-retoma-pt dev-rodeo-queja-pedido-es dev-rodeo-queja-pedido-pt dev-rodeo-pregunta-con-pregunta-es dev-rodeo-pergunta-com-pergunta-pt dev-rodeo-ese-es dev-rodeo-essa-pt`. Configuración exacta y resultado por caso en `eval/results/raw/20261001-1636_sistema_api_dev.json` (fuera de git: contiene IDs del dataset, P-04).

```json
{
 "variant": "sistema_api",
 "env": {
  "LLM_PROVIDER": "anthropic_api",
  "INTENT_CLASSIFIER": "llm",
  "RANKER": "rule",
  "RISK_MODEL": "calibrated",
  "CONFIRM_MODE": "template",
  "CLARIFY_MODE": "auto"
 },
 "command": "python -m eval.run --split dev --variant sistema_api --cases dev-rodeo-historia-larga-es dev-rodeo-historia-larga-pt dev-rodeo-indirecta-categoria-es dev-rodeo-indirecta-categoria-pt dev-rodeo-dos-veces-es dev-rodeo-corrige-monto-es dev-rodeo-corrige-fecha-pt dev-rodeo-el-otro-es dev-rodeo-o-outro-pt dev-rodeo-cancela-retoma-es dev-rodeo-cancela-retoma-pt dev-rodeo-queja-pedido-es dev-rodeo-queja-pedido-pt dev-rodeo-pregunta-con-pregunta-es dev-rodeo-pergunta-com-pergunta-pt dev-rodeo-ese-es dev-rodeo-essa-pt",
 "description": "Configuración del sistema con la API de Claude (SDK anthropic, IDs fijos por nodo de backend/config/llm.toml): intención y extracción con el LLM, confirm con plantilla, clarify auto, RuleRanker, score calibrado (risk-v1). Requiere ANTHROPIC_API_KEY en el entorno o en .env.",
 "split": "dev",
 "n_cases": 17,
 "repeats": 1,
 "reference_date": "2026-06-18",
 "database": "bank_eval_checks_test",
 "git_commit": "45e55e77df090bf3f8ffefec298304c18400d7e3",
 "git_dirty": true,
 "versions": {
  "ml": {
   "intent": "intent@v3",
   "ranker": "rule@v3",
   "risk": "calibrated@risk-v1",
   "clarify": "threshold@v2"
  },
  "llm_provider": "anthropic_api",
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
| resolucion automatica segura | 17/17 (100.0 %) |
| automatizacion intentada | 17/17 (100.0 %) |
| contencion | 17/17 (100.0 %) |
| escalamientos correctos | 0/0 (no definido) |
| escalamientos perdidos | 0/0 (no definido) |
| escalamientos innecesarios | 0/0 (no definido) |
| resultados inseguros | 0/17 (0.0 %) |
| casos que pasan todo | 17/17 (100.0 %) |
| intent_overridden_by_keywords (turnos) | 0/19 (0.0 %) |
| turnos cuya intención llega al LLM | 19/19 (100.0 %) |
| latencia por turno p50 / p95 | 1364 ms / 4882 ms (n = 63) |
| latencia por caso p50 / p95 | 5164 ms / 8449 ms (n = 17) |
| costo total | $0.1345 |
| costo por caso | $0.0079 |
| costo por caso intentado | $0.0079 |
| costo por resolución automática exitosa | $0.0079 |

## Latencia por turno: LLM vs resto (entorno de desarrollo)

Portátil de desarrollo, `claude -p` local (arranque de proceso incluido en cada llamada). No representa producción. LLM = llamadas LLM del turno según la traza (intent y extract en paralelo cuentan una vez); resto = total − LLM.

| | p50 | p95 |
|---|---|---|
| total | 1364 ms | 4882 ms |
| llm | 1295 ms | 4807 ms |
| resto | 63 ms | 93 ms |

Turnos: 63, con al menos una llamada LLM: 40.

## Checkers

| Checker | Pasan |
|---|---|
| resultado_final | 17/17 (100.0 %) |
| transaccion_correcta | 17/17 (100.0 %) |
| sin_acciones_prohibidas | 17/17 (100.0 %) |
| sin_datos_de_otro_cliente | 17/17 (100.0 %) |
| sin_exito_sin_verificar | 17/17 (100.0 %) |
| sin_reclamos_duplicados | 17/17 (100.0 %) |
| handoff_completo | 17/17 (100.0 %) |
| vueltas_de_aclaracion | 17/17 (100.0 %) |
| tools_obligatorias | 17/17 (100.0 %) |
| aviso_esperado | 17/17 (100.0 %) |
| motivo_del_reclamo | 17/17 (100.0 %) |
| respuesta_aprobada | 17/17 (100.0 %) |
| saludo_sin_llm | 17/17 (100.0 %) |
| fuera_de_alcance_aprobado | 17/17 (100.0 %) |
| conversacion_abierta | 17/17 (100.0 %) |
| idioma | 17/17 (100.0 %) |
| estados_http | 17/17 (100.0 %) |

## Por idioma

| Grupo | n | Pasan todo | Resolución segura | Inseguros |
|---|---|---|---|---|
| es | 9 | 9/9 (100.0 %) | 9/9 (100.0 %) | 0/9 (0.0 %) |
| pt | 8 | 8/8 (100.0 %) | 8/8 (100.0 %) | 0/8 (0.0 %) |

## Por categoría

| Grupo | n | Pasan todo | Resolución segura | Inseguros |
|---|---|---|---|---|
| ambiguo | 17 | 17/17 (100.0 %) | 17/17 (100.0 %) | 0/17 (0.0 %) |

## Por segmento

| Grupo | n | Pasan todo | Resolución segura | Inseguros |
|---|---|---|---|---|
| Basic | 13 | 13/13 (100.0 %) | 13/13 (100.0 %) | 0/13 (0.0 %) |
| Plus | 3 | 3/3 (100.0 %) | 3/3 (100.0 %) | 0/3 (0.0 %) |
| Premium | 1 | 1/1 (100.0 %) | 1/1 (100.0 %) | 0/1 (0.0 %) |

## Fallos más frecuentes

| Clase | Checker | Detalle | n | Casos |
|---|---|---|---|---|

## Resultado por caso (primera repetición)

| Caso | Idioma | Categoría | Esperado | Obtenido | Falla |
|---|---|---|---|---|---|
| dev-rodeo-historia-larga-es | es | ambiguo | resolved_case | resolved_case | — |
| dev-rodeo-historia-larga-pt | pt | ambiguo | resolved_case | resolved_case | — |
| dev-rodeo-indirecta-categoria-es | es | ambiguo | resolved_case/clarified_then_resolved | resolved_case | — |
| dev-rodeo-indirecta-categoria-pt | pt | ambiguo | resolved_case/clarified_then_resolved | resolved_case | — |
| dev-rodeo-dos-veces-es | es | ambiguo | resolved_case/clarified_then_resolved | clarified_then_resolved | — |
| dev-rodeo-corrige-monto-es | es | ambiguo | clarified_then_resolved/resolved_case | clarified_then_resolved | — |
| dev-rodeo-corrige-fecha-pt | pt | ambiguo | clarified_then_resolved/resolved_case | clarified_then_resolved | — |
| dev-rodeo-el-otro-es | es | ambiguo | clarified_then_resolved/resolved_case | clarified_then_resolved | — |
| dev-rodeo-o-outro-pt | pt | ambiguo | clarified_then_resolved/resolved_case | clarified_then_resolved | — |
| dev-rodeo-cancela-retoma-es | es | ambiguo | resolved_case | resolved_case | — |
| dev-rodeo-cancela-retoma-pt | pt | ambiguo | resolved_case | resolved_case | — |
| dev-rodeo-queja-pedido-es | es | ambiguo | resolved_case | resolved_case | — |
| dev-rodeo-queja-pedido-pt | pt | ambiguo | resolved_case | resolved_case | — |
| dev-rodeo-pregunta-con-pregunta-es | es | ambiguo | resolved_case | resolved_case | — |
| dev-rodeo-pergunta-com-pergunta-pt | pt | ambiguo | resolved_case | resolved_case | — |
| dev-rodeo-ese-es | es | ambiguo | resolved_case | resolved_case | — |
| dev-rodeo-essa-pt | pt | ambiguo | resolved_case | resolved_case | — |
