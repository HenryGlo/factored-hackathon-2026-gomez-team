# Documentación

Índice de la documentación del proyecto. Las etiquetas **[Oficial]**, **[Decisión]**, **[Propuesta]** y **[Supuesto]** se explican en el [README raíz](../README.md).

## Fuentes oficiales

**[Oficial]** Material entregado por los organizadores (guardado localmente en `data/`, fuera del control de versiones):

- Enunciado: *Factored AI & Data Hackathon 2026 — Problem Statement*.
- Presentación del kickoff (25 de septiembre).
- *LATAM Bank Dataset Summary* v1.0.0.
- *LATAM Bank Complete Data Dictionary* v1.0.0 (contiene credenciales del bucket: **no copiar a ningún archivo versionado**).

## Documentos

| Documento | Contenido |
|---|---|
| [architecture.md](architecture.md) | Componentes, responsabilidades, flujo de datos; qué hace el LLM, el ML y el código determinista. |
| [conversation-flow.md](conversation-flow.md) | Nodos, estados, transiciones y los tres caminos del reto. |
| [api-contract.md](api-contract.md) | Endpoints, peticiones, respuestas, bloques de UI, Idempotency-Key y confirmation_token. |
| [tools-contract.md](tools-contract.md) | Cada tool con entradas, salidas, errores y permisos. |
| [llm-data.md](llm-data.md) | Capa LLM: qué datos salen al modelo en cada nodo (P-05), contexto del CLI y latencias medidas. |
| [prompts/](prompts/) | Prompts de trabajo por fase (03: backend, capa LLM y harness). |
| [policies.md](policies.md) | Reglas R1–R6 (supuestos de práctica). |
| [handoff-schema.md](handoff-schema.md) | Campos del handoff a una persona. |
| [data/](data/README.md) | Inventario de tablas, reporte de calidad y uso de datos. |
| [ml/](ml/README.md) | Fichas de modelos: ranker, riesgo de fraude, intención. |
| [evaluation.md](evaluation.md) | Taxonomía de casos, métricas, splits, juez LLM y ablaciones. |
| [decisions/](decisions/README.md) | ADR numerados. |
| [submission.md](submission.md) | Checklist de entrega. |
| [open-questions.md](open-questions.md) | Todo lo pendiente de confirmar. |
- [Ciclo de mejora con Opus](improvement-loop.md): feedback y fallos → reporte y casos propuestos, siempre con revisión humana.
