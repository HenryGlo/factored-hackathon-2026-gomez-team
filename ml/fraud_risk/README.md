# ml/fraud_risk/

Riesgo de fraude calibrado (prompt 07, bloque 2). Ficha: [docs/ml/fraud-risk.md](../../docs/ml/fraud-risk.md).
Experimento: [docs/experiments/EXP-20261001-risk-calibration.md](../../docs/experiments/EXP-20261001-risk-calibration.md).

- `experiment.py`: **un solo comando** (`python -m ml.fraud_risk.experiment`, lee `data/bank.duckdb`): partición temporal,
  score crudo vs isotónica vs modelo simple para movimientos sin score, umbral por costo esperado, reporte, figura y
  `models/risk/risk-v1.json`.
- `config.toml`: partición, costos (supuestos del equipo), bandas y variables.

El código de ejecución está en `backend/app/ml/risk.py`. No se guarda ningún dato del dataset en el repo.
