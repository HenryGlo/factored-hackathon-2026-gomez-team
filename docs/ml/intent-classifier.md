# Ficha del modelo: clasificador de intención en cascada (`intent-v1`)

Responsable sugerido: data scientist. Código: [ml/intent/](../../ml/intent/README.md).

## Objetivo

**[Decisión]** El nodo de intención lo resuelve Haiku 4.5 ([ADR-0004](../decisions/0004-modelo-por-nodo.md)). Desde el 2026-10-01 existe además una **cascada** (variante `sistema_cascade`): un modelo pequeño atiende los turnos rutinarios y Haiku queda para los difíciles. Esta ficha describe ese modelo; el experimento completo está en [EXP-20261001-intent-cascade](../experiments/EXP-20261001-intent-cascade.md).

Clases (las 9 intenciones del flujo, [conversation-flow.md](../conversation-flow.md)): `cargo_no_reconocido`, `cobro_indebido`, `consulta_movimientos`, `estado_reclamo`, `pregunta_proceso`, `bloquear_tarjeta`, `pedir_humano`, `fuera_de_alcance`, `sin_contenido`. El idioma lo dan las reglas (`detect_language`).

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

## Modelo `intent-v1`

| | |
|---|---|
| Propósito | Decidir la intención de los mensajes rutinarios sin llamar al LLM. No decide nada sobre dinero ni acciones: solo enruta. |
| Tipo | TF-IDF de palabras (1–2) y de caracteres (3–5) + regresión logística (`class_weight=balanced`), calibrada con sigmoide. |
| Artefacto | `models/intent/intent-v1.joblib` (1,4 MB) + `intent-v1.json`: versión, fecha, hash de los datos y del artefacto, τ, configuración. |
| Datos | 187 mensajes reales de dev y dev_paraphrase (plantillas rellenadas con valores inventados) + 989 sintéticos (Sonnet, marcados `synthetic`, solo para entrenar). Nunca el split test. |
| Etiquetas | Intención de Haiku en una corrida donde el caso pasó todos los checkers, revisada a mano por una persona (2 corregidas). Sin doble anotación. |
| Entrenamiento | `python -m ml.intent.train` (un solo comando: validación cruzada por grupos, reporte, figuras y modelo). |
| Umbral | τ = 0,85, elegido por costo esperado en validación ([experimento](../experiments/EXP-20261001-intent-cascade.md)); los costos de error son supuestos del equipo (`ml/intent/config.toml`). |

## Cómo se usa (cascada)

`INTENT_CLASSIFIER=cascade` ([backend/app/ml/intent.py](../../backend/app/ml/intent.py), variante `sistema_cascade`):

1. Va **siempre al LLM** si el mensaje tiene marcas de manipulación, varias intenciones según las reglas o más de 400
   caracteres: el modelo pequeño da una sola intención y no detecta manipulación.
2. Si no, responde el modelo pequeño cuando su probabilidad es ≥ τ; por debajo, decide Haiku.
3. Si el modelo pequeño resolvió una intención que no necesita datos del mensaje (`pedir_humano`, `pregunta_proceso`,
   `estado_reclamo`, `fuera_de_alcance`, `sin_contenido`), el turno tampoco llama a `extract`.
4. Si el archivo del modelo falta, no coincide con su hash o no carga, **todo va a Haiku** y la traza lo dice
   (`cascada.motivo = modelo_no_disponible`).

La traza del paso `intent` guarda `cascada`: ruta (`local` | `llm`), probabilidad, τ, versión del modelo y motivo.
Las guardas, la política R1–R6 y las confirmaciones no cambian: la cascada solo decide por dónde entra el mensaje.

## Resultados

Validación cruzada de 5 folds por grupos sobre los 187 mensajes reales (las paráfrasis de un caso y los mensajes con la misma
plantilla van al mismo fold; los sintéticos solo entrenan):

| Vía | Aciertos | Macro-F1 | Turnos que llegan al LLM |
|---|---|---|---|
| Palabras clave (reglas actuales, tras el bloque 3) | 168/187 (89,8 %) | 0,868 | 0 % |
| TF-IDF + LR calibrado | 180/187 (96,3 %) | 0,928 | 0 % |
| Haiku (solo LLM) | 183/187 (97,9 %) | 0,977 | 100 % |
| **Cascada (τ = 0,85)** | 183/187 (97,9 %) | 0,968 | 26/187 (13,9 %) |

