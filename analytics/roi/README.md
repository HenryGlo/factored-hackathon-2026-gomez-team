# analytics/roi/

## Propósito

**[Oficial]** Estimar costo por resolución y el impacto operativo, etiquetando por separado lo medido offline, lo simulado y lo proyectado. Nunca presentar una comparación offline como una mejora medida en producción.

## Qué irá aquí

**[Propuesta]**

- Línea base operativa del dataset: duración, espera, FCR y escalamiento en `call_center_interactions`; días de resolución y SLA en `complaints`.
- Costo del sistema por caso intentado y por resolución automatizada exitosa, tomado de [eval/results/](../../eval/results/README.md).
- Proyección de ahorro con supuestos explícitos (costo por minuto de agente, volumen, tasa de resolución segura). Pendiente: supuestos de costo (P-13 en [docs/open-questions.md](../../docs/open-questions.md)).
- Análisis de sensibilidad sobre esos supuestos.

## Entradas y salidas

Entrada: tablas `core`, resultados de evaluación, supuestos. Salida: tabla de ROI etiquetada como proyección.

## Dependencias

[eval/](../../eval/README.md), [data_pipeline/](../../data_pipeline/README.md).

## Responsable sugerido

Data analyst.
