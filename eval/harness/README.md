# eval/harness/

## Propósito

Correr cada caso de principio a fin contra el sistema y calcular métricas.

## Estado

**[Decisión] Implementado:** [runner.py](runner.py) (ejecuta el guion contra la API en proceso), [checkers.py](checkers.py) (deterministas), [metrics.py](metrics.py) (métricas y reporte), [env.py](env.py) (base `bank_eval_test` aislada).

## Qué irá aquí

**[Propuesta]**

- Ejecutor que abre una sesión de prueba, envía los turnos del caso (mensajes y acciones), respeta `confirmation_token` e `Idempotency-Key`, y guarda bloques y trazas.
- Inyección de fallas para casos adversarios: sesión expirada, tool caído, token vencido, respuesta lenta del LLM.
- Selector de variante de orquestación (A, B, C, D) y de modelo por nodo.
- Cálculo de métricas deterministas (estado final, acción, regla, handoff, fuga de datos) y llamada al juez para las no deterministas.
- Agregación con n por celda y repeticiones.

## Entradas y salidas

Entrada: casos de [cases/](../cases/README.md), configuración de variante. Salida: registros por caso y resumen en [results/](../results/README.md).

## Dependencias

[backend/api/](../../backend/api/README.md), [judge/](../judge/README.md).

## Responsable sugerido

Data scientist.
