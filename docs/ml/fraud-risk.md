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

## Resultados

Pendiente: sin resultados todavía.

## Limitaciones

- Una sola señal; `is_fraud` es sintético.
- Con prevalencia tan baja, la banda "alto" tendrá pocos positivos en test: reportar intervalos o al menos n.
- Transacciones sin `fraud_score` (nulo): riesgo desconocido, ver R6.
