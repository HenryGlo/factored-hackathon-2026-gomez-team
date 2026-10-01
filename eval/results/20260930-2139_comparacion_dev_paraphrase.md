# Comparación de variantes · split dev_paraphrase · 2026-09-30 21:39

Generado con `python -m eval.compare` a partir de: `20260930-2044_baseline_dev_paraphrase.json`, `20260930-2139_sistema_dev_paraphrase.json` (crudos fuera de git).

Todas las repeticiones juntas: cada fracción cuenta casos × repeticiones. `sin_exito_sin_verificar` re-evaluado con el checker actual sobre las respuestas crudas (cambios por variante: `baseline` 0, `sistema` 0).

| Variante | Rep. | Resolución segura | Pasan todo | Inseguros | Escalamientos correctos | Contención | Latencia/turno p50 / p95 | Costo por caso | Commit |
|---|---|---|---|---|---|---|---|---|---|
| `baseline` | 1 | 51/70 (72.9 %) | 71/98 (72.4 %) | 0/98 (0.0 %) | 14/20 (70.0 %) | 84/98 (85.7 %) | 15 ms / 21 ms | $0.0000 | a2f0a1e (con cambios sin commit) |
| `sistema` | 1 | 66/70 (94.3 %) | 92/98 (93.9 %) | 0/98 (0.0 %) | 18/20 (90.0 %) | 80/98 (81.6 %) | 5.1 s / 10.4 s | $0.0153 | a2f0a1e (con cambios sin commit) |

## Latencia por turno: LLM vs resto (entorno de desarrollo)

Portátil de desarrollo con `claude -p` local; cada llamada incluye el arranque del proceso del CLI. No es una medida de producción. LLM = llamadas LLM del turno según la traza (intent y extract en paralelo cuentan una vez, los fallos cuentan el tiempo esperado); resto = total − LLM (código, tools, base y harness).

| Variante | Turnos | Con LLM | Total p50 / p95 | LLM p50 / p95 | Resto p50 / p95 |
|---|---|---|---|---|---|
| `baseline` | 242 | 177 | 15 ms / 21 ms | 0 ms / 0 ms | 15 ms / 21 ms |
| `sistema` | 258 | 180 | 5.1 s / 10.4 s | 5.0 s / 10.4 s | 43 ms / 58 ms |

## Casos fallidos por causa raíz

Una clase por caso: la del resultado final si falló, si no la de la transacción, si no la del primer checker. Extracción incluye la comprensión del mensaje (intención mal clasificada o datos mal extraídos).

| Variante | extracción | aclaración | política | escalamiento | idioma | tool | casos fallidos |
|---|---|---|---|---|---|---|---|
| `baseline` | 20 | 2 | 3 | 2 | 0 | 0 | 27/98 |
| `sistema` | 0 | 2 | 2 | 2 | 0 | 0 | 6/98 |

`baseline`: aclaración: dev-empate-sin-separar-es-p2, dev-fecha-equivocada-es-p1; escalamiento: dev-fallo-tool-es-p2, dev-riesgo-alto-pt-p1; extracción: dev-aclaracion-agotada-es-p2, dev-cambio-movimiento-es-p1, dev-cambio-movimiento-pt-p2, dev-claro-es-p1, dev-claro-es-p2, dev-claro-pt-p2, dev-comercio-vago-es-p1, dev-comercio-vago-es-p2, dev-consulta-es-p1, dev-empate-fecha-separa-es-p1, dev-fallo-tool-es-p1, dev-fuera-plazo-es-p1, dev-gasto-comercio-pt-p1, dev-gasto-comercio-pt-p2, dev-otro-cliente-es-p1, dev-reclamo-existente-pt-p2, dev-revertido-es-p1, dev-revertido-es-p2, dev-riesgo-desconocido-es-p2, dev-sin-monto-pt-p2; política: dev-claro-pt-p1, dev-reclamo-existente-es-p1, dev-reclamo-existente-es-p2

`sistema`: aclaración: dev-empate-sin-separar-es-p2, dev-fecha-equivocada-es-p1; escalamiento: dev-fallo-tool-es-p2, dev-riesgo-alto-pt-p1; política: dev-claro-pt-p1, dev-sin-monto-pt-p2

## Checkers fallidos por clase

Cuenta checkers, no casos: un mismo caso puede sumar varios.

