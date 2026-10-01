# Evaluación dev · variante `sistema_api` · 2026-10-01 16:23

Harness: `python -m eval.run --split dev --variant sistema_api --cases dev-riesgo-medio-calibrado-es dev-riesgo-alto-no-lo-hice-es dev-riesgo-alto-nao-fui-eu-pt dev-riesgo-alto-es dev-riesgo-alto-pt`. Configuración exacta y resultado por caso en `eval/results/raw/20261001-1623_sistema_api_dev.json` (fuera de git: contiene IDs del dataset, P-04).

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
 "command": "python -m eval.run --split dev --variant sistema_api --cases dev-riesgo-medio-calibrado-es dev-riesgo-alto-no-lo-hice-es dev-riesgo-alto-nao-fui-eu-pt dev-riesgo-alto-es dev-riesgo-alto-pt",
 "description": "Configuración del sistema con la API de Claude (SDK anthropic, IDs fijos por nodo de backend/config/llm.toml): intención y extracción con el LLM, confirm con plantilla, clarify auto, RuleRanker, score calibrado (risk-v1). Requiere ANTHROPIC_API_KEY en el entorno o en .env.",
 "split": "dev",
 "n_cases": 5,
 "repeats": 1,
 "reference_date": "2026-06-18",
 "database": "bank_eval_checks_test",
 "git_commit": "0e1b08241c16872690d6c6eebf3b897f80e9a439",
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
| resolucion automatica segura | 0/0 (no definido) |
| automatizacion intentada | 5/5 (100.0 %) |
| contencion | 0/5 (0.0 %) |
| escalamientos correctos | 5/5 (100.0 %) |
| escalamientos perdidos | 0/5 (0.0 %) |
| escalamientos innecesarios | 0/5 (0.0 %) |
| resultados inseguros | 0/5 (0.0 %) |
| casos que pasan todo | 5/5 (100.0 %) |
| intent_overridden_by_keywords (turnos) | 0/5 (0.0 %) |
| turnos cuya intención llega al LLM | 5/5 (100.0 %) |
| latencia por turno p50 / p95 | 1781 ms / 4074 ms (n = 15) |
| latencia por caso p50 / p95 | 5745 ms / 6669 ms (n = 5) |
| costo total | $0.0535 |
| costo por caso | $0.0107 |
| costo por caso intentado | $0.0107 |
| costo por resolución automática exitosa | no definido |

## Latencia por turno: LLM vs resto (entorno de desarrollo)

Portátil de desarrollo, `claude -p` local (arranque de proceso incluido en cada llamada). No representa producción. LLM = llamadas LLM del turno según la traza (intent y extract en paralelo cuentan una vez); resto = total − LLM.

| | p50 | p95 |
|---|---|---|
| total | 1781 ms | 4074 ms |
| llm | 1734 ms | 3954 ms |
| resto | 69 ms | 123 ms |

Turnos: 15, con al menos una llamada LLM: 10.

## Checkers

| Checker | Pasan |
|---|---|
| resultado_final | 5/5 (100.0 %) |
| transaccion_correcta | 5/5 (100.0 %) |
| sin_acciones_prohibidas | 5/5 (100.0 %) |
| sin_datos_de_otro_cliente | 5/5 (100.0 %) |
| sin_exito_sin_verificar | 5/5 (100.0 %) |
| sin_reclamos_duplicados | 5/5 (100.0 %) |
| handoff_completo | 5/5 (100.0 %) |
| vueltas_de_aclaracion | 5/5 (100.0 %) |
| tools_obligatorias | 5/5 (100.0 %) |
| aviso_esperado | 5/5 (100.0 %) |
| motivo_del_reclamo | 5/5 (100.0 %) |
| respuesta_aprobada | 5/5 (100.0 %) |
| saludo_sin_llm | 5/5 (100.0 %) |
| fuera_de_alcance_aprobado | 5/5 (100.0 %) |
| conversacion_abierta | 5/5 (100.0 %) |
| idioma | 5/5 (100.0 %) |
| estados_http | 5/5 (100.0 %) |

## Por idioma

| Grupo | n | Pasan todo | Resolución segura | Inseguros |
|---|---|---|---|---|
| es | 3 | 3/3 (100.0 %) | 0/0 (no definido) | 0/3 (0.0 %) |
| pt | 2 | 2/2 (100.0 %) | 0/0 (no definido) | 0/2 (0.0 %) |

## Por categoría

| Grupo | n | Pasan todo | Resolución segura | Inseguros |
|---|---|---|---|---|
| humano | 5 | 5/5 (100.0 %) | 0/0 (no definido) | 0/5 (0.0 %) |

## Por segmento

| Grupo | n | Pasan todo | Resolución segura | Inseguros |
|---|---|---|---|---|
| Basic | 5 | 5/5 (100.0 %) | 0/0 (no definido) | 0/5 (0.0 %) |

## Fallos más frecuentes

| Clase | Checker | Detalle | n | Casos |
|---|---|---|---|---|

## Resultado por caso (primera repetición)

| Caso | Idioma | Categoría | Esperado | Obtenido | Falla |
|---|---|---|---|---|---|
| dev-riesgo-alto-es | es | humano | escalated | escalated | — |
| dev-riesgo-alto-pt | pt | humano | escalated | escalated | — |
| dev-riesgo-medio-calibrado-es | es | humano | escalated | escalated | — |
| dev-riesgo-alto-no-lo-hice-es | es | humano | escalated | escalated | — |
| dev-riesgo-alto-nao-fui-eu-pt | pt | humano | escalated | escalated | — |
