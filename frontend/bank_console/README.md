# frontend/bank_console/

## Propósito

Consola de solo lectura para el personal del banco: ver reclamos, handoffs y la traza de cada turno. Sirve para la demo del camino de escalamiento y para auditar decisiones.

## Qué irá aquí

**[Propuesta]**

- Lista y detalle de reclamos (`/api/cases`).
- Lista y detalle de handoffs (`/api/handoffs`), mostrando por separado afirmaciones del cliente y hechos verificados ([docs/handoff-schema.md](../../docs/handoff-schema.md)).
- Visor de trazas por turno (`/api/traces/{turn_id}`): nodos, modelo y versión de prompt, tools, reglas de política, latencia y costo.

## Entradas y salidas

Entrada: API con sesión de rol `analyst`. Salida: ninguna escritura.

## Dependencias

[backend/api/](../../backend/api/README.md). Pendiente: autenticación de la consola (P-12 en [docs/open-questions.md](../../docs/open-questions.md)).

## Responsable sugerido

Software developer.
