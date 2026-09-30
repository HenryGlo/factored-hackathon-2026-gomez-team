# infra/

## Propósito

Despliegue de la app (backend, frontend, PostgreSQL) y operación: trazas, monitoreo, secretos y retención.

## Qué irá aquí

**[Propuesta]**

- Definición de contenedores para backend y frontend, y composición local con PostgreSQL.
- Configuración de la plataforma de despliegue. Pendiente: plataforma y presupuesto (P-06 en [docs/open-questions.md](../docs/open-questions.md)).
- **[Decisión]** Composición local: [docker-compose.yml](docker-compose.yml) con PostgreSQL 17, volumen persistente, healthcheck y roles (`postgres/init/01-roles.sh`). Ver [docs/data/postgres.md](../docs/data/postgres.md).
- Manejo de secretos (API key de Claude, contraseñas y URLs de base de datos) en el gestor de la plataforma, nunca en el repo.
- Pipeline de CI: pruebas del backend y chequeo de enlaces de docs.
- Monitoreo: latencia p50/p95, costo por caso, tasa de escalamiento, errores de tools.
- Documento de operación: límites de capacidad medidos, controles de acceso, retención de datos (P-20) y trabajo pendiente antes de producción.

**[Oficial]** El reto pide explicar límites de capacidad, monitoreo, controles de acceso, retención de datos y el trabajo de despliegue restante, y ser honesto sobre lo que falta.

## Entradas y salidas

Entrada: código de [backend/](../backend/README.md) y [frontend/](../frontend/README.md). Salida: app desplegada con URL pública (requisito de entrega, [docs/submission.md](../docs/submission.md)).

## Dependencias

[backend/](../backend/README.md), [frontend/](../frontend/README.md), [data_pipeline/](../data_pipeline/README.md).

## Responsable sugerido

Software developer.
