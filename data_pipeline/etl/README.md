# data_pipeline/etl/

## Propósito

Mover los CSV a PostgreSQL de forma repetible e incremental.

## Qué irá aquí

**[Propuesta]**

- Descubrimiento de archivos y particiones en `RAW_DATA_DIR`.
- Carga a `raw` con columnas de linaje.
- Transformación a `core`: casteo según contrato, normalización de nulos y de país, completado de `amount_usd`, deduplicación por PK, zona horaria (P-29).
- Registro de corridas y archivos (`etl_runs`, `etl_files`).
- Punto de entrada de línea de comandos: carga completa, carga de una partición, subconjunto de clientes de demo.

## Entradas y salidas

Entrada: CSV + contratos. Salida: tablas `raw.*`, `core.*`, registros de linaje.

## Dependencias

[contracts/](../contracts/README.md), [quality/](../quality/README.md).

## Responsable sugerido

Software developer.
