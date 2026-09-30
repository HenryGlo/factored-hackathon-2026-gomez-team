# Inventario de tablas

**[Oficial]** Fuente: *LATAM Bank Complete Data Dictionary* y *LATAM Bank Dataset Summary*, v1.0.0. Filas = cifras del diccionario, no conteos medidos (los conteos medidos están en [quality-report.md](quality-report.md)).

- Países: México, Colombia, Argentina. Monedas: MXN, COP, ARS, USD.
- Rango de fechas: 2023-06-17 a 2026-06-17.
- Texto en español con variantes regionales.
- Tablas de hechos particionadas por fecha (`year=/month=/day=`), en CSV.

## Resumen

| Tabla | Tipo | Filas (diccionario) | Fuente | Partición | PK |
|---|---|---|---|---|---|
| customers | dimensión | 150.000 | Core Banking | monthly_snapshot | `customer_id` |
| products | dimensión | 400.000 | Core Banking | monthly_snapshot | `product_id` |
| branches | dimensión | 350 | Internal | full_snapshot | `branch_id` |
| service_agents | dimensión | 1.200 | Internal | monthly_snapshot | `agent_id` |
| marketing_campaigns | dimensión | 200 | Internal | full_snapshot | `campaign_id` |
| transactions | hechos | 5.000.000 | Core Banking | daily | `transaction_id` |
| call_center_interactions | hechos | 800.000 | Contact Center | daily | `interaction_id` |
| call_transcripts | hechos | 200.000 | Contact Center | daily | `transcript_id` |
| satisfaction_surveys | hechos | 250.000 | Contact Center | daily | `survey_id` |
| digital_events | hechos | 10.000.000 | Digital Banking | daily | `event_id` |
| complaints | hechos | 80.000 | PQR | daily | `complaint_id` |
| campaign_sends | hechos | 2.000.000 | Internal | daily | `send_id` |
| daily_exchange_rates | referencia | 3.000 | Reference | daily | (`date`, `source_currency`, `target_currency`) |

## Columnas de las tablas que usa la solución

Solo se detallan las tablas usadas (ver [usage.md](usage.md)). El resto de columnas está en el diccionario oficial.

### transactions

| Columna | Tipo | Descripción (diccionario) | Restricción |
|---|---|---|---|
| transaction_id | VARCHAR(30) | ID único | PK, NOT NULL |
| transaction_date | TIMESTAMP | Fecha y hora | NOT NULL |
| process_date | DATE | Fecha de proceso (partición) | NOT NULL |
| product_id | VARCHAR(20) | Producto | FK, NOT NULL |
| customer_id | VARCHAR(20) | Cliente | FK, NOT NULL |
| transaction_type | VARCHAR(50) | Deposit, Withdrawal, Transfer, Payment, Purchase, Adjustment | NOT NULL |
| transaction_category | VARCHAR(50) | Food, Transport, Services, Entertainment, Health, Other | — |
| amount | DECIMAL(15,2) | Monto | NOT NULL |
| currency | VARCHAR(3) | Moneda | NOT NULL |
| amount_usd | DECIMAL(15,2) | Monto en USD | — |
| channel | VARCHAR(30) | ATM, Branch, Web, App, POS, Transfer | NOT NULL |
| branch_id | VARCHAR(20) | Sucursal | FK |
| merchant_name | VARCHAR(150) | Comercio (compras) | — |
| merchant_category | VARCHAR(50) | MCC | — |
| transaction_country | VARCHAR(50) | País | NOT NULL |
| transaction_city | VARCHAR(100) | Ciudad | — |
| transaction_status | VARCHAR(20) | Approved, Declined, Pending, Reversed | NOT NULL |
| response_code | VARCHAR(10) | Código de respuesta | — |
| is_fraud | BOOLEAN | Marcada como fraude | NOT NULL |
| fraud_score | DECIMAL(5,2) | Score de riesgo 0–100 | — |
| latitude, longitude | DECIMAL(10,7) | Coordenadas | — |

### customers (columnas usadas)

| Columna | Tipo | Descripción | Restricción |
|---|---|---|---|
| customer_id | VARCHAR(20) | ID único | PK, NOT NULL |
| first_name, last_name | VARCHAR(100) | Nombre | NOT NULL |
| country | VARCHAR(50) | México, Colombia, Argentina | NOT NULL |
| segment | VARCHAR(50) | Premium, Plus, Basic, Student | NOT NULL |
| customer_status | VARCHAR(20) | Active, Inactive, Suspended, Closed | NOT NULL |
| detected_accent | VARCHAR(50) | mexican, colombian, argentine, neutral | — |

No se usan en la solución (y no se envían al LLM): `document_number`, `document_type`, `date_of_birth`, `email`, `mobile_phone`, `landline_phone`, `address`, `postal_code`, `credit_score`, `estimated_monthly_income`, `gender`, `marital_status`, `education_level`, `occupation`.

### products (columnas usadas)

| Columna | Tipo | Descripción | Restricción |
|---|---|---|---|
| product_id | VARCHAR(20) | ID único | PK, NOT NULL |
| customer_id | VARCHAR(20) | Dueño | FK, NOT NULL |
| product_type | VARCHAR(50) | Checking Account, Savings Account, Credit Card, Debit Card, Personal Loan, Mortgage, Investment… | NOT NULL |
| product_number | VARCHAR(30) | Número de cuenta/tarjeta | NOT NULL, UNIQUE |
| currency | VARCHAR(3) | Moneda | NOT NULL |
| product_status | VARCHAR(20) | Active, Blocked, Closed, Suspended | NOT NULL |

`product_number` solo se muestra enmascarado (últimos 4 dígitos). Nota: el reporte de viabilidad encontró los valores de `product_type` en español en los datos (por ejemplo "Tarjeta Crédito"), distinto del diccionario; ver [quality-report.md](quality-report.md).

### complaints (columnas usadas para análisis)

`complaint_id`, `creation_date`, `customer_id`, `case_type` (Complaint, Claim, Request, Suggestion), `category`, `subcategory`, `reception_channel`, `affected_product_id`, `description`, `claimed_amount`, `currency`, `priority`, `status`, `sla_breached`, `resolution_days`, `compensation_granted`.

### call_center_interactions (columnas usadas para análisis)

`interaction_id`, `interaction_date`, `customer_id`, `interaction_type`, `channel`, `contact_reason`, `reason_category`, `duration_seconds`, `wait_time_seconds`, `was_resolved`, `requires_followup`, `was_escalated`.

### call_transcripts (columnas usadas para análisis de idioma)

`transcript_id`, `interaction_id`, `customer_text`, `detected_language`, `detected_intents`.

### daily_exchange_rates

`date`, `source_currency`, `target_currency`, `exchange_rate`, `buy_rate`, `sell_rate`, `source`.

## Relaciones relevantes

**[Oficial]** Del diccionario:

- `transactions.customer_id → customers.customer_id`
- `transactions.product_id → products.product_id`
- `products.customer_id → customers.customer_id`
- `complaints.customer_id → customers.customer_id`
- `complaints.affected_product_id → products.product_id`
- `complaints.origin_interaction_id → call_center_interactions.interaction_id`
- `call_transcripts.interaction_id → call_center_interactions.interaction_id`

**[Oficial]** No existe FK entre `complaints` y `transactions`. El diccionario advierte un pequeño porcentaje de registros huérfanos a propósito.
