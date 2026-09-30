# ADR-0004: Modelo por nodo

Estado: Aceptada · Etiqueta: **[Decisión]**

## Contexto

- **[Oficial]** Hacer explícitos los trade-offs entre autonomía, precisión, latencia, costo y supervisión humana; reportar latencia p50/p95 y costo por caso.
- Los nodos tienen dificultad distinta: clasificar intención o extraer un monto es más simple que explicar un resultado de política o resumir un caso para un humano.

## Decisión

- **Haiku 4.5** para intención, extracción, aclaración y confirmación (tareas cortas, frecuentes, con salida estructurada).
- **Sonnet 5** para la explicación final al cliente y el resumen del handoff (tareas de redacción con más contexto, una vez por conversación).
- Un modelo por nodo, con alias del CLI (`haiku` | `sonnet`).
  - Valores por defecto en [backend/config/llm.toml](../../backend/config/llm.toml), versionado; override por entorno con `MODEL_<NODO>` (p. ej. `MODEL_EXPLAIN=haiku`). **Actualizado 2026-09-30**: reemplaza a `LLM_MODEL_FAST` y `LLM_MODEL_REASONING`.
  - La traza guarda el alias pedido **y** el ID real que devuelve el proveedor. Con `claude -p` (Claude Code 2.1.286), `haiku` → `claude-haiku-4-5-20251001` y `sonnet` → `claude-sonnet-5-5` (medido en [llm-data.md](../llm-data.md)).
  - Proveedor con `LLM_PROVIDER=claude_cli|fake`. La interfaz `LLMClient` permite agregar un cliente de la API de Claude sin tocar los nodos.
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
