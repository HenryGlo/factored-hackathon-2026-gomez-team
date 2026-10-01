# backend/api/

## Propósito

Capa HTTP: valida peticiones, autentica la sesión de prueba, aplica `Idempotency-Key` y devuelve bloques de UI. No contiene lógica de negocio.

## Qué irá aquí

**[Propuesta]**

- **[Decisión] Implementado (fases 1 y 5):**
  - autenticación en [backend/app/auth/](../app/auth/) (`/api/auth/csrf`, `/login`, `/logout`, `/me`);
  - conversaciones, turnos (Idempotency-Key obligatoria) y consola (`/api/cases`, `/api/handoffs`, `/api/traces/{turn_id}`, `/api/conversations/{id}`) en [backend/app/conversations.py](../app/conversations.py) y [backend/app/console/](../app/console/).

  Respuesta única por turno, sin SSE. El código del backend vive en `backend/app/`; esta carpeta queda como documentación.
- Rutas de conversación (`/api/conversations`, `/api/conversations/{id}/turns`): reciben mensaje o acción y delegan al controlador.
- Rutas de consola (`/api/cases`, `/api/handoffs`, `/api/traces/{turn_id}`): solo lectura para el rol `analyst`, con el usuario de base de datos de solo lectura.
- Esquemas de petición y respuesta, incluido el catálogo de bloques (`text`, `candidate_list`, `transaction_card`, `action_confirmation`, `result`, `handoff_notice`, `notice`, `error`).
- Middleware de idempotencia: guarda y reproduce respuestas por clave.
- Manejo de errores con los códigos del contrato.

## Entradas y salidas

Entrada: HTTP con `Authorization` e `Idempotency-Key`. Salida: JSON según [docs/api-contract.md](../../docs/api-contract.md).

## Dependencias

[controller/](../controller/README.md), [persistence/](../persistence/README.md).

## Responsable sugerido

Software developer.
