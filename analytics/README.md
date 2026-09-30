# analytics/

## Propósito

**[Oficial]** Evidencia de datos para el problema: motivos de contacto, patrones de demanda, calidad de datos y restricciones operativas, y costo por resolución (ROI). Separar mediciones offline, simulaciones y ahorros proyectados.

| Carpeta | Contenido |
|---|---|
| [demand/](demand/README.md) | Análisis de demanda del flujo de disputas. |
| [data_quality/](data_quality/README.md) | Reporte de calidad a partir del ETL. |
| [roi/](roi/README.md) | Costo por resolución y proyección de ahorro. |

Material previo relacionado (fuera de esta carpeta): `dashboard/`, `viability_check.py`, `viability_report.md`, `dataset_eval.ipynb`. Pendiente: moverlo aquí (P-15 en [docs/open-questions.md](../docs/open-questions.md)).

## Entradas y salidas

Entrada: esquemas `core` y reportes de calidad del ETL; resultados de [eval/results/](../eval/results/README.md). Salida: reportes y gráficos para la documentación y las slides.

## Dependencias

[data_pipeline/](../data_pipeline/README.md), [eval/](../eval/README.md).

## Responsable sugerido

Data analyst.
