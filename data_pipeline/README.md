# data_pipeline/

## Propósito

Pipeline repetible CSV → DuckDB → PostgreSQL, con controles de integridad, cuarentena, linaje y carga incremental. Documento completo: [docs/data/postgres.md](../docs/data/postgres.md).

**[Oficial]** El reto pide preparación de datos repetible con contratos, controles de calidad, linaje y una política de actualización/frescura. Si solo hay datos estáticos, hay que demostrar la corrección de las actualizaciones con un fixture de prueba claramente etiquetado.

## Diseño

**[Decisión]**

| Capa | Dónde | Contenido |
|---|---|---|
| raw | DuckDB `raw_<tabla>` | Los CSV tal cual (todo texto) + `source_file`, `partition_date`, `ingest_run`. |
| limpia | DuckDB `<tabla>` | Tipada, deduplicada por PK, normalizada y enriquecida. Las 13 tablas, para análisis y ML. |
| servida | PostgreSQL `ref` | Solo `customers`, `products`, `transactions` y `daily_exchange_rates`, con PK, FK y cuarentena (`ref.rejected_rows`). |
| linaje | PostgreSQL `ops` | `etl_runs` (una fila por corrida) y `etl_files` (una por CSV leído). Nunca se trunca. |
| aplicación | PostgreSQL `app` | La crea [backend/persistence/](../backend/persistence/README.md); el ETL nunca la toca. |

- **Carga completa:** reconstruye DuckDB desde los CSV y hace TRUNCATE + COPY de `ref` en una transacción.
- **Carga incremental por `process_date`:** solo los archivos nuevos o con hash distinto, y solo sus particiones.
- **Frescura:** el dataset es estático. La incremental se demuestra con el fixture sintético de [fixtures/](fixtures/README.md) y su test.
- **Volumen:** carga completa por defecto; `--customers-sample N` para un subconjunto determinista (cierra P-06).

## Uso

```bash
.venv/bin/python -m data_pipeline.run full                         # CSV → DuckDB → PostgreSQL
.venv/bin/python -m data_pipeline.run full --customers-sample 200  # subconjunto determinista
.venv/bin/python -m data_pipeline.run incremental                  # archivos nuevos o modificados
.venv/bin/python -m data_pipeline.run check                        # huérfanos, sin cargar
.venv/bin/pytest data_pipeline/tests -v                            # base *_test (TEST_DATABASE_URL)
```

| Archivo | Qué hace |
|---|---|
| [run.py](run.py) | Punto de entrada; aplica las migraciones de Alembic antes de cargar. |
| [config.py](config.py) | Rutas (`.env`) y diccionario de datos. Movido desde `dashboard/src/config.py`. |
| [etl/build_duckdb.py](etl/build_duckdb.py) | CSV → DuckDB (completa atómica e incremental). Movido y adaptado desde `dashboard/scripts/build_db.py`. |
| [etl/load_postgres.py](etl/load_postgres.py) | DuckDB → PostgreSQL: controles, cuarentena, COPY, linaje. |
| [etl/demo_customers.py](etl/demo_customers.py) | Regla determinista de clientes de demo por escenario. |
| [contracts/](contracts/README.md) | Contratos por tabla (YAML) y su motor: reglas bloqueantes o de advertencia. |
| [quality/explain_indexes.py](quality/explain_indexes.py) | EXPLAIN ANALYZE de los índices de `ref`. |
| [quality/schema_doc.py](quality/schema_doc.py) | Genera [docs/data/postgres-schema.md](../docs/data/postgres-schema.md) desde los modelos. |
| [tests/](tests/) | Incremental, carga completa (idempotencia, contratos, convivencia con `app`), roles, contratos vs modelos y tiempos de las tools. |

## Entradas y salidas

Entrada: CSV en `RAW_DATA_DIR` (fuera del repo). Salida: base DuckDB en `DUCKDB_PATH` y esquemas `ref` y `ops` en PostgreSQL.

## Dependencias

Modelos de [backend/persistence/models.py](../backend/persistence/models.py) (fuente única del esquema) y migraciones de [backend/migrations/](../backend/migrations/). Lo consumen [backend/](../backend/README.md), [ml/](../ml/README.md), [eval/](../eval/README.md) y [analytics/](../analytics/README.md).

## Responsable sugerido

Software developer (carga), data analyst (contratos y calidad).
