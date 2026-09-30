# ADR-0004: Modelo por nodo

Estado: Aceptada · Etiqueta: **[Decisión]**

## Contexto

- **[Oficial]** Hacer explícitos los trade-offs entre autonomía, precisión, latencia, costo y supervisión humana; reportar latencia p50/p95 y costo por caso.
- Los nodos tienen dificultad distinta: clasificar intención o extraer un monto es más simple que explicar un resultado de política o resumir un caso para un humano.

## Decisión

- **Haiku 4.5** para intención, extracción, aclaración y confirmación (tareas cortas, frecuentes, con salida estructurada).
- **Sonnet 5** para la explicación final al cliente y el resumen del handoff (tareas de redacción con más contexto, una vez por conversación).
- IDs exactos de modelo en variables de entorno (`LLM_MODEL_FAST`, `LLM_MODEL_REASONING`); Pendiente confirmar IDs y precios (P-07).
- Prompts versionados por nodo; cada traza registra modelo y versión de prompt.

## Alternativas

| Alternativa | Por qué no |
|---|---|
| Sonnet en todos los nodos | Más costo y latencia en los nodos más frecuentes, sin evidencia de que mejore. |
| Haiku en todos los nodos | Puede ser suficiente; se verifica en la ablación. |
| Modelos locales o clásicos en intención | Se evalúan como baselines ([intent-classifier.md](../ml/intent-classifier.md)). |

## Consecuencias

- La ablación "modelo por nodo" ([evaluation.md](../evaluation.md)) debe confirmar o revertir esta decisión con datos.
- Dos modelos que versionar y monitorear.
