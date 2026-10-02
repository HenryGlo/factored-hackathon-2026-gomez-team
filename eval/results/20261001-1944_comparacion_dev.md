# Comparación de variantes · split dev · 2026-10-01 19:44

Generado con `python -m eval.compare` a partir de: `20261001-1944_baseline_dev.json`, `20261001-1943_sistema_dev.json`, `20261001-1939_sistema_cascade+llm_provider-claude_cli_dev.json` (crudos fuera de git).

Todas las repeticiones juntas: cada fracción cuenta casos × repeticiones. `sin_exito_sin_verificar` re-evaluado con el checker actual sobre las respuestas crudas (cambios por variante: `baseline` 0, `sistema` 0, `sistema_cascade+llm_provider-claude_cli` 0).

| Variante | Rep. | Resolución segura | Pasan todo | Inseguros | Escalamientos correctos | Contención | Latencia/turno p50 / p95 | Costo por caso | Llamadas LLM fallidas | intent_overridden_by_keywords | Intención por LLM | Commit |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `baseline` | 1 | 75/75 (100.0 %) | 102/102 (100.0 %) | 0/102 (0.0 %) | 13/13 (100.0 %) | 89/102 (87.3 %) | 18 ms / 27 ms | $0.0000 | 0/199 (0.0 %) | 0/110 (0.0 %) | 0/110 (0.0 %) | 3a704da (con cambios sin commit) |
| `sistema` | 1 | 75/75 (100.0 %) | 102/102 (100.0 %) | 0/102 (0.0 %) | 13/13 (100.0 %) | 89/102 (87.3 %) | 3.6 s / 16.9 s | $0.0188 | 3/309 (1.0 %) | 0/110 (0.0 %) | 110/110 (100.0 %) | 3a704da (con cambios sin commit) |
| `sistema_cascade+llm_provider-claude_cli` | 1 | 75/75 (100.0 %) | 102/102 (100.0 %) | 0/102 (0.0 %) | 13/13 (100.0 %) | 89/102 (87.3 %) | 3.4 s / 14.2 s | $0.0122 | 4/203 (2.0 %) | 1/110 (0.9 %) | 20/110 (18.2 %) | 3a704da (con cambios sin commit) |

## Latencia del saludo

Primer turno de los casos de saludo (`expected.fast_path: true`): "hola", "gracias", "oi"…

| Variante | n | p50 | p95 |
|---|---|---|---|
| `baseline` | 4 | 12 ms | 13 ms |
| `sistema` | 4 | 18 ms | 27 ms |
| `sistema_cascade+llm_provider-claude_cli` | 4 | 15 ms | 18 ms |

## Latencia por turno: LLM vs resto (entorno de desarrollo)

Portátil de desarrollo con `claude -p` local; cada llamada incluye el arranque del proceso del CLI. No es una medida de producción. LLM = llamadas LLM del turno según la traza (intent y extract en paralelo cuentan una vez, los fallos cuentan el tiempo esperado); resto = total − LLM (código, tools, base y harness).

| Variante | Turnos | Con LLM | Total p50 / p95 | LLM p50 / p95 | Resto p50 / p95 |
|---|---|---|---|---|---|
| `baseline` | 284 | 187 | 18 ms / 27 ms | 0 ms / 0 ms | 18 ms / 27 ms |
| `sistema` | 284 | 187 | 3.6 s / 16.9 s | 3.6 s / 16.9 s | 43 ms / 76 ms |
| `sistema_cascade+llm_provider-claude_cli` | 284 | 178 | 3.4 s / 14.2 s | 3.4 s / 14.1 s | 42 ms / 69 ms |

## Casos fallidos por causa raíz

Una clase por caso: la del resultado final si falló, si no la de la transacción, si no la del primer checker. Extracción incluye la comprensión del mensaje (intención mal clasificada o datos mal extraídos).

| Variante | extracción | aclaración | política | escalamiento | idioma | tool | casos fallidos |
|---|---|---|---|---|---|---|---|
| `baseline` | 0 | 0 | 0 | 0 | 0 | 0 | 0/102 |
| `sistema` | 0 | 0 | 0 | 0 | 0 | 0 | 0/102 |
| `sistema_cascade+llm_provider-claude_cli` | 0 | 0 | 0 | 0 | 0 | 0 | 0/102 |

## Checkers fallidos por clase

Cuenta checkers, no casos: un mismo caso puede sumar varios.

| Variante | extracción | aclaración | política | escalamiento | idioma | tool | total |
|---|---|---|---|---|---|---|---|
| `baseline` | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `sistema` | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `sistema_cascade+llm_provider-claude_cli` | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

## Aclaraciones por modo

Paso `clarify` de la traza: modo (llm / plantilla) y motivo. Las corridas anteriores a CONFIRM_MODE / CLARIFY_MODE no registran motivo (—).

| Variante | Modo:motivo → n |
|---|---|
| `baseline` | llm:mas_datos → 2, plantilla:elegir_candidatas → 6 |
| `sistema` | llm:mas_datos → 2, plantilla:elegir_candidatas → 6 |
| `sistema_cascade+llm_provider-claude_cli` | llm:mas_datos → 2, plantilla:elegir_candidatas → 6 |
