# Uso de datos en la solución

## Origen de cada input

**[Oficial]** El reto pide identificar qué inputs son reales, desidentificados, sintéticos o generados por el equipo.

| Input | Origen | Dónde se usa |
|---|---|---|
| Tablas del LATAM Bank Dataset | **Sintético** (organizadores) | ETL, tools, análisis, modelos |
| Reclamos de entrenamiento y evaluación | **Generado por el equipo** sobre transacciones sintéticas reales del dataset | Ranker, intención, harness |
| Set de test escrito a mano | **Escrito por el equipo** | Evaluación final |
| Casos en portugués | **Generado/escrito por el equipo** | Evaluación multilingüe |
| Políticas R1–R6 | **Supuesto del equipo** | Política |
| Reclamos, handoffs, bloqueos creados en la demo | **Generados por el sistema** (esquema `app`) | Consola, verificación |

## Tablas usadas

**[Decisión]** / **[Propuesta]**

| Tabla | Para qué | Componente |
|---|---|---|
| transactions | Universo de búsqueda; features del ranker; `fraud_score` para riesgo; base del generador de reclamos. | tools, [ml/ranker](../ml/ranker.md), [ml/fraud-risk](../ml/fraud-risk.md), [eval/generator](../../eval/generator/README.md) |
| customers | Clientes de los usuarios demo (`scripts/seed_demo_users.py`); nombre visible, país y segmento para análisis por segmento. | API (`/api/auth/me`), evaluación por segmento |
| products | Tarjetas del cliente (`lock_card`, `get_card_status`); producto de cada transacción. | tools |
| daily_exchange_rates | Completar `amount_usd` y normalizar montos entre monedas. | ETL, ranker |
| complaints | Análisis de demanda (subcategoría "Cargo no reconocido"), SLA y días de resolución como línea base operativa. | [analytics/](../../analytics/README.md) |
| call_center_interactions | Demanda por motivo, duración y FCR como línea base para ROI. | [analytics/](../../analytics/README.md) |
| call_transcripts | Evidencia de cobertura de idioma (sin portugués). | [analytics/](../../analytics/README.md) |
| service_agents | **[Supuesto]** Posible insumo de costo por agente en ROI; sin uso en el sistema (P-13). | [analytics/roi](../../analytics/roi/README.md) |

## Tablas no usadas

`branches`, `marketing_campaigns`, `campaign_sends`, `digital_events`, `satisfaction_surveys`: no aportan al flujo de disputas. `satisfaction_surveys` podría usarse en análisis de satisfacción; queda fuera por ahora.

## Datos que nunca salen del backend

**[Decisión]** No se envían al LLM ni al frontend del cliente: documento de identidad, datos de contacto, dirección, `credit_score`, ingresos, `is_fraud`, coordenadas. Al LLM se le envían solo los campos necesarios para redactar (monto, fecha, comercio, canal, estado). Pendiente confirmar si incluso eso está permitido con la API externa (P-05).
