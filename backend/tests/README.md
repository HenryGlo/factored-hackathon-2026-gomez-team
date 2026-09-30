# backend/tests/

## Propósito

Pruebas automáticas del backend. No reemplazan al harness de [eval/](../../eval/README.md), que mide calidad; aquí se prueba que el código hace lo que dice el contrato.

## Qué irá aquí

**[Propuesta]**

- Unitarias de política (una por regla R1–R6, con casos límite como exactamente 60 días).
- Unitarias de la máquina de estados (transiciones válidas e inválidas, límite de 3 vueltas).
- Permisos de tools: acceso a datos de otro cliente devuelve `not_found`.
- `confirmation_token`: vencido, reusado, ligado a otra transacción.
- Idempotencia: misma clave no crea dos reclamos; clave con cuerpo distinto da `409`.
- Integración de la API con el LLM simulado (respuestas fijas) y una base de prueba con el fixture de [data_pipeline/fixtures/](../../data_pipeline/fixtures/README.md).

## Entradas y salidas

Entrada: fixtures. Salida: reporte de pruebas en CI.

## Dependencias

Todas las subcarpetas de `backend/`.

## Responsable sugerido

Software developer.
