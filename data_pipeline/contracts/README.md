# data_pipeline/contracts/

## Propósito

Contratos de datos por tabla de `ref`: columnas, tipos, dominios, rangos, unicidad e integridad referencial. Cada regla es **bloqueante** o de **advertencia**.

## Contenido

**[Decisión]**

| Archivo | Tabla |
|---|---|
| [customers.yaml](customers.yaml) | `ref.customers` (incluye la derivación de `display_name`) |
| [products.yaml](products.yaml) | `ref.products` |
| [transactions.yaml](transactions.yaml) | `ref.transactions` |
| [daily_exchange_rates.yaml](daily_exchange_rates.yaml) | `ref.daily_exchange_rates` |
| [engine.py](engine.py) | Motor que evalúa los contratos en DuckDB antes de cargar. |

Formato de un contrato:

- `columns`: nombre → `type`, `nullable` y, si aplica, `derived` (expresión SQL sobre la capa limpia). Deben coincidir con [backend/persistence/models.py](../../backend/persistence/models.py); lo verifica [tests/test_contracts.py](../tests/test_contracts.py).
- `primary_key`, `partition` (unidad de la carga incremental).
- `rules`, cada una con `id`, `check` (`domain`, `range`, `unique`, `fk`, `expr`), `severity` y un `why` opcional. Además, cada columna con `nullable: false` genera una regla `not_null` bloqueante implícita.

Severidad:

- **`block`:** la fila va a `ref.rejected_rows` con `reason` = id de la regla y no se carga. Las reglas se evalúan en orden y manda la primera que falla. Si una tabla supera 0,1 % de rechazos, la corrida se detiene sin tocar `ref`.
- **`warn`:** la fila se carga. El conteo por regla queda en `ops.etl_runs.counts -> 'contract_warnings'`.

Advertencias con el dataset actual:

- `product_number_unique`: 12 filas (6 números repetidos, H14).
- `customer_accent_domain`: no dispara; los nulos (29,9 %) no cuentan.

`transaction_date_offset` (H16) y `transaction_amount_usd_consistency` no disparan.

Para cambiar una regla, editar el YAML y subir `version`. Las versiones de cada corrida quedan en `ops.etl_runs.params -> 'contract_versions'`.

## Responsable sugerido

Data analyst.