**Este es el número principal del modelo: 183/187 (97,9 %) con el 13,9 % de los turnos al LLM.** Matriz de confusión, Brier/ECE,
curva de cobertura y análisis por idioma: en el [experimento](../experiments/EXP-20261001-intent-cascade.md).

### Harness (contaminado por el entrenamiento: no mide el modelo)

El modelo pequeño se entrenó con los mensajes de dev y dev_paraphrase, los mismos que usa el harness. Estas cifras solo
comprueban que la integración no rompe el flujo ni la seguridad:

| Split | Variante | Pasan todo | Inseguros | Intención por LLM | Costo por caso | Latencia p50 / p95 |
|---|---|---|---|---|---|---|
| dev (81) | `sistema_api` | 81/81 | 0 | 87/87 | $0.0072 | 1,4 s / 4,4 s |
| dev (81) | `sistema_cascade` | 81/81 | 0 | 15/87 | $0.0044 | 1,3 s / 5,2 s |
| dev_paraphrase (96) | `sistema_api` | 96/96 | 0 | 100/100 | $0.0073 | 1,4 s / 4,5 s |
| dev_paraphrase (96) | `sistema_cascade` | 96/96 | 0 | 8/100 | $0.0046 | 1,4 s / 4,8 s |

La medida limpia será el split test escrito a mano, que no se ha usado.

### Por qué la latencia no baja (trabajo futuro)

La cascada evita la llamada de intención, pero en los turnos de disputa `extract` sigue llamando al LLM, y ya corría en paralelo
con la intención: el turno tarda lo mismo. Solo se ahorra tiempo cuando la intención resuelta en local no necesita extracción
(`pedir_humano`, `pregunta_proceso`…), que son pocos turnos, y el p95 lo dominan `explain` y `handoff_summary`.
**Trabajo futuro:** extraer monto, fecha y comercio con reglas o con un modelo pequeño cuando la intención se resuelve en local,
y medirlo con el mismo protocolo (validación cruzada por grupos y, después, el test).

## Limitaciones

- **Pocos datos reales y desbalanceados:** 127 de 187 son `cargo_no_reconocido`; `cobro_indebido`, `estado_reclamo` y
  `sin_contenido` no tienen mensajes reales. Para esas clases el modelo solo vio sintéticos y **no hay validación real**.
- **Etiquetas con sesgo hacia Haiku** (salen de Haiku + revisión de una persona): el acierto de Haiku en dev está inflado.
- **El harness mide sobre mensajes vistos al entrenar:** sus números son optimistas. Falta la medida sobre el split test.
- **La calibración (sigmoide) no mejoró** Brier ni ECE frente al modelo sin calibrar.
- Mensajes generados o escritos por el equipo, no de clientes reales; el portugués no tiene datos de referencia en el dataset.
- No mejora la latencia (ver arriba): el ahorro es de costo.

## Cuándo reentrenar

- Cambia la lista de intenciones o su definición (prompt de intent), o se agregan casos de dev de una intención nueva.
- La métrica `turnos cuya intención llega al LLM` del harness sube de forma sostenida, o aparecen errores de enrutamiento
  en las trazas con `cascada.ruta = local` (feedback 👎, ciclo de mejora).
- Cambia la versión de scikit-learn del backend (el artefacto guarda la versión con la que se entrenó).
- Siempre: subir la versión (`intent-v2`), no sobrescribir `intent-v1`, y volver a correr el experimento completo.

## Estado

**`sistema_api` (todo por Haiku) sigue siendo la configuración de producción.** `sistema_cascade` es una variante evaluada;
se activa con `INTENT_CLASSIFIER=cascade` si la corrida final sobre el split test confirma el resultado.

## Otras implementaciones

- **`KeywordIntentClassifier`** (`keyword@v1`, baseline): reglas es/pt en [keyword_rules.py](../../backend/app/ml/keyword_rules.py).
  También es el respaldo en modo degradado (presupuesto de LLM agotado) y la red de seguridad de `intencion_corregida`.
- **`LLMIntentClassifier`**: el nodo `intent` con Haiku.
