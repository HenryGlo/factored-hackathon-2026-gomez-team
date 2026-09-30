# Preguntas abiertas

Todo lo marcado como "Pendiente" o **[Supuesto]** en la documentación se rastrea aquí. Al resolver una pregunta: anotar la respuesta, la fuente y la fecha, y actualizar los documentos afectados.

Tipos: **Organizadores** (preguntar en Slack/#technical-help o por email), **Equipo** (decidir internamente), **Experimento** (se resuelve con datos).

## Entrega y reglas

| ID | Pregunta | Tipo | Afecta | Supuesto actual |
|---|---|---|---|---|
| P-01 | ¿Fecha, hora y zona horaria límite de entrega? El material solo dice "sprint de 10 días" desde el kickoff del 25 de septiembre. | Organizadores | [submission.md](submission.md), congelamiento del test | Ninguno. |
| P-02 | ¿Duración máxima y formato del video pitch? | Organizadores | [submission.md](submission.md) | Ninguno. |
| P-03 | ~~¿Nombre del equipo para el repo?~~ **Resuelta (2026-09-30):** `gomez-team` → `factored-hackathon-2026-gomez-team`. | Equipo | README, repo | — |
| P-04 | ¿Se puede publicar el dataset o derivados (muestras, fixtures, casos con IDs reales) en un repo público? | Organizadores | [.gitignore](../.gitignore), [data/](../data/README.md), fixtures de test | No se publica nada del dataset. |
| P-05 | ¿Se permite enviar datos del dataset sintético a la API de Claude? El reto prohíbe datos privados o restringidos en solicitudes a modelos externos. | Organizadores | [architecture.md](architecture.md), [data/usage.md](data/usage.md) | Sí, solo campos mínimos (monto, fecha, comercio, canal, estado). |
| P-18 | Integrantes del equipo y asignación de roles. | Equipo | README | Roles definidos, nombres pendientes. |
| P-22 | ¿Hay plantilla o formato requerido para las slides? | Organizadores | [submission.md](submission.md) | Formato libre, 4–6 slides. |

## Datos

| ID | Pregunta | Tipo | Afecta | Supuesto actual |
|---|---|---|---|---|
| P-08 | ¿Qué fecha "hoy" usa la demo para calcular los 60 días de R1? El dataset termina el 2026-06-17. | Equipo | [policies.md](policies.md), `REFERENCE_DATE` | Una fecha fija cercana al final del dataset. |
| P-17 | ¿Cómo tratar la moneda ambigua ("$120")? En los datos, México opera en USD y no hay MXN. | Equipo / Experimento | [ml/ranker.md](ml/ranker.md) | El ranker no exige moneda; compara contra monto local y USD. |
| P-19 | Discrepancias diccionario vs datos: menos filas, 0 % de PK duplicadas, categorías en español. ¿Hay versión nueva del dataset? | Organizadores | [data/quality-report.md](data/quality-report.md), contratos del ETL | Se usan los datos tal como llegan y se documentan las diferencias. |
| P-24 | ¿Qué clientes de demo se usan para portugués? No hay clientes de Brasil. | Equipo | [conversation-flow.md](conversation-flow.md), demo | Cualquier cliente puede escribir en portugués. |
| P-29 | ¿En qué zona horaria están los timestamps? Hay un desfase de ~6 h respecto de la partición. | Organizadores / Experimento | ETL, "el cargo del martes" | **Medido (2026-09-30):** `transaction_date` cae siempre 6–30 h después de `process_date`, igual en los tres países (H16 en [quality-report.md](data/quality-report.md)). Se guarda `TIMESTAMP` sin zona. Las fechas relativas del cliente se resuelven contra `transaction_date`; particiones y `data_as_of` usan `process_date`; el aviso de frescura usa el `transaction_date` más reciente ([data/postgres.md](data/postgres.md#zona-horaria)). Falta confirmar con organizadores. |
| P-30 | ¿Cada cuánto llega una partición nueva y a qué hora se considera completa? El dataset es estático. | Organizadores / Equipo | [data/postgres.md](data/postgres.md#política-de-frescura), aviso de frescura | Incremental diaria a las 07:00 UTC; la partición D se da por completa después de D+1 06:00 (H16); datos viejos si hay más de 26 h sin carga válida. Sin scheduler implementado. |

## Producto y políticas

| ID | Pregunta | Tipo | Afecta | Supuesto actual |
|---|---|---|---|---|
| P-14 | ¿Pueden los mentores validar R1–R6 o hay políticas de referencia? | Organizadores | [policies.md](policies.md) | Son supuestos de práctica del equipo. |
| P-21 | ¿`lock_card` entra en el MVP? | Equipo | [tools-contract.md](tools-contract.md) | Sí, como acción secundaria con confirmación. |
| P-23 | ¿Qué hacer con cargos `Declined` y `Reversed`? | Equipo | [policies.md](policies.md) | Informativo, como `Pending`. |
| P-26 | Un mensaje nuevo en una conversación cerrada, ¿reabre o crea otra? | Equipo | [conversation-flow.md](conversation-flow.md) | Crea una conversación nueva. |
| P-27 | ¿Cuántos intentos de acceso no autorizado disparan escalamiento? | Equipo | [policies.md](policies.md) | Sin definir. |
| P-28 | Regla de prioridad del handoff. | Equipo | [handoff-schema.md](handoff-schema.md) | `alta` para riesgo alto o acceso no autorizado. |

## Modelos y evaluación

| ID | Pregunta | Tipo | Afecta | Supuesto actual |
|---|---|---|---|---|
| P-07 | IDs exactos de modelo (Haiku 4.5, Sonnet 5) y precios para calcular costo. | Equipo | [ADR-0004](decisions/0004-modelo-por-nodo.md), `.env.example` | Configurables por variable de entorno. |
| P-09 | Umbrales τ y δ de "candidata clara" y precisión objetivo. | Experimento | [ml/ranker.md](ml/ranker.md) | Se fijan en dev. |
| P-10 | Tamaño de la ventana de búsqueda de transacciones. | Equipo / Experimento | [tools-contract.md](tools-contract.md) | Más larga que 60 días. |
| P-16 | Tamaño de cada split y del set manual, mezcla por categoría e idioma, número de anotadores y de repeticiones. | Equipo | [evaluation.md](evaluation.md) | Sin definir. |
| P-25 | Cortes de las bandas de riesgo (en especial "alto"). | Experimento | [ml/fraud-risk.md](ml/fraud-risk.md), R6 | Se fijan en validación. |

## Operación y despliegue

| ID | Pregunta | Tipo | Afecta | Supuesto actual |
|---|---|---|---|---|
| P-06 | Plataforma de despliegue, presupuesto, límites de capacidad y de peticiones. ~~¿Se carga todo `transactions` (~4,4 M filas) o un subconjunto de clientes de demo?~~ **Volumen resuelto (2026-09-30):** carga completa por defecto; `--customers-sample N` da un subconjunto determinista, consistente (todos los productos y transacciones de esos clientes) y que cubre los escenarios de prueba ([data/postgres.md](data/postgres.md#subconjunto-de-clientes)). | Equipo | [infra/](../infra/README.md), [data_pipeline/](../data_pipeline/README.md) | Plataforma, presupuesto y límites: sin definir. |
| P-11 | TTL de sesión, de `confirmation_token` y de `Idempotency-Key`. | Equipo | [api-contract.md](api-contract.md) | Configurables por variable de entorno. |
| P-12 | ¿Cómo se autentica la consola del banco? | Equipo | [api-contract.md](api-contract.md) | Sesión de prueba con rol `agent`. |
| P-13 | Supuestos de costo para el ROI (costo por minuto de agente, volumen). | Equipo | [analytics/roi/](../analytics/roi/README.md) | Sin definir; se etiquetará como proyección. |
| P-15 | ¿Movemos `dashboard/`, `viability_check.py`, `viability_report.md` y `dataset_eval.ipynb` a `analytics/`? | Equipo | README, [analytics/](../analytics/README.md) | Se dejan donde están por ahora. |
| P-20 | Política de retención de conversaciones y trazas. | Equipo | [architecture.md](architecture.md), [infra/](../infra/README.md) | Sin definir. |
