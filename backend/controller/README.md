# backend/controller/

## Propósito

**[Decisión]** Único dueño del estado de la conversación. Implementa la máquina de estados (`inicio`, `aclarando`, `confirmando_movimiento`, `confirmando_accion`, `ejecutando`, `cerrado`, `escalado`) y decide qué nodo, tool o política se ejecuta. Ver [docs/conversation-flow.md](../../docs/conversation-flow.md) y [ADR-0005](../../docs/decisions/0005-maquina-de-estados-con-loop-acotado.md).

## Qué irá aquí

**[Propuesta]**

- Definición de estados y tabla de transiciones.
- Orquestador de turno: carga estado, ejecuta nodos, llama tools, evalúa política, arma bloques y guarda el nuevo estado.
- Contador de vueltas de aclaración (máximo 3) y disparadores de escalamiento.
- Emisión y validación de `confirmation_token`.
- Reintentos acotados, timeouts y fallback seguro.
- Registro de trazas por paso.

## Entradas y salidas

Entrada: mensaje o acción + sesión. Salida: nuevo estado, bloques de UI y traza del turno.

## Dependencias

[nodes/](../nodes/README.md), [tools/](../tools/README.md), [policy/](../policy/README.md), [persistence/](../persistence/README.md).

## Responsable sugerido

Software developer, con el data scientist para los puntos de integración con nodos LLM.
