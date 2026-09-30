# Ficha: riesgo de fraude calibrado

Responsable sugerido: data scientist. Código: [ml/fraud_risk/](../../ml/fraud_risk/README.md).

## Objetivo

**[Decisión]** Convertir `fraud_score` (0–100) en una probabilidad calibrada de fraude y una banda (`bajo`, `medio`, `alto`) para la regla R6 ([policies.md](../policies.md)): si la banda es `alto`, el caso se escala en vez de crear el reclamo automáticamente.

## Etiquetas

`transactions.is_fraud` del dataset (**[Oficial]**, columna del diccionario). Es una etiqueta sintética.

## Features

`fraud_score`. **[Propuesta]** Opcional como experimento: estado, canal, tipo y monto en USD, solo si mejoran en validación. Nunca atributos demográficos.

## Baseline y modelo

| Variante | Descripción |
|---|---|
| Baseline | `fraud_score / 100` sin calibrar, con corte fijo. |
| Propuesto | Calibración (Platt o isotónica) de `fraud_score` sobre `is_fraud`. |

## Métricas

**[Propuesta]** AUC, PR-AUC (la prevalencia es muy baja), Brier, curva de confiabilidad y, para cada corte de banda: tasa de escalamiento (casos escalados / casos) y recall de fraude (fraudes en banda alta / fraudes).

Referencia medida en exploración (no es resultado del modelo): AUC de `fraud_score` crudo = 0,847; tasa de fraude ~0,09 % en una muestra de 500k ([quality-report.md](../data/quality-report.md)).

## Umbrales

Pendiente: cortes de bandas (P-25). Se eligen en validación balanceando escalamientos innecesarios contra fraude no escalado.

## Splits

**[Propuesta]** Split temporal por `transaction_date` (entrenar en el pasado, evaluar en el futuro), además de separar por cliente.

## Implementación actual (fase 3, sin calibrar)

**[Decisión]** `RawFraudScoreRisk` (`raw_fraud_score@v1`) en [backend/app/ml/risk.py](../../backend/app/ml/risk.py). Detrás de una interfaz y seleccionable en [backend/config/ml.toml](../../backend/config/ml.toml) (override por entorno); cada decisión deja implementación y versión en la traza.

- `probability = fraud_score / 100`, sin calibrar.
- Bandas: alto si ≥ 0,70 (umbral configurable, `RISK_THRESHOLD`), medio si ≥ 0,35, bajo en otro caso, y desconocido si no hay `fraud_score`.
- **Medido en el dataset completo (2026-09-30):** `fraud_score` ≥ 70 marca 999 transacciones y **las 999 tienen `is_fraud`**. Es decir, precisión 100 % y recall 999 / 4.316 = 23 % de los fraudes.
- **Sin score:** 885.157 transacciones no tienen `fraud_score`; su banda es "desconocido" y R6 no escala solo por eso.
- La calibración (Platt o isotónica) y el umbral por costo esperado llegan en el prompt 04 (E2). **Antes de calibrar**, E2 debe revisar si la falta de `fraud_score` se relaciona con `is_fraud`, es decir, si la tasa de fraude es distinta con y sin score. Si lo está, la ausencia es información y se trata como una categoría aparte, no como un valor a imputar.
- **Uso en la política:** R6 por bandas ([policies.md](../policies.md#r6--riesgo-por-bandas)).

## Resultados

Pendiente: sin resultados todavía.

## Limitaciones

- Una sola señal; `is_fraud` es sintético.
- Con prevalencia tan baja, la banda "alto" tendrá pocos positivos en test: reportar intervalos o al menos n.
- Transacciones sin `fraud_score` (nulo): riesgo desconocido, ver R6.
