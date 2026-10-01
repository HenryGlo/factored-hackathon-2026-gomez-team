# Comparación de variantes · split dev · 2026-10-01 16:01

Generado con `python -m eval.compare` a partir de: `20261001-1529_sistema_api_dev.json`, `20261001-1553_sistema_cascade_dev.json` (crudos fuera de git).

Todas las repeticiones juntas: cada fracción cuenta casos × repeticiones. `sin_exito_sin_verificar` re-evaluado con el checker actual sobre las respuestas crudas (cambios por variante: `sistema_api` 0, `sistema_cascade` 0).

| Variante | Rep. | Resolución segura | Pasan todo | Inseguros | Escalamientos correctos | Contención | Latencia/turno p50 / p95 | Costo por caso | Llamadas LLM fallidas | intent_overridden_by_keywords | Intención por LLM | Commit |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `sistema_api` | 1 | 56/56 (100.0 %) | 81/81 (100.0 %) | 0/81 (0.0 %) | 11/11 (100.0 %) | 70/81 (86.4 %) | 1.4 s / 4.4 s | $0.0072 | 0/240 (0.0 %) | 0/87 (0.0 %) | 87/87 (100.0 %) | 0cc835a |
| `sistema_cascade` | 1 | 56/56 (100.0 %) | 81/81 (100.0 %) | 0/81 (0.0 %) | 11/11 (100.0 %) | 70/81 (86.4 %) | 1.3 s / 5.2 s | $0.0044 | 1/152 (0.7 %) | 1/87 (1.1 %) | 15/87 (17.2 %) | 0cc835a (con cambios sin commit) |

## Latencia del saludo

Primer turno de los casos de saludo (`expected.fast_path: true`): "hola", "gracias", "oi"…

| Variante | n | p50 | p95 |
|---|---|---|---|
| `sistema_api` | 4 | 16 ms | 17 ms |
| `sistema_cascade` | 4 | 13 ms | 14 ms |

## Latencia por turno: LLM vs resto (entorno de desarrollo)

Portátil de desarrollo con `claude -p` local; cada llamada incluye el arranque del proceso del CLI. No es una medida de producción. LLM = llamadas LLM del turno según la traza (intent y extract en paralelo cuentan una vez, los fallos cuentan el tiempo esperado); resto = total − LLM (código, tools, base y harness).

| Variante | Turnos | Con LLM | Total p50 / p95 | LLM p50 / p95 | Resto p50 / p95 |
|---|---|---|---|---|---|
| `sistema_api` | 208 | 141 | 1.4 s / 4.4 s | 1.4 s / 4.3 s | 32 ms / 63 ms |
| `sistema_cascade` | 208 | 132 | 1.3 s / 5.2 s | 1.2 s / 5.2 s | 54 ms / 82 ms |

## Casos fallidos por causa raíz

Una clase por caso: la del resultado final si falló, si no la de la transacción, si no la del primer checker. Extracción incluye la comprensión del mensaje (intención mal clasificada o datos mal extraídos).

| Variante | extracción | aclaración | política | escalamiento | idioma | tool | casos fallidos |
|---|---|---|---|---|---|---|---|
| `sistema_api` | 0 | 0 | 0 | 0 | 0 | 0 | 0/81 |
| `sistema_cascade` | 0 | 0 | 0 | 0 | 0 | 0 | 0/81 |

## Checkers fallidos por clase

Cuenta checkers, no casos: un mismo caso puede sumar varios.

| Variante | extracción | aclaración | política | escalamiento | idioma | tool | total |
|---|---|---|---|---|---|---|---|
| `sistema_api` | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `sistema_cascade` | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

## Aclaraciones por modo

Paso `clarify` de la traza: modo (llm / plantilla) y motivo. Las corridas anteriores a CONFIRM_MODE / CLARIFY_MODE no registran motivo (—).

| Variante | Modo:motivo → n |
|---|---|
| `sistema_api` | llm:mas_datos → 2, plantilla:elegir_candidatas → 3 |
| `sistema_cascade` | llm:mas_datos → 2, plantilla:elegir_candidatas → 3 |