| Variante | extracción | aclaración | política | escalamiento | idioma | tool | total |
|---|---|---|---|---|---|---|---|
| `baseline` | 36 | 4 | 18 | 8 | 4 | 18 | 88 |
| `sistema` | 1 | 5 | 5 | 4 | 0 | 6 | 21 |

### `baseline`: fallos

| Clase | Checker | Detalle | n | Casos |
|---|---|---|---|---|
| extracción | transaccion_correcta | esperada objetivo, vista ninguna | 15 | dev-claro-es-p1, dev-claro-es-p2, dev-claro-pt-p2, dev-sin-monto-pt-p2, dev-comercio-vago-es-p1, dev-comercio-vago-es-p2 |
| tool | estados_http | paso 2: 409 | 11 | dev-claro-es-p1, dev-claro-es-p2, dev-claro-pt-p1, dev-claro-pt-p2, dev-sin-monto-pt-p2, dev-comercio-vago-es-p1 |
| extracción | resultado_final | esperado ['resolved_case'], obtenido abstained | 7 | dev-claro-es-p1, dev-claro-es-p2, dev-claro-pt-p2, dev-sin-monto-pt-p2, dev-empate-fecha-separa-es-p1, dev-reclamo-existente-pt-p2 |
| extracción | resultado_final | esperado ['resolved_info'], obtenido abstained | 5 | dev-revertido-es-p1, dev-revertido-es-p2, dev-consulta-es-p1, dev-gasto-comercio-pt-p1, dev-gasto-comercio-pt-p2 |
| política | motivo_del_reclamo | esperado unrecognized, obtenido [] | 4 | dev-claro-es-p1, dev-claro-es-p2, dev-claro-pt-p1, dev-claro-pt-p2 |
| idioma | idioma | esperado pt, respondió es | 4 | dev-sin-monto-pt-p2, dev-cambio-movimiento-pt-p2, dev-reclamo-existente-pt-p2, dev-gasto-comercio-pt-p2 |
| extracción | resultado_final | esperado ['escalated'], obtenido abstained | 4 | dev-fuera-plazo-es-p1, dev-riesgo-desconocido-es-p2, dev-aclaracion-agotada-es-p2, dev-fallo-tool-es-p1 |
| política | tools_obligatorias | faltan ['create_dispute_case', 'get_case', 'get_existing_case', 'get_transaction', 'search | 3 | dev-claro-es-p1, dev-claro-es-p2, dev-claro-pt-p2 |
| política | aviso_esperado | esperado existing_case, vistos ['out_of_scope', 'out_of_scope'] | 3 | dev-reclamo-existente-es-p1, dev-reclamo-existente-es-p2, dev-reclamo-existente-pt-p2 |
| política | tools_obligatorias | faltan ['list_transactions'] | 3 | dev-consulta-es-p1, dev-gasto-comercio-pt-p1, dev-gasto-comercio-pt-p2 |
| tool | estados_http | paso 3: 409 | 3 | dev-otro-cliente-es-p1, dev-fallo-tool-es-p1, dev-fallo-tool-es-p2 |
| extracción | resultado_final | esperado ['resolved_case', 'clarified_then_resolved'], obtenido abstained | 2 | dev-comercio-vago-es-p1, dev-comercio-vago-es-p2 |
| tool | estados_http | paso 1: 409 | 2 | dev-empate-sin-separar-es-p2, dev-aclaracion-agotada-es-p2 |
| extracción | resultado_final | esperado ['clarified_then_resolved', 'resolved_case'], obtenido abstained | 2 | dev-cambio-movimiento-es-p1, dev-cambio-movimiento-pt-p2 |
| tool | estados_http | paso 4: 409 | 2 | dev-cambio-movimiento-es-p1, dev-cambio-movimiento-pt-p2 |
| política | aviso_esperado | esperado no_active_charge, vistos ['out_of_scope', 'out_of_scope'] | 2 | dev-revertido-es-p1, dev-revertido-es-p2 |
| escalamiento | resultado_final | esperado ['escalated'], obtenido resolved_info | 2 | dev-riesgo-alto-pt-p1, dev-fallo-tool-es-p2 |
| escalamiento | handoff_completo | falta handoff fallo_tool | 2 | dev-fallo-tool-es-p1, dev-fallo-tool-es-p2 |
| política | resultado_final | esperado ['resolved_case'], obtenido resolved_info | 1 | dev-claro-pt-p1 |
| aclaración | vueltas_de_aclaracion | vueltas 1 (máx 3, esperadas 0) | 1 | dev-claro-pt-p1 |
| política | tools_obligatorias | faltan ['create_dispute_case', 'get_case', 'get_existing_case', 'get_transaction'] | 1 | dev-claro-pt-p1 |
| aclaración | resultado_final | esperado ['resolved_case', 'clarified_then_resolved'], obtenido resolved_info | 1 | dev-fecha-equivocada-es-p1 |
| aclaración | resultado_final | esperado ['clarified_then_resolved'], obtenido resolved_info | 1 | dev-empate-sin-separar-es-p2 |
| extracción | transaccion_correcta | esperada objetivo, vista otra | 1 | dev-empate-sin-separar-es-p2 |
| aclaración | vueltas_de_aclaracion | vueltas 0 (máx 3, esperadas 1) | 1 | dev-empate-sin-separar-es-p2 |
| escalamiento | handoff_completo | falta handoff riesgo_alto | 1 | dev-riesgo-alto-pt-p1 |
| política | tools_obligatorias | faltan ['create_handoff', 'get_card_status', 'lock_card'] | 1 | dev-riesgo-alto-pt-p1 |
| escalamiento | handoff_completo | falta handoff fuera_de_plazo | 1 | dev-fuera-plazo-es-p1 |
| escalamiento | handoff_completo | falta handoff riesgo_desconocido | 1 | dev-riesgo-desconocido-es-p2 |
| escalamiento | handoff_completo | falta handoff aclaracion_agotada | 1 | dev-aclaracion-agotada-es-p2 |

### `sistema`: fallos

| Clase | Checker | Detalle | n | Casos |
|---|---|---|---|---|
| tool | estados_http | paso 2: 409 | 4 | dev-claro-pt-p1, dev-sin-monto-pt-p2, dev-fecha-equivocada-es-p1, dev-riesgo-alto-pt-p1 |
| política | resultado_final | esperado ['resolved_case'], obtenido resolved_info | 2 | dev-claro-pt-p1, dev-sin-monto-pt-p2 |
| aclaración | vueltas_de_aclaracion | vueltas 1 (máx 3, esperadas 0) | 2 | dev-claro-pt-p1, dev-sin-monto-pt-p2 |
| escalamiento | resultado_final | esperado ['escalated'], obtenido resolved_info | 2 | dev-riesgo-alto-pt-p1, dev-fallo-tool-es-p2 |
| política | tools_obligatorias | faltan ['create_dispute_case', 'get_case', 'get_existing_case', 'get_transaction'] | 1 | dev-claro-pt-p1 |
| política | motivo_del_reclamo | esperado unrecognized, obtenido [] | 1 | dev-claro-pt-p1 |
| aclaración | resultado_final | esperado ['resolved_case', 'clarified_then_resolved'], obtenido resolved_info | 1 | dev-fecha-equivocada-es-p1 |
| aclaración | resultado_final | esperado ['clarified_then_resolved'], obtenido resolved_info | 1 | dev-empate-sin-separar-es-p2 |
| extracción | transaccion_correcta | esperada objetivo, vista otra | 1 | dev-empate-sin-separar-es-p2 |
| aclaración | vueltas_de_aclaracion | vueltas 0 (máx 3, esperadas 1) | 1 | dev-empate-sin-separar-es-p2 |
| tool | estados_http | paso 1: 409 | 1 | dev-empate-sin-separar-es-p2 |
| escalamiento | handoff_completo | falta handoff riesgo_alto | 1 | dev-riesgo-alto-pt-p1 |
| política | tools_obligatorias | faltan ['create_handoff', 'get_card_status', 'lock_card'] | 1 | dev-riesgo-alto-pt-p1 |
| escalamiento | handoff_completo | falta handoff fallo_tool | 1 | dev-fallo-tool-es-p2 |
| tool | estados_http | paso 3: 409 | 1 | dev-fallo-tool-es-p2 |

## Aclaraciones por modo

Paso `clarify` de la traza: modo (llm / plantilla) y motivo. Las corridas anteriores a CONFIRM_MODE / CLARIFY_MODE no registran motivo (—).

| Variante | Modo:motivo → n |
|---|---|
| `baseline` | llm:mas_datos → 2, plantilla:elegir_candidatas → 4 |
| `sistema` | llm:mas_datos → 4, llm:tipo_problema → 1, plantilla:elegir_candidatas → 6 |
