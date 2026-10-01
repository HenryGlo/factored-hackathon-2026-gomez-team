# ml/intent/

Clasificador de intención en cascada (prompt 07, bloque 1). Ficha del modelo: [docs/ml/intent-classifier.md](../../docs/ml/intent-classifier.md).
Experimento: [docs/experiments/EXP-20261001-intent-cascade.md](../../docs/experiments/EXP-20261001-intent-cascade.md).

| Archivo | Qué hace |
|---|---|
| `build_labels.py` | Etiquetas de los mensajes de dev (`data/labels.yaml`) y predicciones de Haiku por mensaje (`data/haiku_predictions.json`), desde crudos del harness. |
| `generate_synthetic.py` | Mensajes sintéticos con Sonnet a partir de una plantilla documentada; revisión con reglas (`data/synthetic.jsonl`). |
| `dataset.py` | Filas reales (plantillas rellenadas con valores inventados) y sintéticas; grupos para la validación cruzada sin fuga. |
| `train.py` | **Un solo comando** (`python -m ml.intent.train`): validación cruzada, elección de τ, reporte, figuras y modelo final en `models/intent/`. |
| `config.toml` | Hiperparámetros y supuestos de costo (supuestos del equipo). |
| `harness_results.md` | Resultados del harness y conclusión; `train.py` los añade al reporte. |

Reglas: nunca el split test; nada del dataset en `data/` (los mensajes son plantillas con valores inventados); el código que
el backend necesita en ejecución vive en `backend/app/ml/intent_model.py`, no aquí.
