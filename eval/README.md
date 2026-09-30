# eval/

## Propósito

Medir si el sistema funciona y es seguro, comparando baseline y sistema propuesto sobre los mismos casos held-out. Diseño completo: [docs/evaluation.md](../docs/evaluation.md).

| Carpeta | Contenido |
|---|---|
| [harness/](harness/README.md) | Ejecutor de casos contra el sistema y cálculo de métricas. |
| [cases/](cases/README.md) | Casos de evaluación por split. |
| [generator/](generator/README.md) | Generador de reclamos sobre transacciones reales. |
| [judge/](judge/README.md) | Rúbrica y juez LLM, con validación contra humanos. |
| [results/](results/README.md) | Resultados de corridas, experimentos y ablaciones. |

## Entradas y salidas

Entrada: casos + sistema desplegado o local + datos en PostgreSQL. Salida: métricas con numerador y denominador, por idioma, país y segmento.

## Dependencias

[backend/](../backend/README.md), [data_pipeline/](../data_pipeline/README.md), [ml/](../ml/README.md).

## Responsable sugerido

Data scientist.
