# Ficha: clasificador de intención (baselines)

Responsable sugerido: data scientist. Código: [ml/intent/](../../ml/intent/README.md).

## Objetivo

**[Decisión]** El nodo de intención lo resuelve Haiku 4.5 ([ADR-0004](../decisions/0004-modelo-por-nodo.md)). Esta ficha define los **baselines** contra los que se compara, para justificar el uso del LLM.

Clases **[Propuesta]**: `disputa`, `bloquear_tarjeta`, `estado_reclamo`, `pedir_humano`, `fuera_de_alcance`, `otro`. Más idioma: `es`, `pt`.

Ejemplos:

- "Tengo un cobro de $120 que no reconozco" → `disputa`, `es`
- "Tenho uma cobrança de 120 que não reconheço" → `disputa`, `pt`
- "Quiero hablar con alguien" → `pedir_humano`
- "¿Me dan un crédito?" → `fuera_de_alcance`

## Etiquetas

**[Decisión]** Generadas por el equipo (plantillas y paráfrasis) + set escrito a mano. No se usan `call_transcripts.detected_intents` ni `complaints.description` del dataset: son de plantilla y casi todo es `consulta_general` ([quality-report.md](../data/quality-report.md), H2 y H6).

## Modelos

| Variante | Descripción |
|---|---|
| Reglas | Palabras clave en es/pt. |
| Clásico | TF-IDF (caracteres y palabras) + regresión logística. |
| LLM | Haiku 4.5 con salida estructurada (el que usa el sistema). |

## Métricas

**[Propuesta]** Accuracy y F1 macro, matriz de confusión, desglose por idioma. Prioridad: recall de `pedir_humano` y precisión de `disputa`. Además latencia y costo por mensaje.

## Splits

Por plantilla y por autor: las paráfrasis de una misma plantilla no se reparten entre train y test. El set escrito a mano solo se usa en test.

## Implementación actual (fase 3)

**[Decisión]** Detrás de una interfaz y seleccionable en [backend/config/ml.toml](../../backend/config/ml.toml) (override por entorno); cada decisión deja implementación y versión en la traza.

- **`KeywordIntentClassifier`** (`keyword@v1`, baseline): reglas es/pt en [keyword_rules.py](../../backend/app/ml/keyword_rules.py), para las 8 intenciones de [conversation-flow.md](../conversation-flow.md#intenciones-n1).
  - Incluye negativos difíciles, detección de idioma, `tema` para `fuera_de_alcance` y la bandera de manipulación.
  - Con varias intenciones, `bloquear_tarjeta` va primero.
- **`LLMIntentClassifier`** (`intent@v1`): el nodo `intent` con Haiku.
- El clasificador entrenado y la cascada (clasificador → Haiku si duda) llegan en el prompt 04 (E1).

## Resultados

Pendiente: sin resultados todavía.

## Limitaciones

- Mensajes generados por el equipo, no de clientes reales; el portugués no tiene datos de referencia en el dataset.
- Un clasificador clásico entrenado en plantillas puede parecer muy bueno y fallar con texto real: por eso el set escrito a mano.
