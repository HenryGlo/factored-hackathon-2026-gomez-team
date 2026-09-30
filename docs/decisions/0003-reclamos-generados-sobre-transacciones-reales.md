# ADR-0003: Reclamos generados sobre transacciones reales

Estado: Aceptada · Etiqueta: **[Decisión]**

## Contexto

- Las quejas del dataset no se ligan a transacciones (match ~1 %) y su texto es de plantilla (5 descripciones distintas). Ver [quality-report.md](../data/quality-report.md).
- No hay texto en portugués en el dataset. **[Oficial]** Se deben demostrar interacciones en español y portugués.
- **[Oficial]** Usar etiquetas o juicios de relevancia válidos, evitar leakage y evaluar sobre casos held-out.

## Decisión

1. **Generar** reclamos de entrenamiento y evaluación eligiendo una **transacción real** (sintética del dataset) de un cliente y redactando un reclamo sobre ella en español y portugués, con plantillas, paráfrasis y ruido controlado. La transacción elegida es la etiqueta.
2. Escribir **a mano** un set de test con mensajes realistas y adversarios, en ambos idiomas.
3. Registrar el origen de cada caso (`generado` o `manual`) y la versión del generador.

## Alternativas

| Alternativa | Por qué no |
|---|---|
| Usar las quejas del dataset como etiquetas | No se ligan a transacciones; texto de plantilla. |
| Todo escrito a mano | Muy pocos casos para entrenar el ranker. |
| Todo generado con LLM | Riesgo de evaluar al LLM con su propio estilo; se usa solo para paráfrasis y se contrasta con el set manual. |

## Consecuencias

- Etiquetas limpias y abundantes, pero el ranker aprende la distribución del generador; el set manual mide cuánto se degrada con texto real.
- Split por cliente y por plantilla para evitar leakage ([evaluation.md](../evaluation.md)).
- Limitación a reportar: los casos no vienen de clientes reales.
