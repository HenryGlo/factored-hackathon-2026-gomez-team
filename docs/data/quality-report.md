# Reporte de calidad de datos

Fuentes:

- **[Oficial]** Retos de calidad anunciados en el diccionario: ~2 % de duplicados, ~5 % de nulos en campos opcionales, llegadas tardías y evolución de esquema.
- **Medido por el equipo** en exploración previa: `viability_report.md` (generado por `viability_check.py`) y el dashboard exploratorio (`dashboard/`, página de inicio). Esas cifras se citan tal cual; se deben recalcular con el ETL oficial del proyecto ([data_pipeline/](../../data_pipeline/README.md)) antes de usarlas en la entrega.

## Hallazgos principales

| # | Hallazgo | Evidencia | Impacto en la solución |
|---|---|---|---|
| H1 | La mayoría de columnas son **independientes y uniformes**. | Las 5 categorías de queja tienen ~18 % cada una; SLA incumplido ~20 % en todas; en el dashboard, la mayoría de pares categóricos tiene V de Cramér < 0,02. | Los análisis de demanda muestran poca diferencia real entre motivos. Hay que decirlo en la justificación del flujo ([ADR-0001](../decisions/0001-workflow-disputas.md)). |
| H2 | El texto de quejas es **de plantilla**. | 5 descripciones distintas en 67.095 quejas ("Queja relacionada con transactions", etc.). | No sirve para entrenar ni evaluar intención ni extracción. |
| H3 | Las quejas **no se ligan a transacciones**. | Match por monto (±2 %) en los 90 días previos: ~1 % (0,010 ponderado); match exacto: 0. | No hay etiquetas de relevancia en el dataset → reclamos generados sobre transacciones reales ([ADR-0003](../decisions/0003-reclamos-generados-sobre-transacciones-reales.md)). |
| H4 | La **mora es aleatoria**. | Mora > 30 d ~10 % en todos los productos de crédito; AUC con `credit_score` solo: 0,513; mejor modelo exploratorio: 0,623 (con leakage temporal, no válido). | Descarta el flujo de crédito ([ADR-0001](../decisions/0001-workflow-disputas.md)). |
| H5 | `fraud_score` vs `is_fraud`: **AUC 0,847**, única señal real encontrada. | Reporte de viabilidad y dashboard. Tasa de fraude ~0,09 % (muestra de 500k). | Se usa como base del riesgo calibrado ([ml/fraud-risk.md](../ml/fraud-risk.md)). Prevalencia muy baja: reportar PR-AUC además de AUC. |
| H6 | **Sin portugués.** | `call_transcripts.detected_language`: 100 % `es`. `detected_intents`: casi todo `consulta_general`. | Los casos en portugués y las etiquetas de intención los genera o escribe el equipo. Limitación a reportar. |
| H7 | Menos filas que el diccionario. | Ejemplos medidos: transactions 4.425.008 (vs 5.000.000), call_center_interactions 686.296 (vs 800.000), complaints 67.095 (vs 80.000). | El ETL registra conteos por archivo y partición; se reportan conteos medidos, no los del diccionario. |
| H8 | 0 % de PK duplicadas (se anunciaban ~2 %). | Reporte de viabilidad y dashboard. Hay duplicados por clave de negocio en algunas tablas (ver dashboard). | El ETL deduplica por PK y además revisa duplicados de contenido. |
| H9 | **Monedas**: no hay transacciones en MXN; clientes de México operan en USD. `amount_usd` vacío en transacciones USD. | Dashboard exploratorio. | "$120" es ambiguo; el ranker no exige moneda; `amount_usd` se completa con `daily_exchange_rates` (P-17). |
| H10 | País escrito como "México" y "Mexico"; en `transaction_country` aparecen otros países. | Dashboard exploratorio. | Normalización en el ETL. |
| H11 | Timestamps desplazados ~6 h respecto de la partición (probable UTC vs hora local). | Dashboard exploratorio. | Definir zona horaria en el contrato de datos; afecta "el cargo del martes" (P-29). |
| H12 | Valores categóricos en español en los datos, en inglés en el diccionario (p. ej. `reason_category = "Transaccional"`, `product_type = "Tarjeta Crédito"`). | Reporte de viabilidad. | El contrato de datos acepta y mapea ambos; preguntar a organizadores (P-19). |
| H13 | `contact_reason` tiene 6 valores, iguales a `reason_category`. | Reporte de viabilidad. | La demanda por motivo de contacto no permite aislar disputas en el call center. |
| H14 | `product_number` no es único: 6 números repetidos en 400.000 productos (el diccionario dice UNIQUE). | ETL, 2026-09-30. | `ref.products.product_number` sin UNIQUE; la identidad es `product_id`. |
| H15 | 0 huérfanos: 0 transacciones con producto inexistente, 0 productos sin cliente y 0 transacciones cuyo cliente no es el dueño del producto (en 4.425.008 / 400.000). | `python -m data_pipeline.run check`, 2026-09-30. | La FK compuesta (`product_id`, `customer_id`) de `ref.transactions` lo garantiza en la base; `ref.rejected_rows` queda vacía. |
| H16 | **`transaction_date` cae 6–30 h DESPUÉS de `process_date`** en las 4.425.008 transacciones, igual en los tres países. Es contraintuitivo: lo normal es procesar después de ocurrir. Es consistente con timestamps en UTC y `process_date` como día hábil en UTC−6, aplicado igual a todos los países (probable regla del generador). | ETL, 2026-09-30; regla de advertencia `transaction_date_offset` en [contracts/transactions.yaml](../../data_pipeline/contracts/transactions.yaml). | (1) Las fechas relativas del cliente ("ayer", "el martes") se resuelven contra `transaction_date`, que es cuando el cliente vio el cargo. (2) Las particiones, la carga incremental y `data_as_of` usan `process_date`. (3) El aviso de frescura al cliente usa el `transaction_date` más reciente cargado (`ops.etl_runs.max_transaction_date`), no `data_as_of`. |

