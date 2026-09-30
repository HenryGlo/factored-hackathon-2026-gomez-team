# frontend/customer_chat/

## Propósito

Chat donde el cliente de prueba inicia sesión y conversa con el agente en español o portugués.

## Qué irá aquí

**[Propuesta]**

- Pantalla de login con usuario y contraseña (`/api/auth/csrf`, `/api/auth/login`), marcada claramente como entorno de demostración.
- Vista de chat que renderiza cada bloque:
  - `candidate_list`: lista seleccionable + opción "ninguno" + indicador de vuelta (1/3).
  - `transaction_card`: detalle del movimiento con botones "Sí, es este" / "No es este".
  - `action_confirmation`: resumen, aviso de que no es una devolución, botones Confirmar / Cancelar (envía `confirm` con el token).
  - `result`, `handoff_notice`, `notice`, `error`, `text`.
- Botón permanente "Hablar con una persona" (`request_human`).
- Generación de `Idempotency-Key` por intento y reintento seguro.
- Manejo de sesión expirada.

Ejemplo: el cliente escribe "Tengo un cobro de $120 que no reconozco" y ve una tarjeta con el movimiento para confirmar.

## Entradas y salidas

Entrada: bloques de la API. Salida: mensajes y acciones.

## Dependencias

[backend/api/](../../backend/api/README.md).

## Responsable sugerido

Software developer.
