# Comparación de variantes · split dev · 2026-10-01 13:35

Generado con `python -m eval.compare` a partir de: `20261001-1333_sistema_api+fast_path_enabled-false_dev.json`, `20261001-1335_sistema_api_dev.json` (crudos fuera de git).

Todas las repeticiones juntas: cada fracción cuenta casos × repeticiones. `sin_exito_sin_verificar` re-evaluado con el checker actual sobre las respuestas crudas (cambios por variante: `sistema_api+fast_path_enabled-false` 0, `sistema_api` 0).

| Variante | Rep. | Resolución segura | Pasan todo | Inseguros | Escalamientos correctos | Contención | Latencia/turno p50 / p95 | Costo por caso | Llamadas LLM fallidas | intent_overridden_by_keywords | Commit |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `sistema_api+fast_path_enabled-false` | 1 | 4/4 (100.0 %) | 0/4 (0.0 %) | 0/4 (0.0 %) | 0/0 (no definido) | 4/4 (100.0 %) | 561 ms / 2243 ms | $0.0025 | 0/4 (0.0 %) | 0/2 (0.0 %) | fbf1805 (con cambios sin commit) |
| `sistema_api` | 1 | 8/8 (100.0 %) | 16/16 (100.0 %) | 0/16 (0.0 %) | 0/0 (no definido) | 16/16 (100.0 %) | 1.3 s / 4.7 s | $0.0042 | 0/28 (0.0 %) | 0/12 (0.0 %) | fbf1805 (con cambios sin commit) |

## Latencia del saludo

Primer turno de los casos de saludo (`expected.fast_path: true`): "hola", "gracias", "oi"…

| Variante | n | p50 | p95 |
|---|---|---|---|
| `sistema_api+fast_path_enabled-false` | 4 | 561 ms | 2243 ms |
| `sistema_api` | 4 | 13 ms | 49 ms |

## Latencia por turno: LLM vs resto (entorno de desarrollo)

Portátil de desarrollo con `claude -p` local; cada llamada incluye el arranque del proceso del CLI. No es una medida de producción. LLM = llamadas LLM del turno según la traza (intent y extract en paralelo cuentan una vez, los fallos cuentan el tiempo esperado); resto = total − LLM (código, tools, base y harness).

| Variante | Turnos | Con LLM | Total p50 / p95 | LLM p50 / p95 | Resto p50 / p95 |
|---|---|---|---|---|---|
| `sistema_api+fast_path_enabled-false` | 4 | 2 | 561 ms / 2243 ms | 537 ms / 2148 ms | 24 ms / 95 ms |
| `sistema_api` | 24 | 16 | 1.3 s / 4.7 s | 1.2 s / 4.6 s | 45 ms / 89 ms |

## Casos fallidos por causa raíz

Una clase por caso: la del resultado final si falló, si no la de la transacción, si no la del primer checker. Extracción incluye la comprensión del mensaje (intención mal clasificada o datos mal extraídos).

| Variante | extracción | aclaración | política | escalamiento | idioma | tool | casos fallidos |
|---|---|---|---|---|---|---|---|
| `sistema_api+fast_path_enabled-false` | 4 | 0 | 0 | 0 | 0 | 0 | 4/4 |
| `sistema_api` | 0 | 0 | 0 | 0 | 0 | 0 | 0/16 |

`sistema_api+fast_path_enabled-false`: extracción: dev-gracias-es, dev-gracias-pt, dev-saludo-es, dev-saludo-pt

## Checkers fallidos por clase

Cuenta checkers, no casos: un mismo caso puede sumar varios.

| Variante | extracción | aclaración | política | escalamiento | idioma | tool | total |
|---|---|---|---|---|---|---|---|
| `sistema_api+fast_path_enabled-false` | 4 | 0 | 2 | 0 | 0 | 0 | 6 |
| `sistema_api` | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

### `sistema_api+fast_path_enabled-false`: fallos

| Clase | Checker | Detalle | n | Casos |
|---|---|---|---|---|
| extracción | saludo_sin_llm | sin paso fast_path | 4 | dev-saludo-es, dev-saludo-pt, dev-gracias-es, dev-gracias-pt |
| política | conversacion_abierta | estado final cerrado | 2 | dev-gracias-es, dev-gracias-pt |

## Aclaraciones por modo

Paso `clarify` de la traza: modo (llm / plantilla) y motivo. Las corridas anteriores a CONFIRM_MODE / CLARIFY_MODE no registran motivo (—).

| Variante | Modo:motivo → n |
|---|---|
| `sistema_api+fast_path_enabled-false` | — |
| `sistema_api` | — |