## Resultados de la primera carga completa

**Medido** con el ETL del proyecto ([data/postgres.md](postgres.md)): corrida `run_id = 1` de `ops.etl_runs`, 2026-09-30, PostgreSQL 17.9.

- Código: sobre el commit `838e2d9`, con cambios sin commitear (`git_dirty = true`: el pipeline todavía no estaba commiteado).
- Base DuckDB: sha256 `7c71b35d…`.
- Duración: 117 s de punta a punta (79 s CSV → DuckDB, 38 s DuckDB → PostgreSQL).

### Conteos por capa

Todas las tablas del dataset, en DuckDB:

| Tabla | Archivos | Filas CSV | raw | limpia | Descartadas por dedup PK | Líneas CSV mal formadas |
|---|---|---|---|---|---|---|
| branches | 1 | 350 | 350 | 350 | 0 | 0 |
| call_center_interactions | 1.097 | 686.296 | 686.296 | 686.296 | 0 | 0 |
| call_transcripts | 1.097 | 171.321 | 171.321 | 171.321 | 0 | 0 |
| campaign_sends | 1.083 | 1.746.801 | 1.746.801 | 1.746.801 | 0 | 0 |
| complaints | 1.097 | 67.095 | 67.095 | 67.095 | 0 | 0 |
| customers | 1 | 150.000 | 150.000 | 150.000 | 0 | 0 |
| daily_exchange_rates | 1 | 13.164 | 13.164 | 13.164 | 0 | 0 |
| digital_events | 1.097 | 15.620.994 | 15.620.994 | 15.620.994 | 0 | 0 |
| marketing_campaigns | 1 | 200 | 200 | 200 | 0 | 0 |
| products | 1 | 400.000 | 400.000 | 400.000 | 0 | 0 |
| satisfaction_surveys | 1.097 | 212.759 | 212.759 | 212.759 | 0 | 0 |
| service_agents | 1 | 1.200 | 1.200 | 1.200 | 0 | 0 |
| transactions | 1.097 | 4.425.008 | 4.425.008 | 4.425.008 | 0 | 0 |

- 0 fallos de casteo en la capa limpia (`cast_failures` vacía).
- 0 líneas mal formadas en los 7.671 archivos.
- `campaign_sends` tiene 1.083 particiones diarias, no 1.097: faltan 14 días.

Las 4 tablas servidas, en PostgreSQL `ref`, coinciden en todas las capas (csv = raw = limpia = ref):

| Tabla | ref | Rechazadas | Advertencias de contrato |
|---|---|---|---|
| customers | 150.000 | 0 | — |
| products | 400.000 | 0 | `product_number_unique`: 12 filas (H14) |
| transactions | 4.425.008 | 0 | — (incluida `transaction_date_offset`, H16: 0 fuera del rango de 6–30 h) |
| daily_exchange_rates | 13.164 | 0 | — |

### Contratos e integridad

- **Versiones:** customers v2, products v1, transactions v1, daily_exchange_rates v1 ([contracts/](../../data_pipeline/contracts/README.md)).
- **Reglas bloqueantes:** 0 filas en cuarentena (`ref.rejected_rows` vacía), lejos del umbral de 0,1 %.
- **Huérfanos antes de cargar:** (a) 0 transacciones con producto inexistente; (b) 0 productos sin cliente; (c) 0 transacciones de un cliente que no es el dueño del producto (H15).
- **Consistencia de `app`:** `app_orphans` = 0 en las tres comprobaciones.
- **Frescura:** `data_as_of` = 2026-06-17; `max_transaction_date` = 2026-06-18 05:59:41 (H16).
- **Clientes de demo:** 12 (2 por escenario). Huella de los 150.000 `customer_id` cargados: `ac4449e3…`.

## Evidencia de demanda para disputas

- **Medido:** en `complaints`, la subcategoría "Cargo no reconocido" tiene 12.297 casos (18,3 % del total medido), con SLA incumplido 20,4 % y 15,4 días promedio de resolución.
- **Advertencia:** por H1, las otras subcategorías tienen porcentajes casi iguales. La evidencia justifica que la demanda existe, no que sea mayor que la de otros motivos.

## Pendientes

- H7, H8, H11 y H14–H16 ya están confirmados con el ETL (sección anterior). Recalcular con el ETL los hallazgos que vienen del reporte de viabilidad (H1–H6, H9, H10, H12, H13) y guardar el reporte en `analytics/data_quality/` (ver [analytics/data_quality/README.md](../../analytics/data_quality/README.md)).
- Confirmar con organizadores las discrepancias H7, H8 y H12 (P-19).
