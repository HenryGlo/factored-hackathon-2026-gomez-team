# data_pipeline/quality/

## Propósito

Controles de calidad que corren en cada carga y producen un reporte reproducible.

## Qué irá aquí

**[Propuesta]**

- Chequeos por contrato: tipos, nulos, dominios, PK únicas, FK huérfanas, duplicados por contenido.
- Chequeos de volumen: filas por partición vs corrida anterior.
- Chequeos específicos del dominio: `amount_usd` consistente con la tasa del día; timestamps vs partición.
- Salida del reporte en `analytics/data_quality/` para el análisis del data analyst.

## Entradas y salidas

Entrada: `raw` y `core`. Salida: resultado por chequeo (pasa/falla, n afectados / n total) y decisión de bloquear o no la carga.

## Dependencias

[contracts/](../contracts/README.md).

## Responsable sugerido

Data analyst.
