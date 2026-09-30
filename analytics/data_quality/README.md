# analytics/data_quality/

## Propósito

Reporte de calidad reproducible generado desde el ETL del proyecto, que reemplaza las cifras de la exploración previa en [docs/data/quality-report.md](../../docs/data/quality-report.md).

## Qué irá aquí

**[Propuesta]**

- Conteos medidos vs diccionario, nulos, duplicados por PK y por contenido, FK huérfanas, desfase de timestamps, consistencia de `amount_usd`.
- Independencia entre columnas (V de Cramér) para documentar H1.
- Señal de `fraud_score` vs `is_fraud` (AUC, PR-AUC).
- Registro de discrepancias para consultar con organizadores (P-19).

## Entradas y salidas

Entrada: salida de [data_pipeline/quality/](../../data_pipeline/quality/README.md). Salida: reporte con fecha y versión del ETL.

## Dependencias

[data_pipeline/](../../data_pipeline/README.md).

## Responsable sugerido

Data analyst.
