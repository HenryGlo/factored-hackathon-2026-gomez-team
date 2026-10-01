# Comparación de variantes · split dev_paraphrase · 2026-10-01 16:01

Generado con `python -m eval.compare` a partir de: `20261001-1537_sistema_api_dev_paraphrase.json`, `20261001-1601_sistema_cascade_dev_paraphrase.json` (crudos fuera de git).

Todas las repeticiones juntas: cada fracción cuenta casos × repeticiones. `sin_exito_sin_verificar` re-evaluado con el checker actual sobre las respuestas crudas (cambios por variante: `sistema_api` 0, `sistema_cascade` 0).

| Variante | Rep. | Resolución segura | Pasan todo | Inseguros | Escalamientos correctos | Contención | Latencia/turno p50 / p95 | Costo por caso | Llamadas LLM fallidas | intent_overridden_by_keywords | Intención por LLM | Commit |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `sistema_api` | 1 | 68/68 (100.0 %) | 96/96 (100.0 %) | 0/96 (0.0 %) | 20/20 (100.0 %) | 76/96 (79.2 %) | 1.4 s / 4.5 s | $0.0073 | 4/282 (1.4 %) | 0/100 (0.0 %) | 100/100 (100.0 %) | 0cc835a (con cambios sin commit) |
| `sistema_cascade` | 1 | 68/68 (100.0 %) | 96/96 (100.0 %) | 0/96 (0.0 %) | 20/20 (100.0 %) | 76/96 (79.2 %) | 1.4 s / 4.8 s | $0.0046 | 2/180 (1.1 %) | 0/100 (0.0 %) | 8/100 (8.0 %) | 0cc835a (con cambios sin commit) |

## Latencia por turno: LLM vs resto (entorno de desarrollo)

Portátil de desarrollo con `claude -p` local; cada llamada incluye el arranque del proceso del CLI. No es una medida de producción. LLM = llamadas LLM del turno según la traza (intent y extract en paralelo cuentan una vez, los fallos cuentan el tiempo esperado); resto = total − LLM (código, tools, base y harness).

| Variante | Turnos | Con LLM | Total p50 / p95 | LLM p50 / p95 | Resto p50 / p95 |
|---|---|---|---|---|---|
| `sistema_api` | 260 | 176 | 1.4 s / 4.5 s | 1.3 s / 4.5 s | 40 ms / 76 ms |
| `sistema_cascade` | 260 | 170 | 1.4 s / 4.8 s | 1.3 s / 4.8 s | 60 ms / 89 ms |

## Casos fallidos por causa raíz

Una clase por caso: la del resultado final si falló, si no la de la transacción, si no la del primer checker. Extracción incluye la comprensión del mensaje (intención mal clasificada o datos mal extraídos).

| Variante | extracción | aclaración | política | escalamiento | idioma | tool | casos fallidos |
|---|---|---|---|---|---|---|---|
| `sistema_api` | 0 | 0 | 0 | 0 | 0 | 0 | 0/96 |
| `sistema_cascade` | 0 | 0 | 0 | 0 | 0 | 0 | 0/96 |

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
| `sistema_api` | llm:mas_datos → 4, plantilla:elegir_candidatas → 5 |
| `sistema_cascade` | llm:mas_datos → 4, plantilla:elegir_candidatas → 5 |
