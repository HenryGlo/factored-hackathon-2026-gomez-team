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

## Modelo `risk-v1` (2026-10-01)

| | |
|---|---|
| Propósito | Dar una señal de **movimiento anómalo** para decidir la ruta y la prioridad de un caso disputado. No declara fraudes ni decide sobre dinero. |
| Tipo | Regresión isotónica de `fraud_score/100` sobre `is_fraud`. Artefacto: `models/risk/risk-v1.json` (24 puntos, con hash; sin datos del dataset). |
| Datos | Los 4,4 M de movimientos del dataset, con partición **temporal**: entrena y valida con lo anterior al 2025-11-12, prueba con lo posterior (885.002 movimientos, 782 fraudes). |
| Etiqueta | `transactions.is_fraud` (columna del diccionario de datos; sintética). |
| Umbral | Costo esperado mínimo en validación, con costos supuestos por el equipo (fraude no priorizado: $100; legítimo enviado a fraude: $5; `ml/fraud_risk/config.toml`). |
| Reproducir | `python -m ml.fraud_risk.experiment` |

## Resultados (prueba, movimientos con score)

| Opción | Enviados con prioridad | Fraudes detectados | Precisión | Costo esperado por 1.000 |
|---|---|---|---|---|
| Score crudo, banda alta anterior (≥ 0,70) | 182/708.054 | 182/620 (29,4 %) | 182/182 | $61,86 |
| Score crudo, umbral por costo (≥ 0,30) | 1.082/708.054 | 446/620 (71,9 %) | 446/1.082 (41,2 %) | $29,07 |
| **Score calibrado, umbral por costo** | 446/708.054 | 446/620 (71,9 %) | 446/446 | **$24,57** |

- Brier: 0,000246 calibrado frente a 0,030270 del score crudo/100 (que no es una probabilidad). PR-AUC igual (0,72): la isotónica no cambia el orden.
- **El calibrador es casi un escalón** en `fraud_score` ≈ 30: por encima, todos los movimientos de entrenamiento eran fraude; por debajo, ~0,03 %. Es una propiedad de este dataset sintético; el corte anterior de 70 dejaba fuera los fraudes entre 30 y 70.
- **Movimientos sin score (20 %): el modelo simple no sirve.** LightGBM con variables del movimiento: PR-AUC 0,0009 frente a una prevalencia de 0,0009 y ROC-AUC 0,51 (azar; corrida determinista). No se integra; siguen en la banda `desconocido` con la regla R6 actual. La falta de score tampoco es señal (0,097 % de fraude con score, 0,101 % sin score).
- Detalle, figura de confiabilidad y curva de costo: [EXP-20261001-risk-calibration](../experiments/EXP-20261001-risk-calibration.md).

## Estado: umbral pendiente de decisión

**Por defecto se usa el score crudo** (`RISK_MODEL=raw_fraud_score`, alto ≥ 0,70) hasta que el líder del equipo elija el corte.
El score calibrado queda disponible con `RISK_MODEL=calibrated`, sin activar.

Tabla para elegir (score crudo, periodo de prueba: 217 días, 708.054 movimientos con score, 620 fraudes; costos supuestos por
el equipo: $100 un fraude no priorizado, $5 un legítimo enviado a fraude):

| Umbral (`fraud_score` ≥) | Alertas por 1.000 movimientos con score | Precisión | Recall | Alertas por día (dataset completo) | Alertas por día (volumen demo, 200 clientes) | Costo esperado por 1.000 |
|---|---|---|---|---|---|---|
| 70 (actual) | 0,257 (182) | 182/182 | 182/620 (29,4 %) | 0,84 | 0,0011 | $61,86 |
| 60 | 0,356 (252) | 252/252 | 252/620 (40,6 %) | 1,16 | 0,0015 | $51,97 |
| 50 | 0,451 (319) | 319/319 | 319/620 (51,5 %) | 1,47 | 0,0020 | $42,51 |
| 40 | 0,544 (385) | 385/385 | 385/620 (62,1 %) | 1,77 | 0,0024 | $33,19 |
| 35 | 0,595 (421) | 421/421 | 421/620 (67,9 %) | 1,94 | 0,0026 | $28,11 |
| 30 | 0,794 (562) | 446/562 (79,4 %) | 446/620 (71,9 %) | 2,59 | 0,0035 | $25,39 |
| calibrado (score > 30) | 0,630 (446) | 446/446 | 446/620 (71,9 %) | 2,06 | 0,0027 | $24,57 |

- Las alertas por día suponen que **todos** los movimientos se evalúan; en el sistema solo se evalúa el movimiento que el cliente
  disputa, así que son una cota superior. Un escalamiento **urgente** exige además que el cliente afirme que no lo hizo: con el
  volumen demo se espera menos de una alerta por semana con cualquier corte.
- Entre 35 y 70 la precisión sigue en 100 % y cada punto que se baja gana recall. En 30 exactos aparecen legítimos (el salto del
  calibrador está justo por encima de 30).
- El modelo simple para movimientos sin score ronda el azar: ROC-AUC 0,5115 en prueba (IC 95 % 0,473–0,553), 0,62 en
  entrenamiento, y un modelo con etiquetas barajadas da lo mismo. No es fuga ni etiqueta invertida (con la misma etiqueta,
  `fraud_score` da 0,85): las variables del movimiento no tienen señal. Detalle en el experimento.

## Uso en la política

`RawFraudScoreRisk` por defecto; `CalibratedFraudScoreRisk` (`calibrated@risk-v1`, [backend/app/ml/risk.py](../../backend/app/ml/risk.py))
disponible con `RISK_MODEL=calibrated`. R6 por bandas ([policies.md](../policies.md#r6--riesgo-por-bandas)): banda alta → escalar
al equipo de fraude y recomendar el bloqueo; **alta + "no lo hice" → prioridad `urgente`** (vale con cualquiera de los dos
modelos). Si el archivo del modelo calibrado falta o no coincide con su hash, se usa el score crudo y la traza lo dice.

## Limitaciones

- **Etiqueta sintética y una sola señal.** El escalón en 30 difícilmente existiría con datos reales.
- **Población distinta:** se midió sobre todos los movimientos, no sobre los que un cliente disputa; ahí la proporción de fraude es mayor y los umbrales deberían recalcularse con casos reales.
- **Costos supuestos** por el equipo; cambian el umbral.
- Una probabilidad de 1,0 es lo que dice el calibrador en este dataset, no una certeza: por eso el handoff dice "señal de movimiento anómalo; no es un fraude confirmado".
- Movimientos sin `fraud_score`: riesgo desconocido (R6).

## Cuándo recalibrar

Al cargar datos nuevos con etiqueta, si cambia la definición o la escala de `fraud_score`, o si los escalamientos a fraude suben
sin que suban los fraudes confirmados. Siempre con versión nueva (`risk-v2`) y el experimento completo.

## Implementación anterior (baseline, sin calibrar)

**[Decisión]** `RawFraudScoreRisk` (`raw_fraud_score@v1`): `probability = fraud_score / 100`; alto si ≥ 0,70, medio si ≥ 0,35. Medido
en el dataset completo (2026-09-30): `fraud_score` ≥ 70 marca 999 transacciones y las 999 tienen `is_fraud` (precisión 100 %,
recall 999/4.316 = 23 %). Sigue disponible como respaldo y como referencia.
