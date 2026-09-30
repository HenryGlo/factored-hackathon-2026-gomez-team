# data_pipeline/contracts/

## Propósito

Contratos de datos por tabla: el esquema esperado y las reglas que una partición debe cumplir para cargarse a `core`.

## Qué irá aquí

**[Propuesta]** Un contrato por tabla usada ([docs/data/usage.md](../../docs/data/usage.md)) con:

- Columnas, tipos y nulabilidad según el diccionario ([docs/data/inventory.md](../../docs/data/inventory.md)).
- PK y FK.
- Dominios de valores (por ejemplo `transaction_status` ∈ {Approved, Declined, Pending, Reversed}), aceptando los alias en español encontrados en los datos (H12 en [docs/data/quality-report.md](../../docs/data/quality-report.md)).
- Umbrales: qué porcentaje de filas rechazadas bloquea la carga.
- Versión del contrato, para manejar evolución de esquema.

## Entradas y salidas

Entrada: diccionario de datos. Salida: contratos que usan [etl/](../etl/README.md) y [quality/](../quality/README.md).

## Dependencias

Ninguna.

## Responsable sugerido

Data analyst.
