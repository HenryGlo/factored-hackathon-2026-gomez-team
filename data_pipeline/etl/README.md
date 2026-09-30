# data_pipeline/etl/

## Propósito

Mover los CSV a DuckDB y de DuckDB a PostgreSQL (`ref`) de forma repetible e incremental. Detalle: [docs/data/postgres.md](../../docs/data/postgres.md).

## Contenido

**[Decisión]**

- [build_duckdb.py](build_duckdb.py): descubre archivos y particiones en `RAW_DATA_DIR`, calcula el sha256 de cada archivo, carga `raw_<tabla>` con linaje y construye las tablas limpias (casteo según el diccionario, nulos, país, `amount_usd_filled`, dedup por PK). Modos completo (atómico) e incremental (archivos nuevos o modificados → solo sus particiones).
- [load_postgres.py](load_postgres.py): controles de integridad, cuarentena en `ref.rejected_rows`, umbral de 0,1 %, COPY a `ref` y linaje en `ops.etl_runs` / `ops.etl_files`.
- [demo_customers.py](demo_customers.py): subconjunto determinista de clientes que cubre los escenarios de prueba.

Zona horaria: los timestamps se guardan sin zona, tal como vienen (P-29; evidencia en [postgres.md](../../docs/data/postgres.md#zona-horaria)).

## Entradas y salidas

Entrada: CSV + modelos. Salida: `raw_*` y tablas limpias en DuckDB; `ref.*` y `ops.*` en PostgreSQL.

## Responsable sugerido

Software developer.
