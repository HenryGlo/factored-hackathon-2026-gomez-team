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
| [generated/](generated/README.md) | Flujos generados a escala (combinatoria sobre los casos de dev), guardados en el esquema `eval` de la base local, con muestra estratificada y métricas por caso. Un comando: `scripts/eval_generated.sh`. |

## Estado

**[Decisión] Implementado (fase 6):** `python -m eval.run --split dev --variant <baseline|claude_cli> --repeats N`. Casos en [cases/dev/](cases/dev/cases.yaml) con selectores SQL ([cases/selectors.py](cases/selectors.py)), runner, checkers y métricas en [harness/](harness/), variantes en [variants/](variants/), tests en [tests/](tests/). Detalle: [docs/evaluation.md](../docs/evaluation.md#harness-implementado-fase-6).

Además:

- Variantes `claude_cli` ("todo LLM") y `sistema` (confirm con plantilla, clarify `auto`).
- Tabla comparativa con `python -m eval.compare`.
- Split de estrés `dev_paraphrase` ([generator/](generator/README.md)).
- Kit para el test escrito a mano: [manual/](manual/README.md), `scripts/make_writer_kit.py` y `python -m eval.import_manual`.

## Entradas y salidas

Entrada: casos + sistema desplegado o local + datos en PostgreSQL. Salida: métricas con numerador y denominador, por idioma, país y segmento.

## Dependencias

[backend/](../backend/README.md), [data_pipeline/](../data_pipeline/README.md), [ml/](../ml/README.md).

## Responsable sugerido

Data scientist.
