# ADR-0002: Ranker en vez de LLM para identificar la transacción

Estado: Aceptada · Etiqueta: **[Decisión]**

## Contexto

- Un cliente describe el cargo de forma vaga ("Tengo un cobro de $120 que no reconozco") y puede tener decenas de transacciones en la ventana de búsqueda.
- **[Oficial]** Evaluar al menos un componente aprendido contra un baseline, con etiquetas válidas y sin leakage. Justificar dónde es apropiada la IA y dónde es preferible la lógica determinista.
- Pasar todas las transacciones al LLM aumenta costo y latencia, expone más datos al proveedor externo y puede producir IDs inexistentes.

## Decisión

El LLM solo **extrae** campos (monto, fecha, comercio, canal). Un **ranker de ML** ordena las transacciones candidatas: regresión logística como modelo principal y LightGBM lambdarank como retador, contra un baseline determinista de monto y recencia. Un umbral en código decide si la candidata es clara. Ficha: [ranker.md](../ml/ranker.md).

## Alternativas

| Alternativa | Por qué no |
|---|---|
| LLM elige la transacción entre las del cliente | Más caro y lento, difícil de calibrar, puede alucinar; se mantiene como variante de comparación en la ablación. |
| Solo reglas (monto exacto + recencia) | Frágil con montos aproximados y fechas relativas; queda como baseline y fallback. |
| Búsqueda semántica con embeddings | `merchant_name` es corto y a veces nulo; el problema es mayormente numérico y temporal. |

## Consecuencias

- Componente aprendido medible con Top-1, Recall@3 y MRR.
- Score utilizable como umbral para aclarar o abstenerse.
- Requiere etiquetas de relevancia construidas ([ADR-0003](0003-reclamos-generados-sobre-transacciones-reales.md)).
- Si el ranker falla, el sistema cae al baseline y lo registra.
