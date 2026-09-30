# ml/

## Propósito

Componentes de ML: ranker de transacciones, riesgo de fraude calibrado y baselines de intención. Fichas: [docs/ml/](../docs/ml/README.md).

| Carpeta | Ficha |
|---|---|
| [ranker/](ranker/README.md) | [docs/ml/ranker.md](../docs/ml/ranker.md) |
| [fraud_risk/](fraud_risk/README.md) | [docs/ml/fraud-risk.md](../docs/ml/fraud-risk.md) |
| [intent/](intent/README.md) | [docs/ml/intent-classifier.md](../docs/ml/intent-classifier.md) |

**[Propuesta]** Convenciones comunes:

- Cada modelo produce un artefacto versionado (`<modelo>@<fecha>-<commit>`) en `artifacts/`, fuera de git.
- Cada entrenamiento guarda configuración, semilla, datos usados (versión del ETL y split) y métricas en `eval/results/`.
- El backend carga artefactos por ruta desde variables de entorno.

## Entradas y salidas

Entrada: tablas del esquema `core` y casos de [eval/](../eval/README.md). Salida: artefactos de modelo y reportes de métricas.

## Dependencias

[data_pipeline/](../data_pipeline/README.md), [eval/generator/](../eval/generator/README.md).

## Responsable sugerido

Data scientist.
