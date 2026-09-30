# frontend/

## Propósito

**[Decisión]** Dos interfaces sobre la misma API: el chat del cliente y la consola del banco. El frontend solo renderiza bloques y envía mensajes o acciones; nunca decide si se ejecuta algo.

| Carpeta | Contenido |
|---|---|
| [customer_chat/](customer_chat/README.md) | Chat del cliente. |
| [bank_console/](bank_console/README.md) | Consola del banco (reclamos, handoffs, trazas). |

**[Propuesta]** Aquí también irán la configuración compartida del proyecto de frontend y los componentes comunes (render de bloques, cliente HTTP con `Authorization` e `Idempotency-Key`). Pendiente: framework (decisión del software developer).

## Entradas y salidas

Entrada: respuestas de la API ([docs/api-contract.md](../docs/api-contract.md)). Salida: peticiones a la API.

## Dependencias

[backend/api/](../backend/api/README.md). Variable `PUBLIC_API_BASE_URL` de [.env.example](../.env.example).

## Responsable sugerido

Software developer.
