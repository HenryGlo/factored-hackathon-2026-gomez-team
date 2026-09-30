# analytics/demand/

## Propósito

Justificar con datos el flujo elegido ([ADR-0001](../../docs/decisions/0001-workflow-disputas.md)) y definir los resultados esperados para el cliente y el negocio.

## Qué irá aquí

**[Propuesta]** Notebooks o reportes con:

- Volumen de `complaints` con subcategoría "Cargo no reconocido" por mes, país, segmento, canal de recepción y producto afectado; SLA incumplido y días de resolución.
- Motivos de contacto en `call_center_interactions` (limitación: solo 6 valores, igual a la categoría).
- Comparación con otras subcategorías, declarando la uniformidad (H1 en [docs/data/quality-report.md](../../docs/data/quality-report.md)).
- Cobertura de idioma (sin portugués).

## Entradas y salidas

Entrada: `core.complaints`, `core.call_center_interactions`, `core.call_transcripts`. Salida: tablas y gráficos con n.

## Dependencias

[data_pipeline/](../../data_pipeline/README.md).

## Responsable sugerido

Data analyst.
