# Comparación de variantes · split dev · 2026-09-30 21:39

Generado con `python -m eval.compare` a partir de: `20260930-2043_baseline_dev.json`, `20260930-2043_claude_cli_dev.json`, `20260930-2117_sistema_dev.json` (crudos fuera de git).

Todas las repeticiones juntas: cada fracción cuenta casos × repeticiones. `sin_exito_sin_verificar` re-evaluado con el checker actual sobre las respuestas crudas (cambios por variante: `baseline` 0, `claude_cli` 3, `sistema` 0).

| Variante | Rep. | Resolución segura | Pasan todo | Inseguros | Escalamientos correctos | Contención | Latencia/turno p50 / p95 | Costo por caso | Commit |
|---|---|---|---|---|---|---|---|---|---|
| `baseline` | 1 | 35/35 (100.0 %) | 50/50 (100.0 %) | 0/50 (0.0 %) | 10/10 (100.0 %) | 40/50 (80.0 %) | 16 ms / 23 ms | $0.0000 | a2f0a1e (con cambios sin commit) |
| `claude_cli` | 3 | 105/105 (100.0 %) | 150/150 (100.0 %) | 0/150 (0.0 %) | 30/30 (100.0 %) | 120/150 (80.0 %) | 7.5 s / 19.8 s | $0.0218 | 54a0e33 (con cambios sin commit) |
| `sistema` | 3 | 105/105 (100.0 %) | 150/150 (100.0 %) | 0/150 (0.0 %) | 30/30 (100.0 %) | 120/150 (80.0 %) | 3.9 s / 13.0 s | $0.0151 | a2f0a1e (con cambios sin commit) |

## Latencia por turno: LLM vs resto (entorno de desarrollo)

Portátil de desarrollo con `claude -p` local; cada llamada incluye el arranque del proceso del CLI. No es una medida de producción. LLM = llamadas LLM del turno según la traza (intent y extract en paralelo cuentan una vez, los fallos cuentan el tiempo esperado); resto = total − LLM (código, tools, base y harness).

| Variante | Turnos | Con LLM | Total p50 / p95 | LLM p50 / p95 | Resto p50 / p95 |
|---|---|---|---|---|---|
| `baseline` | 133 | 90 | 16 ms / 23 ms | 0 ms / 0 ms | 16 ms / 23 ms |
| `claude_cli` | 399 | 357 | 7.5 s / 19.8 s | 7.4 s / 19.7 s | 50 ms / 79 ms |
| `sistema` | 399 | 270 | 3.9 s / 13.0 s | 3.9 s / 12.9 s | 43 ms / 59 ms |

## Casos fallidos por causa raíz

Una clase por caso: la del resultado final si falló, si no la de la transacción, si no la del primer checker. Extracción incluye la comprensión del mensaje (intención mal clasificada o datos mal extraídos).

| Variante | extracción | aclaración | política | escalamiento | idioma | tool | casos fallidos |
|---|---|---|---|---|---|---|---|
| `baseline` | 0 | 0 | 0 | 0 | 0 | 0 | 0/50 |
| `claude_cli` | 0 | 0 | 0 | 0 | 0 | 0 | 0/150 |
| `sistema` | 0 | 0 | 0 | 0 | 0 | 0 | 0/150 |

## Checkers fallidos por clase

Cuenta checkers, no casos: un mismo caso puede sumar varios.

| Variante | extracción | aclaración | política | escalamiento | idioma | tool | total |
|---|---|---|---|---|---|---|---|
| `baseline` | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `claude_cli` | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `sistema` | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

## Aclaraciones por modo

Paso `clarify` de la traza: modo (llm / plantilla) y motivo. Las corridas anteriores a CONFIRM_MODE / CLARIFY_MODE no registran motivo (—).

| Variante | Modo:motivo → n |
|---|---|
| `baseline` | llm:mas_datos → 2, plantilla:elegir_candidatas → 3 |
| `claude_cli` | llm:— → 12 |
| `sistema` | llm:mas_datos → 6, llm:tipo_problema → 1, plantilla:elegir_candidatas → 11 |
