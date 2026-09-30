# ADR-0005: Máquina de estados con loop acotado en vez de agente único

Estado: Aceptada · Etiqueta: **[Decisión]**

## Contexto

- **[Oficial]** "La IA no debe ser autónoma solo porque puede." Hay que definir qué acciones requieren confirmación, cuándo abstenerse y cuándo transferir, y aplicar permisos y políticas fuera del texto del modelo.
- **[Oficial]** Demostrar trazabilidad, reintentos acotados y fallback seguro.
- Un agente único con todos los tools decide el orden de pasos dentro del prompt: es más difícil garantizar que confirme antes de actuar y que no pregunte indefinidamente.

## Decisión

Un **controlador con máquina de estados explícita** (`inicio`, `aclarando`, `confirmando_movimiento`, `confirmando_accion`, `ejecutando`, `cerrado`, `escalado`) decide el siguiente nodo. El loop de aclaración está **acotado a 3 vueltas**, contadas en código; al agotarse, se escala. Ver [conversation-flow.md](../conversation-flow.md).

## Alternativas

| Alternativa | Por qué no |
|---|---|
| Agente único con tools (variante C de la ablación) | Menos control y auditoría; se compara en la ablación. |
| Prompt chain sin estado (variante B) | No maneja bien la aclaración multi-turno. |
| Solo reglas sin LLM (variante A) | No entiende lenguaje libre ni portugués; es el baseline. |

## Consecuencias

- Comportamiento predecible y auditable: cada transición queda en la traza.
- Menos flexibilidad para peticiones fuera del flujo, que se abstienen o escalan.
- El límite de 3 vueltas es una elección del equipo; se revisa con los resultados de dev.
