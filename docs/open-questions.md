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
| P-05 | ¿Se permite enviar datos del dataset sintético a la API de Claude? El reto prohíbe datos privados o restringidos en solicitudes a modelos externos. | Organizadores | [llm-data.md](llm-data.md), [architecture.md](architecture.md) | **Abierta; el equipo pregunta.** Supuesto aplicado (2026-09-30): minimización por nodo. intent y extract solo reciben el texto del cliente. Candidatas con referencias opacas y solo comercio, monto, moneda, fecha y estado. confirm redacta con marcadores. Nunca salen `customer_id`, nombres, `product_number` ni IDs internos. El CLI agrega el email de la cuenta de Claude (no se puede quitar sin `--bare`). |
| P-18 | Integrantes del equipo y asignación de roles. | Equipo | README | Roles definidos, nombres pendientes. |
| P-22 | ¿Hay plantilla o formato requerido para las slides? | Organizadores | [submission.md](submission.md) | Formato libre, 4–6 slides. |

## Datos

| ID | Pregunta | Tipo | Afecta | Supuesto actual |
|---|---|---|---|---|
| P-08 | ¿Qué fecha "hoy" usa la demo para calcular los 60 días de R1? El dataset termina el 2026-06-17. | Equipo | [policies.md](policies.md), `REFERENCE_DATE` | **Implementado (2026-09-30):** `REFERENCE_DATE` si está definida; si no, la fecha del último `transaction_date` cargado (hoy 2026-06-18). Se fija por conversación (`app.conversations.session_date`); el harness la simula por caso. |
| P-17 | ¿Cómo tratar la moneda ambigua ("$120")? En los datos, México opera en USD y no hay MXN. | Equipo / Experimento | [ml/ranker.md](ml/ranker.md) | El ranker no exige moneda; compara contra monto local y USD. |
| P-19 | Discrepancias diccionario vs datos: menos filas, 0 % de PK duplicadas, categorías en español. ¿Hay versión nueva del dataset? | Organizadores | [data/quality-report.md](data/quality-report.md), contratos del ETL | Se usan los datos tal como llegan y se documentan las diferencias. |
| P-24 | ¿Qué clientes de demo se usan para portugués? No hay clientes de Brasil. | Equipo | [conversation-flow.md](conversation-flow.md), demo | Cualquier cliente puede escribir en portugués. |
| P-29 | ¿En qué zona horaria están los timestamps? Hay un desfase de ~6 h respecto de la partición. | Organizadores / Experimento | ETL, "el cargo del martes" | **Medido (2026-09-30):** `transaction_date` cae siempre 6–30 h después de `process_date`, igual en los tres países (H16 en [quality-report.md](data/quality-report.md)). Se guarda `TIMESTAMP` sin zona. Las fechas relativas del cliente se resuelven contra `transaction_date`; particiones y `data_as_of` usan `process_date`; el aviso de frescura usa el `transaction_date` más reciente ([data/postgres.md](data/postgres.md#zona-horaria)). Falta confirmar con organizadores. |
| P-30 | ¿Cada cuánto llega una partición nueva y a qué hora se considera completa? El dataset es estático. | Organizadores / Equipo | [data/postgres.md](data/postgres.md#política-de-frescura), aviso de frescura | Incremental diaria a las 07:00 UTC; la partición D se da por completa después de D+1 06:00 (H16); datos viejos si hay más de 26 h sin carga válida. Sin scheduler implementado. |

## Producto y políticas

| ID | Pregunta | Tipo | Afecta | Supuesto actual |
|---|---|---|---|---|
| P-14 | ¿Pueden los mentores validar R1–R6 o hay políticas de referencia? | Organizadores | [policies.md](policies.md) | Son supuestos de práctica del equipo. |
| P-21 | ~~¿`lock_card` entra en el MVP?~~ **Resuelta (2026-09-30):** sí, como intención propia `bloquear_tarjeta` (autoservicio) y como recomendación u oferta en R6. | Equipo | [tools-contract.md](tools-contract.md) | — |
| P-23 | ¿Qué hacer con cargos `Declined` y `Reversed`? | Equipo | [policies.md](policies.md) | Implementado como supuesto: `informar` (R2, `no_active_charge`), igual que `Pending`. |
| P-26 | Un mensaje nuevo en una conversación cerrada, ¿reabre o crea otra? | Equipo | [conversation-flow.md](conversation-flow.md) | **Resuelto 2026-10-01:** los resultados no cierran; solo la despedida o 15 min de inactividad. Un mensaje a una conversación cerrada → `409` en la API y el frontend crea una nueva **enlazada** (`previous_conversation_id`) con el cargo en foco. |
| P-27 | ¿Cuántos intentos de acceso no autorizado disparan escalamiento? | Equipo | [policies.md](policies.md) | Sin definir. |
| P-28 | Regla de prioridad del handoff. | Equipo | [handoff-schema.md](handoff-schema.md) | `alta` para riesgo alto o acceso no autorizado. |
| P-31 | El estado "Aprobado/Aprovado" de un movimiento, ¿puede aparecer en textos del asistente? La guarda R5 rechaza cualquier texto con "aprobado". | Equipo | [policies.md](policies.md) (R5), [llm-data.md](llm-data.md), [api-contract.md](api-contract.md) (`status_label`) | **Resuelto 2026-10-01:** el LLM nunca escribe la palabra del estado. Usa el marcador `{estado}` (o `{estado_c1}`…) y el código lo rellena **después** de la guarda R5, con la misma etiqueta traducida del bloque. La guarda sigue estricta con el texto libre: un "aprobado" escrito por el LLM se rechaza. Bloque y texto dicen lo mismo. |
| P-32 | ¿Qué textos aprobados usa el asistente para explicar el proceso? Por ejemplo: si devuelven el dinero, plazos de revisión, cancelar un reclamo, tarjeta bloqueada. | Organizadores / Equipo | [backend/knowledge/faq.yaml](../backend/knowledge/faq.yaml), [conversation-flow.md](conversation-flow.md#preguntas-sobre-el-proceso) | **[Supuesto]** 12 respuestas del equipo, marcadas `supuesto_del_equipo`. Plazo de revisión "hasta 15 días hábiles" sin fuente oficial. Ninguna promete devoluciones (test). |

## Modelos y evaluación

| ID | Pregunta | Tipo | Afecta | Supuesto actual |
|---|---|---|---|---|
| P-07 | IDs exactos de modelo (Haiku 4.5, Sonnet 5) y precios para calcular costo. | Equipo | [ADR-0004](decisions/0004-modelo-por-nodo.md), [backend/config/llm.toml](../backend/config/llm.toml) | **IDs medidos (2026-09-30):** con `claude -p`, `haiku` → `claude-haiku-4-5-20251001` y `sonnet` → `claude-sonnet-5-5`. El costo es el `total_cost_usd` que informa el CLI (precio de lista). Precios del despliegue con la API: pendiente. |
| P-09 | Umbrales τ y δ de "candidata clara" y precisión objetivo. | Experimento | [ml/ranker.md](ml/ranker.md) | Valores iniciales en [backend/config/ml.toml](../backend/config/ml.toml): τ = 0,60, δ = 0,20, tolerancia de monto ±10 %. Se ajustan con el split dev del harness (fase 6). |
| P-10 | Tamaño de la ventana de búsqueda de transacciones. | Equipo / Experimento | [tools-contract.md](tools-contract.md) | 120 días (`search_window_days`), más que los 60 de R1. Se revisa con el harness. |
| P-16 | Tamaño de cada split y del set manual, mezcla por categoría e idioma, número de anotadores y de repeticiones. | Equipo | [evaluation.md](evaluation.md) | **Dev (2026-09-30):** 50 casos (27 es / 23 pt), 3 repeticiones para la variante con LLM. Test: pendiente, escrito a mano (30–50 por persona). |
| P-25 | Cortes de las bandas de riesgo (en especial "alto"). | Experimento | [ml/fraud-risk.md](ml/fraud-risk.md), [policies.md](policies.md#r6--riesgo-por-bandas) | **Supuesto aplicado (2026-09-30):** alto ≥ 0,70 (escala al equipo de fraude y recomienda bloquear); medio ≥ 0,35 (ofrece bloqueo); desconocido sin `fraud_score` no cuenta como bajo (ofrece bloqueo y escala si el monto es > 500 USD). Con alto ≥ 0,70: 999/999 fraude, 23 % de recall. Definitivo tras la calibración (prompt 04, E2), que antes debe revisar si la falta de score se relaciona con `is_fraud`. |

## Operación y despliegue

| ID | Pregunta | Tipo | Afecta | Supuesto actual |
|---|---|---|---|---|
| P-06 | Plataforma de despliegue, presupuesto, límites de capacidad y de peticiones. ~~¿Se carga todo `transactions` (~4,4 M filas) o un subconjunto de clientes de demo?~~ **Volumen resuelto (2026-09-30):** carga completa por defecto; `--customers-sample N` da un subconjunto determinista, consistente (todos los productos y transacciones de esos clientes) y que cubre los escenarios de prueba ([data/postgres.md](data/postgres.md#subconjunto-de-clientes)). | Equipo | [infra/](../infra/README.md), [data_pipeline/](../data_pipeline/README.md), [security.md](security.md) | **Límites de peticiones y presupuesto de LLM: implementados (2026-10-01, [security.md](security.md)).** Plataforma: pendiente (fase 5 del prompt 05). |
| P-11 | TTL de sesión, de `confirmation_token` y de `Idempotency-Key`. | Equipo | [api-contract.md](api-contract.md) | **Sesión resuelta (2026-09-30):** 30 min de inactividad y 12 h máximo (`SESSION_IDLE_MINUTES`, `SESSION_MAX_HOURS`). Token de confirmación e Idempotency-Key: configurables, valor pendiente. |
| P-12 | ~~¿Cómo se autentica la consola del banco?~~ **Resuelta (2026-09-30):** login con usuario y contraseña, rol `analyst` (no `agent`, para no confundirlo con el agente de IA), lecturas con el usuario de base de datos de solo lectura ([api-contract.md](api-contract.md#autenticación)). | Equipo | [api-contract.md](api-contract.md) | — |
| P-13 | Supuestos de costo para el ROI (costo por minuto de agente, volumen). | Equipo | [analytics/roi/](../analytics/roi/README.md) | Sin definir; se etiquetará como proyección. |
| P-15 | ¿Movemos `dashboard/`, `viability_check.py`, `viability_report.md` y `dataset_eval.ipynb` a `analytics/`? | Equipo | README, [analytics/](../analytics/README.md) | Se dejan donde están por ahora. |
| P-20 | Política de retención de conversaciones y trazas. | Equipo | [architecture.md](architecture.md), [infra/](../infra/README.md) | Sin definir. |
