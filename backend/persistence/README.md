# backend/persistence/

## Propósito

Acceso a PostgreSQL: lectura de los datos del dataset cargados por el ETL y escritura del estado de la aplicación.

## Qué irá aquí

**[Propuesta]**

- Conexión y sesiones de base de datos.
- Repositorios de lectura sobre el esquema `core` (transacciones, clientes, productos), siempre filtrados por `customer_id`.
- Tablas y migraciones del esquema `app`: `sessions`, `conversations`, `turns`, `dispute_cases`, `handoffs`, `card_status_overrides`, `traces`, `idempotency_keys`, `confirmation_tokens`.
- Restricción de unicidad para evitar dos reclamos sobre la misma transacción (apoya R3).

## Entradas y salidas

Entrada: consultas del controlador y los tools. Salida: filas tipadas.

## Dependencias

Esquema `core` creado por [data_pipeline/](../../data_pipeline/README.md).

## Responsable sugerido

Software developer.
