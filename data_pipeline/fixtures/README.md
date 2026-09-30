# data_pipeline/fixtures/

## Propósito

**[Oficial]** Demostrar la corrección de las actualizaciones con un fixture de prueba claramente etiquetado, ya que el dataset es estático.

## Contenido

**[Decisión]** `incremental/`: archivos **SINTÉTICOS creados por el equipo**. No son filas del dataset (P-04). Todos los IDs empiezan por `FXT-` y los comercios por `FIXTURE`. Las cabeceras son iguales a las de los CSV reales.

| Carpeta | Qué simula |
|---|---|
| `base/` | Carga inicial: 3 clientes, 4 productos, tasas y transacciones de 2026-07-01, 02 y 03. |
| `update/` | Día nuevo (2026-07-04); llegada tardía de un día ya cargado (`transactions_20260702_late.csv`); re-entrega de 2026-07-03 con una fila corregida (`FXT-T0303`: Pending → Approved, 45.10 → 45.01). |
| `bad_owner/` | Día 2026-07-05 con una transacción de `FXT-C002` sobre un producto de `FXT-C001` (rompe el aislamiento por cliente). |

Resultados esperados (los verifica [tests/test_incremental.py](../tests/test_incremental.py)):

- Tras `update/`: se reemplazan solo las particiones 02, 03 y 04 (−6 / +10 filas). Las filas del 01 no se reescriben (mismo `xmin`) y la fila corregida queda con los valores nuevos.
- Correr la incremental otra vez: 0 archivos, estado `noop`, mismas filas y mismos `xmin`.
- Tras `bad_owner/`: con el umbral de 0,1 % la corrida falla sin tocar `ref`. Con un umbral permisivo, `FXT-T0502` va a `ref.rejected_rows` con motivo `transaction_customer_product_mismatch` y las otras dos filas se cargan.

Pendiente: casos de evolución de esquema (columna nueva) y de duplicado de PK entre particiones.

## Responsable sugerido

Data analyst, con el software developer.
