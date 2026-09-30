# ml/fraud_risk/

## Propósito

Calibrar `fraud_score` a una probabilidad de fraude y asignar bandas de riesgo para la regla R6. Ficha: [docs/ml/fraud-risk.md](../../docs/ml/fraud-risk.md).

## Qué irá aquí

**[Propuesta]**

- Split temporal y por cliente de `transactions`.
- Baseline (`fraud_score / 100`) y calibradores (Platt, isotónico).
- Curvas de confiabilidad, AUC, PR-AUC, Brier.
- Selección de cortes de bandas en validación.
- Función de inferencia que el tool `fraud_risk` llama.

## Entradas y salidas

Entrada: `transactions.fraud_score`, `transactions.is_fraud`. Salida: artefacto del calibrador, cortes de bandas y métricas.

## Dependencias

[data_pipeline/](../../data_pipeline/README.md). La consume [backend/tools/](../../backend/tools/README.md).

## Responsable sugerido

Data scientist.
