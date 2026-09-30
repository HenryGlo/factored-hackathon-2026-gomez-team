# data_pipeline/

## Propósito

ETL repetible de los CSV del dataset a PostgreSQL, con contratos de datos, controles de calidad, linaje y política de actualización.

**[Oficial]** El reto pide preparación de datos repetible con contratos, controles de calidad, linaje y una política de actualización/frescura. Si solo hay datos estáticos, demostrar la corrección de las actualizaciones con un fixture de prueba claramente etiquetado. Procesamiento batch, incremental o streaming según la necesidad; la entrega incremental de archivos no obliga a usar streaming.

| Carpeta | Contenido |
|---|---|
| [contracts/](contracts/README.md) | Contratos de datos por tabla. |
| [etl/](etl/README.md) | Extracción, transformación y carga. |
| [quality/](quality/README.md) | Controles de calidad y reporte. |
| [fixtures/](fixtures/README.md) | Fixture etiquetado para probar actualizaciones incrementales. |

## Diseño

**[Propuesta]**

- Esquemas en PostgreSQL:
  - `raw`: los CSV tal como llegan (todo texto) + `source_file`, `partition_date`, `load_id`, `loaded_at`.
  - `core`: tablas limpias y tipadas según el diccionario, deduplicadas por PK, con normalizaciones (país, `amount_usd` completado con `daily_exchange_rates`).
  - `app`: tablas de la aplicación (las crea [backend/persistence/](../backend/persistence/README.md), no el ETL).
- **Batch incremental por partición** (`year=/month=/day=`): cada partición se carga una vez; volver a correr es idempotente (upsert por PK).
- **Linaje**: tabla `etl_runs` (run, commit, fecha, parámetros) y `etl_files` (archivo, partición, filas leídas, rechazadas, hash).
- **Frescura**: el dataset es estático; la política documenta cómo se procesaría una partición nueva o tardía y se prueba con el fixture.
- Pendiente: si se carga todo `transactions` o un subconjunto de clientes de demo (P-06 en [docs/open-questions.md](../docs/open-questions.md)).

El material previo en `dashboard/scripts/build_db.py` (DuckDB) ya resuelve descubrimiento de esquemas, casteos y deduplicación; sirve de referencia.

## Entradas y salidas

Entrada: CSV en `RAW_DATA_DIR` (fuera del repo). Salida: esquemas `raw` y `core` en PostgreSQL, registros de linaje y reporte de calidad.

## Dependencias

Ninguna de otras carpetas de código. Lo consumen [backend/](../backend/README.md), [ml/](../ml/README.md), [eval/](../eval/README.md) y [analytics/](../analytics/README.md).

## Responsable sugerido

Software developer (carga), data analyst (contratos y calidad).
