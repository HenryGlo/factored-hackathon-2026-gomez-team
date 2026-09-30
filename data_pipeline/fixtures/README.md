# data_pipeline/fixtures/

## Propósito

**[Oficial]** Demostrar la corrección de las actualizaciones con un fixture de prueba claramente etiquetado, ya que el dataset es estático.

## Qué irá aquí

**[Propuesta]** Un conjunto pequeño de archivos **sintéticos creados por el equipo** (no filas del dataset, por P-04) etiquetados como `FIXTURE`, que simulan:

- Una carga inicial.
- Una partición nueva.
- Una partición tardía (fecha anterior a la última cargada).
- Un registro duplicado y uno corregido (misma PK, `last_updated` más reciente).
- Una columna nueva (evolución de esquema).

Y la descripción del resultado esperado en `core` después de cada paso, para una prueba automática.

## Entradas y salidas

Entrada: ninguna. Salida: archivos de fixture y resultados esperados.

## Dependencias

La usan [etl/](../etl/README.md) y [backend/tests/](../../backend/tests/README.md).

## Responsable sugerido

Data analyst, con el software developer.
