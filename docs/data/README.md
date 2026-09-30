# Datos

| Documento | Contenido |
|---|---|
| [inventory.md](inventory.md) | Inventario de las 13 tablas según el diccionario oficial. |
| [quality-report.md](quality-report.md) | Hallazgos de calidad y limitaciones del dataset. |
| [postgres.md](postgres.md) | Esquemas `ref`, `ops` y `app` en PostgreSQL, tipos, zona horaria, cuarentena, índices, carga completa e incremental, linaje. |
| [postgres-schema.md](postgres-schema.md) | Diagramas ER (`ref`, `app`, `ops`) y columnas, generados desde los modelos. |
| [postgres-explain.md](postgres-explain.md) | EXPLAIN ANALYZE de los índices de `ref` (generado). |
| [usage.md](usage.md) | Qué tablas usa la solución y para qué; qué datos son reales, sintéticos o generados por el equipo. |

**[Oficial]** El dataset es **sintético** (LATAM Bank Dataset v1.0.0, generado para el hackathon). No contiene clientes reales. Aun así, el repo es público y no sabemos si el dataset o sus derivados se pueden publicar (P-04, ver [open-questions.md](../open-questions.md)): por eso no se versionan datos, solo documentación. Ver [data/README.md](../../data/README.md).
