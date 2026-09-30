# data_pipeline/quality/

## Propósito

Controles de calidad que corren en cada carga y producen un reporte reproducible.

## Estado actual

**[Decisión]**

- Huérfanos y dueño del producto, antes de cada carga: `python -m data_pipeline.run check`. El resultado queda también en `ops.etl_runs.counts`.
- Conteos por capa (csv → raw → clean → ref) en cada corrida: `ops.etl_runs.counts`.
- Índices: [explain_indexes.py](explain_indexes.py) genera [docs/data/postgres-explain.md](../../docs/data/postgres-explain.md).

## Qué irá aquí

**[Propuesta]**

- Chequeos por contrato: tipos, nulos, dominios, PK únicas, FK huérfanas, duplicados por contenido.
- Chequeos de volumen: filas por partición vs corrida anterior.
- Chequeos específicos del dominio: `amount_usd` consistente con la tasa del día; timestamps vs partición.
- Salida del reporte en `analytics/data_quality/` para el análisis del data analyst.

## Entradas y salidas

Entrada: capas raw y limpia de DuckDB y `ref` de PostgreSQL. Salida: resultado por chequeo (pasa/falla, n afectados / n total) y decisión de bloquear o no la carga.

## Dependencias

[contracts/](../contracts/README.md).

## Responsable sugerido

Data analyst.
