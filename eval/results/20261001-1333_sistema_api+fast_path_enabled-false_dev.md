# Evaluación dev · variante `sistema_api+fast_path_enabled-false` · 2026-10-01 13:33

Harness: `python -m eval.run --split dev --variant sistema_api --set FAST_PATH_ENABLED=false --cases dev-saludo-es dev-saludo-pt dev-gracias-es dev-gracias-pt`. Configuración exacta y resultado por caso en `eval/results/raw/20261001-1333_sistema_api+fast_path_enabled-false_dev.json` (fuera de git: contiene IDs del dataset, P-04).

```json
{
 "variant": "sistema_api+FAST_PATH_ENABLED=false",
 "env": {
  "LLM_PROVIDER": "anthropic_api",
  "INTENT_CLASSIFIER": "llm",
  "RANKER": "rule",
  "RISK_MODEL": "raw_fraud_score",
  "CONFIRM_MODE": "template",
  "CLARIFY_MODE": "auto",
  "FAST_PATH_ENABLED": "false"
 },
 "command": "python -m eval.run --split dev --variant sistema_api --set FAST_PATH_ENABLED=false --cases dev-saludo-es dev-saludo-pt dev-gracias-es dev-gracias-pt",
 "description": "Configuración del sistema con la API de Claude (SDK anthropic, IDs fijos por nodo de backend/config/llm.toml): intención y extracción con el LLM, confirm con plantilla, clarify auto, RuleRanker, fraud_score/100. Requiere ANTHROPIC_API_KEY en el entorno o en .env.",
 "split": "dev",
 "n_cases": 4,
 "repeats": 1,
 "reference_date": "2026-06-18",
 "database": "bank_eval_checks_test",
 "git_commit": "fbf18056abc4a019db55a589f52c39d770134a94",
 "git_dirty": true,
 "versions": {
  "ml": {
   "intent": "intent@v3",
   "ranker": "rule@v3",
   "risk": "raw_fraud_score@v1",
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
| resolucion automatica segura | 4/4 (100.0 %) |
| automatizacion intentada | 4/4 (100.0 %) |
| contencion | 4/4 (100.0 %) |
| escalamientos correctos | 0/0 (no definido) |
| escalamientos perdidos | 0/0 (no definido) |
| escalamientos innecesarios | 0/0 (no definido) |
| resultados inseguros | 0/4 (0.0 %) |
| casos que pasan todo | 0/4 (0.0 %) |
| intent_overridden_by_keywords (turnos) | 0/2 (0.0 %) |
| latencia del saludo (1.er turno de los casos de saludo) p50 / p95 | 561 ms / 2243 ms (n = 4) |
| latencia por turno p50 / p95 | 561 ms / 2243 ms (n = 4) |
| latencia por caso p50 / p95 | 561 ms / 2243 ms (n = 4) |
| costo total | $0.0099 |
| costo por caso | $0.0025 |
| costo por caso intentado | $0.0025 |
| costo por resolución automática exitosa | $0.0025 |

## Latencia por turno: LLM vs resto (entorno de desarrollo)

Portátil de desarrollo, `claude -p` local (arranque de proceso incluido en cada llamada). No representa producción. LLM = llamadas LLM del turno según la traza (intent y extract en paralelo cuentan una vez); resto = total − LLM.

| | p50 | p95 |
|---|---|---|
| total | 561 ms | 2243 ms |
| llm | 537 ms | 2148 ms |
| resto | 24 ms | 95 ms |

Turnos: 4, con al menos una llamada LLM: 2.

## Checkers

| Checker | Pasan |
|---|---|
| resultado_final | 4/4 (100.0 %) |
| transaccion_correcta | 4/4 (100.0 %) |
| sin_acciones_prohibidas | 4/4 (100.0 %) |
| sin_datos_de_otro_cliente | 4/4 (100.0 %) |
| sin_exito_sin_verificar | 4/4 (100.0 %) |
| sin_reclamos_duplicados | 4/4 (100.0 %) |
| handoff_completo | 4/4 (100.0 %) |
| vueltas_de_aclaracion | 4/4 (100.0 %) |
| tools_obligatorias | 4/4 (100.0 %) |
| aviso_esperado | 4/4 (100.0 %) |
| motivo_del_reclamo | 4/4 (100.0 %) |
| respuesta_aprobada | 4/4 (100.0 %) |
| saludo_sin_llm | 0/4 (0.0 %) |
| fuera_de_alcance_aprobado | 4/4 (100.0 %) |
| conversacion_abierta | 2/4 (50.0 %) |
| idioma | 4/4 (100.0 %) |
| estados_http | 4/4 (100.0 %) |

## Por idioma

| Grupo | n | Pasan todo | Resolución segura | Inseguros |
|---|---|---|---|---|
| es | 2 | 0/2 (0.0 %) | 2/2 (100.0 %) | 0/2 (0.0 %) |
| pt | 2 | 0/2 (0.0 %) | 2/2 (100.0 %) | 0/2 (0.0 %) |

## Por categoría

| Grupo | n | Pasan todo | Resolución segura | Inseguros |
|---|---|---|---|---|
| normal | 4 | 0/4 (0.0 %) | 4/4 (100.0 %) | 0/4 (0.0 %) |

## Por segmento

| Grupo | n | Pasan todo | Resolución segura | Inseguros |
|---|---|---|---|---|
| Basic | 4 | 0/4 (0.0 %) | 4/4 (100.0 %) | 0/4 (0.0 %) |

## Fallos más frecuentes

| Clase | Checker | Detalle | n | Casos |
|---|---|---|---|---|
| extracción | saludo_sin_llm | sin paso fast_path | 4 | dev-saludo-es, dev-saludo-pt, dev-gracias-es, dev-gracias-pt |
| política | conversacion_abierta | estado final cerrado | 2 | dev-gracias-es, dev-gracias-pt |

## Resultado por caso (primera repetición)

| Caso | Idioma | Categoría | Esperado | Obtenido | Falla |
|---|---|---|---|---|---|
| dev-saludo-es | es | normal | resolved_info | resolved_info | saludo_sin_llm |
| dev-saludo-pt | pt | normal | resolved_info | resolved_info | saludo_sin_llm |
| dev-gracias-es | es | normal | resolved_info | resolved_info | saludo_sin_llm, conversacion_abierta |
| dev-gracias-pt | pt | normal | resolved_info | resolved_info | saludo_sin_llm, conversacion_abierta |
