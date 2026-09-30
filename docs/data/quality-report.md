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

## Evidencia de demanda para disputas

- **Medido:** en `complaints`, la subcategoría "Cargo no reconocido" tiene 12.297 casos (18,3 % del total medido), con SLA incumplido 20,4 % y 15,4 días promedio de resolución.
- **Advertencia:** por H1, las otras subcategorías tienen porcentajes casi iguales. La evidencia justifica que la demanda existe, no que sea mayor que la de otros motivos.

## Pendientes

- Recalcular todo con el ETL del proyecto y guardar el reporte en `analytics/data_quality/` (ver [analytics/data_quality/README.md](../../analytics/data_quality/README.md)).
- Confirmar con organizadores las discrepancias H7, H8 y H12 (P-19).
