# backend/nodes/

## Propósito

Unidades de trabajo del flujo. Cada nodo tiene entrada y salida tipadas y no cambia el estado por sí mismo: devuelve un resultado al controlador. Ver la tabla de nodos en [docs/conversation-flow.md](../../docs/conversation-flow.md).

## Estado

**[Decisión] Implementado (fase 2):** los 6 nodos LLM en [backend/app/llm/nodes.py](../app/llm/nodes.py) (entrada mínima, validación y guarda R5) y la conversión de fechas en [backend/app/dates.py](../app/dates.py). La orquestación llega en la fase 4.

## Qué irá aquí

**[Propuesta]** Un módulo por nodo:

- Intención e idioma (Haiku 4.5): clasifica el mensaje y detecta `es`/`pt`.
- Extracción (Haiku 4.5): devuelve monto, moneda, fecha o rango, comercio, canal; validado por esquema.
- Búsqueda y ranking: arma la consulta para `search_transactions` y aplica el umbral de "candidata clara".
- Aclaración (Haiku 4.5): redacta la pregunta a partir de las candidatas elegidas por código.
- Confirmación (Haiku 4.5): interpreta la respuesta del cliente sobre el movimiento.
- Explicación (Sonnet 5): redacta el resultado con los hechos y la regla aplicada.
- Resumen de handoff (Sonnet 5): redacta solo el campo `summary`.
- Variantes de reglas sin LLM para la ablación A ([docs/evaluation.md](../../docs/evaluation.md)).

Ejemplo de salida de extracción para "Tengo un cobro de $120 que no reconozco": `{monto: 120, moneda: null, fecha: null, comercio: null, canal: null}`.

## Entradas y salidas

Entrada: mensaje, historial resumido, candidatas o hechos según el nodo. Salida: objeto estructurado validado.

## Dependencias

[llm/](../llm/README.md), [tools/](../tools/README.md) (solo el nodo de búsqueda).

## Responsable sugerido

Data scientist.
