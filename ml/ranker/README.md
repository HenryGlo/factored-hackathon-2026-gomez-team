# ml/ranker/

## Propósito

Ordenar las transacciones del cliente según qué tan probable es que sean la que disputa. Ficha: [docs/ml/ranker.md](../../docs/ml/ranker.md). Decisión: [ADR-0002](../../docs/decisions/0002-ranker-en-vez-de-llm.md).

## Qué irá aquí

**[Propuesta]**

- Construcción de pares (consulta, transacción) con etiqueta 0/1 a partir de los reclamos generados.
- Cálculo de features (diferencias de monto y fecha, similitud de comercio, canal, estado, densidad).
- Baseline determinista (monto + recencia), también usado como fallback en producción.
- Entrenamiento de regresión logística (principal) y LightGBM lambdarank (retador).
- Selección de umbrales τ/δ en dev.
- Función de inferencia que el tool `search_transactions` llama.

## Entradas y salidas

Entrada: transacciones del esquema `core` + casos `train`/`dev`. Salida: artefacto del modelo, umbrales y métricas (Top-1, Recall@3, MRR, cobertura vs precisión).

## Dependencias

[eval/generator/](../../eval/generator/README.md), [data_pipeline/](../../data_pipeline/README.md). La consume [backend/tools/](../../backend/tools/README.md).

## Responsable sugerido

Data scientist.
