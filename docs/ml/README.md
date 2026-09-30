# Fichas de modelos

**[Oficial]** Evaluar al menos un componente aprendido contra un baseline apropiado, con etiquetas o juicios de relevancia válidos, sin leakage, y justificar representaciones, métricas, umbrales y splits.

| Ficha | Componente | Rol en el flujo |
|---|---|---|
| [ranker.md](ranker.md) | Ranker de transacciones | Componente aprendido principal. Identifica el cargo que el cliente disputa. |
| [fraud-risk.md](fraud-risk.md) | Riesgo de fraude calibrado | Alimenta la regla R6 (escalar riesgo alto). |
| [intent-classifier.md](intent-classifier.md) | Clasificador de intención (baselines) | Baselines contra los que se compara el nodo de intención con LLM. |

Ninguna ficha tiene resultados todavía. Las secciones "Resultados" se llenan desde `eval/results/` con n y denominadores.
