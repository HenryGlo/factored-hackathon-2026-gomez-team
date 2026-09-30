# backend/persistence/

## Propósito

Acceso a PostgreSQL: lectura de los datos del dataset cargados por el ETL y escritura del estado de la aplicación.

## Qué irá aquí

**[Propuesta]**

- Conexión y sesiones de base de datos.
- Repositorios de lectura sobre el esquema `ref` (transacciones, clientes, productos), siempre filtrados por `customer_id`.
- **[Decisión] Implementado:** modelos SQLAlchemy de `ref`, `ops` y `app` en [models.py](models.py) y migraciones Alembic en [backend/migrations/](../migrations/) (`.venv/bin/alembic -c backend/alembic.ini upgrade head`, usa `ADMIN_DATABASE_URL`, el dueño de los esquemas).
- **Roles:** el backend se conecta con `DATABASE_URL` (usuario del grupo `app_rw`: lee `ref` y `ops`, lee/escribe `app`); la consola con `CONSOLE_DATABASE_URL` (grupo `app_ro`, solo lectura). Nunca el superusuario. Diagramas: [docs/data/postgres-schema.md](../../docs/data/postgres-schema.md).
- Esquema `app`: `sessions`, `conversations`, `turns`, `confirmation_tokens`, `idempotency_keys`, `dispute_cases`, `card_status_overrides`, `handoffs`, `traces` y la vista `card_status_effective` (override más reciente o `ref.products.product_status`).
- `dispute_cases`: índice único parcial (`customer_id`, `transaction_id`) para reclamos abiertos (R3), `idempotency_key` y `confirmation_token_id` UNIQUE, `confirmed_at`.
- `app` no tiene FK hacia `ref`: una recarga de `ref` nunca toca ni bloquea el estado de la app. Detalle en [docs/data/postgres.md](../../docs/data/postgres.md).

## Entradas y salidas

Entrada: consultas del controlador y los tools. Salida: filas tipadas.

## Dependencias

Esquema `ref` cargado por [data_pipeline/](../../data_pipeline/README.md).

## Responsable sugerido

Software developer.
