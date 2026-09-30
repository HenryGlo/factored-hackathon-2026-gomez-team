# ml/intent/

## Propósito

Baselines de intención (reglas y clásico) contra los que se compara el nodo de intención con Haiku 4.5. Ficha: [docs/ml/intent-classifier.md](../../docs/ml/intent-classifier.md).

## Qué irá aquí

**[Propuesta]**

- Clasificador por palabras clave en español y portugués (también usado por la variante A de la ablación).
- TF-IDF + regresión logística entrenado con mensajes generados.
- Evaluación comparativa con el nodo LLM sobre el mismo set.

## Entradas y salidas

Entrada: mensajes etiquetados de [eval/cases/](../../eval/cases/README.md). Salida: artefactos y métricas (F1 macro, por clase y por idioma).

## Dependencias

[eval/generator/](../../eval/generator/README.md), [eval/cases/](../../eval/cases/README.md).

## Responsable sugerido

Data scientist.
