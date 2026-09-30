# Reporte: datos de entrenamiento y evaluación para el ranker de transacciones

Responsable: data scientist · Fecha: 2026-09-30 · Generador `1.0.0`, alias `1.0.0`, semilla 42.
Código: [ml/ranker/](../../ml/ranker/README.md). Ficha del modelo: [ranker.md](ranker.md).

## Veredicto

**TRIVIAL.** Sí se puede construir un conjunto válido de (reclamo, candidatas, transacción correcta) a partir de `customers` y `transactions`: no tiene leakage, es reproducible y lleva etiquetas por construcción. Pero el problema de ranking que sale de este dataset es casi trivial:

- Un cliente tiene **2,5 transacciones disputables en 60 días** (mediana 2). El 28 % de los reclamos tiene una sola candidata.
- Los montos son uniformes y con centavos: **el monto exacto identifica la transacción en el 100 %** de los casos, y el monto ±10 % en el 90 %.
- Con pistas simuladas con ruido (monto redondeado, ausente o equivocado; comercio parcial; fecha relativa o desplazada), un **RuleRanker escrito a mano logra 98,0 % top-1 y 100 % recall@3** en validación. LightGBM llega a 98,7 %, apenas 0,7 pp más.

**Recomendación:** usar RuleRanker (o LR calibrado si se quiere una probabilidad interpretable) y dedicar el esfuerzo al loop de aclaración, a la extracción de pistas y al set de test escrito a mano. Un modelo aprendido solo aporta algo medible en consultas con distractores (subconjunto hard: +3,3–3,4 pp).

## Qué es real y qué es generado

| Elemento | Origen |
|---|---|
| Transacciones objetivo y candidatas (`transactions`), clientes, montos, fechas, comercios, estados | **Sintético de los organizadores** (LATAM Bank Dataset). Se usan tal cual; no se fabrica ni modifica ninguna transacción. |
| Fecha de sesión del reclamo (0–30 días después de la transacción) | **Generado por el equipo** (supuesto). |
| Pistas del cliente (monto, comercio, fecha, moneda) y su ruido | **Generado por el equipo** con [`generate_queries.py`](../../ml/ranker/generate_queries.py). |
| Mapa comercio → alias, descriptores, frases de categoría y léxico | **Escrito a mano por el equipo**, versionado: [`merchant_aliases.json`](../../ml/ranker/merchant_aliases.json). |
| Etiqueta (qué candidata es la correcta) | **Por construcción**: la transacción real sobre la que se generó la consulta. |
| Set de test final (30–50 reclamos por miembro) | **Escrito a mano por el equipo**. Pendiente; ver [Sesgo principal](#sesgo-principal-y-test-escrito-a-mano). |

`complaints` no se usa: sus descripciones son de plantilla y no se ligan a transacciones ([quality-report.md](../data/quality-report.md), H2–H3).

## Fase 1: ¿el material base es realista? ([01_data_audit.ipynb](../../ml/ranker/01_data_audit.ipynb))

| Aspecto | Hallazgo | Consecuencia para el ranker |
|---|---|---|
| Integridad | 4.425.008 transacciones, 134.515 clientes, 2023-06-17 → 2026-06-18. 0 PK duplicadas, 0 duplicados de negocio, 0 huérfanas. | Base consistente. |
| Comercios | **24 nombres limpios** (p. ej. "Super Ahorro", "Uber"), solo en `Purchase` (95 %). Ninguno con `*` ni dígitos. 4 por categoría; `merchant_name` → `merchant_category` es 1:1 y `merchant_category` = `transaction_category` en el 100 % de los casos. | La similitud de comercio es **trivial**: catálogo corto y sin descriptores reales. Solo aplica al 35 % de las candidatas. |
| Hábitos | Comercios distintos por cliente: 9,29 observado vs 9,29 sorteando al azar. | No hay hábitos que aprender. |
| Montos | Uniformes por tipo y moneda (cuartiles en 0,25/0,50/0,75 del rango); centavos uniformes (sin centavos: 1,0 %; en .99: 1,0 %). 279 pares cliente-monto repetidos en 2,79 M. | **El monto exacto es casi un identificador.** No hay precios redondos. |
| `amount_usd` | Error mediano ~1 % frente a la tasa diaria; solo el 6–9 % cae dentro del rango de fuentes del día. Nulo en USD. | Se usa `amount_usd_filled` y se asume ~1–2 % de error al cruzar monedas. |
| Estados | 92 % Approved, 5 % Declined, 2 % Pending, 1 % Reversed, iguales en todos los tipos. Todos los tipos aparecen en los 6 canales (compras en ATM). | El canal no aporta semántica. |
| Universo disputable | `Purchase` + `Payment` + `Withdrawal` (2.787.043; 63 %). Objetivo: solo Approved/Pending (2.619.413). Declined/Reversed quedan como candidatas. | Se excluyen Deposit (abono), Transfer y Adjustment. |
| Densidad (ventana antes de cada disputable) | 7 d: 1,18 de media (84 % con 1 sola). 30 d: 1,77. **60 d: 2,52; mediana 2; 28,3 % con 1 sola; 9,8 % con ≥ 5.** | Techo de dificultad muy bajo. |
| Geografía | 85,6 % en la ciudad del cliente, 4,6 % en otro país, 9,6 % sin ciudad. | Señal real, útil para riesgo; el cliente rara vez la menciona. |
| Tiempo | Hora plana (CV 0,002). Día de semana con patrón leve (sábado 11 %, domingo 10 %, martes a viernes 16 %). Monto independiente de hora, día, comercio y canal (Kruskal p ≥ 0,08). V de Cramér < 0,05, salvo tipo↔comercio. | Nada aprendible del comportamiento temporal. |

## Fase 2: ¿el problema es difícil? ([02_difficulty.ipynb](../../ml/ranker/02_difficulty.ipynb))

20.001 transacciones objetivo, estratificadas de forma proporcional por país × canal. Sesión = transacción + U(0, 30 d). Candidatas: todas las disputables del cliente en los 60 días previos a la sesión. Pistas **perfectas**, sin ruido.

| Pistas que da el cliente | % con candidata única (la regla resuelve sola) | IC 95 % | % con ≥ 2 empates |
|---|---|---|---|
| Ninguna (toda la ventana) | 27,8 % | [27,2; 28,4] | 72,2 % |
| Monto exacto | **100,0 %** | [100; 100] | 0,0 % |
| Monto ±10 % | 90,2 % | [89,7; 90,6] | 9,8 % |
| Solo comercio/categoría | 82,6 % | [82,1; 83,2] | 17,4 % |
| Solo fecha ±3 d | 85,9 % | [85,4; 86,3] | 14,1 % |
| Monto exacto + comercio | 100,0 % | [100; 100] | 0,0 % |
| Monto ±10 % + comercio | 97,9 % | [97,7; 98,1] | 2,1 % |
| Monto exacto + fecha ±3 d | 100,0 % | [100; 100] | 0,0 % |
| Monto ±10 % + fecha ±3 d | 99,0 % | [98,9; 99,2] | 1,0 % |

Sin pistas, "la más reciente" acierta el 71,3 % y el azar el 54,4 %. La ventaja de la recencia la produce nuestro supuesto de sesión (0–30 días dentro de una ventana de 60). País y canal no cambian la ambigüedad (≤ 1,5 pp). La densidad sí: con 5–7 candidatas, el monto ±10 % deja única solo el 72,8 %. Los retiros son los más ambiguos si solo se dicen como "un retiro" (60,6 % única). Mostrar todo el extracto (también transferencias y depósitos) sube las candidatas a 3,3, pero no cambia la unicidad del monto ±10 % (89,2 %).

**Conclusión:** con monto + comercio casi siempre hay candidata única. Un ranker aprendido aporta poco frente a reglas; el valor está en tolerar pistas vagas o incorrectas y en detectar cuándo preguntar.

## Fase 3: dataset de ranking ([generate_queries.py](../../ml/ranker/generate_queries.py))

Por cada transacción objetivo se genera una consulta con pistas estructuradas (lo que saldría del paso de extracción, no texto libre) y se guardan sus parámetros de ruido (`noise_params`, `template_id`).

| Pista | Modos y probabilidades |
|---|---|
| Monto | exacto 30 % · redondeado a 2 cifras significativas, con flag "como…" 40 % · ausente 20 % · equivocado 10 % (±5–15 %, luego redondeado, dicho **sin** flag de aproximado) |
| Comercio | nombre limpio 25 % · fragmento ("la tienda", "Central") 15 % · frase de categoría ("un súper") 20 % · ausente 30 % · descriptor de extracto ("UBER *TRIP 0412") 10 %. Sin comercio (pagos, retiros, 5 % de compras): categoría, frase de tipo ("un retiro") o descriptor de tipo ("RETIRO ATM"). |
| Fecha | exacta 20 % · relativa ("ayer", "la semana pasada", "el mes pasado"…, convertida a rango por código) 40 % · ausente 25 % · desplazada ±1–2 días 15 % |
| Moneda | presente 40 % · ausente 60 % |
| Sesión | 0–30 días después de la transacción (uniforme) |

- **Resolución de pistas:** el texto del comercio se convierte en categorías y tipo posibles solo con el léxico versionado y el catálogo, nunca mirando la objetivo. Las ambigüedades del español quedan tal cual ("tienda" → Food u Other; "servicio" → Services o Transport).
- **Candidatas:** todas las disputables del cliente (cualquier estado) en [sesión − 60 d, sesión], **sin filtrar por monto**. Como la sesión cae ≤ 30 días después de la objetivo, la objetivo siempre está en la ventana de búsqueda. Lo que queda **fuera del rango de fecha dicho** es el 19,7 % de las consultas con fecha: son exactamente las de fecha desplazada.
- **Distractores naturales** (consultas naturales): con mismo monto exacto, 0,0 %; con monto ±10 %, 9,8 %; con mismo comercio o categoría, 17,5 %; con **ambos**, 2,05 %. Como "ambos" es raro, se añadió un subconjunto **hard**: objetivos elegidos entre las que tienen al menos un distractor con mismo comercio y monto ±10 %. Solo cambia qué transacción se usa como objetivo; no se fabrican transacciones.
- **Features por par** (34, calculadas solo con información de la sesión): diferencia relativa y log-ratio de monto, coincidencia exacta, bandas ±5/10/20 %, flag de aproximado, rango y distancia al mejor monto de la consulta; distancia en días al rango dicho, dentro/fuera del rango, ancho del rango, días desde la transacción hasta la sesión, rango de recencia; similitud de comercio (rapidfuzz sobre texto normalizado), coincidencia de categoría y tipo; tipo, estado, moneda, nº de candidatas y flags de pista ausente. **Excluidas:** `is_fraud`, `fraud_score`, campos posteriores a la sesión y el target.
- **Salida** (`data/processed/ranker/`, fuera de git): `pairs.parquet` en formato largo (`query_id, customer_id, target_tx_id, candidate_tx_id, label, features…, noise_params, split`), `queries.parquet` y `manifest.json` con versión, hashes y controles. Dos corridas dan archivos idénticos byte a byte.

## Fase 4: splits y controles de leakage

Split por **cliente** (hash del `customer_id` con semilla: 70/15/15) **y temporal** por fecha de sesión. Cada consulta cae en el split que corresponde a su cliente solo si su sesión cae en el periodo de ese split; las demás se descartan.

| Split | Sesiones | Consultas natural | Consultas hard | Pares | Clientes | Candidatas/consulta |
|---|---|---|---|---|---|---|
| train | 2023-08-16 → 2025-08-31 | 60.000 | 12.000 | 195.955 | 44.936 | 2,54 / 3,61 |
| val | 2025-09-01 → 2025-12-31 | 10.000 | 679 | 27.853 | 7.584 | 2,54 / 3,64 |
| test | 2026-01-01 → 2026-06-18 | 10.000 | 1.045 | 29.637 | 7.700 | 2,58 / 3,66 |

El subconjunto hard de val y test es chico porque el pool con distractores "ambos" es del ~2 %.

**Split por plantilla:** 16 de las 80 plantillas (monto × comercio × fecha) quedan reservadas (`tpl_holdout`) para medir generalización a combinaciones no vistas.

| Control | Resultado |
|---|---|
| Clientes en más de un split | 0 |
| `candidate_tx_id` de test (o val) presentes en train | 0 |
| Consultas con nº de positivos ≠ 1 | 0 |
| Features prohibidas | ninguna |
| Orden temporal train < val < test | sí |
| Feature más asociada al label | `amt_gap_to_best`, AUC univariada 0,885 (ninguna es el label) |
| Candidata posterior a la sesión | 0 (assert en el generador) |

**Artefacto a declarar:** `Declined` y `Reversed` nunca son objetivo (P(label = 1) = 0) porque el generador solo elige objetivos Approved/Pending. El modelo lo aprende como regla.

### Sesgo principal y test escrito a mano

El generador define la distribución de pistas: mezcla de modos, forma del redondeo, léxico y retraso de la sesión. Los modelos aprenden **esa** distribución, y las métricas de arriba miden qué tan bien se recupera lo que el generador eligió, no cómo hablan los clientes reales. Por eso el test final será de **30–50 reclamos escritos a mano por cada miembro del equipo**, en texto libre y sobre transacciones reales del dataset, con su `target_tx_id`. Se guardarán aparte (`eval/cases/`) antes de ver resultados y no se tocarán durante el desarrollo ([evaluation.md](../evaluation.md), "Congelar el test").

## Fase 5: baselines ([03_baselines.ipynb](../../ml/ranker/03_baselines.ipynb))

Modelos: regla exacta (monto exacto en ventana, orden por fecha), RuleRanker (pesos fijados a priori + softmax), regresión logística por pares (`class_weight="balanced"`, escalado) y LightGBM lambdarank (grupos por `query_id`, early stopping en val). Los empates se rompen al azar con semilla 42. IC 95 % por bootstrap de consultas (B = 1000). Nada se ajustó sobre test.

### Validación, consultas naturales (n = 10.000)

| Modelo | Top-1 % | Recall@3 % | MRR × 100 |
|---|---|---|---|
| Más reciente (sin pistas) | 70,9 [70,0; 71,8] | 98,2 [98,0; 98,5] | 84,1 [83,6; 84,6] |
| 1. Regla exacta | 31,2 [30,3; 32,2] | 31,2 [30,3; 32,2] | 31,2 [30,3; 32,2] |
| 2. RuleRanker | 98,0 [97,7; 98,2] | 100,0 [99,9; 100] | 98,9 [98,8; 99,1] |
| 3. Regresión logística | 98,4 [98,1; 98,6] | 100,0 [99,9; 100] | 99,2 [99,0; 99,3] |
| 4. LightGBM lambdarank | **98,7 [98,5; 98,9]** | 99,9 [99,9; 100] | 99,3 [99,2; 99,4] |

La regla exacta solo devuelve algo en el 31,2 % de las consultas (las que traen monto exacto) y en ellas acierta el 100 %.

### Validación hard (n = 679) y test

| Modelo | Val hard top-1 | Test natural top-1 (n = 10.000) | Test hard top-1 (n = 1.045) |
|---|---|---|---|
| Regla exacta | 30,2 [26,7; 33,6] | 30,1 [29,1; 31,0] | 31,7 [28,8; 34,5] |
| RuleRanker | 93,2 [91,3; 95,1] | 97,8 [97,5; 98,0] | 91,3 [89,6; 92,9] |
| Regresión logística | 93,5 [91,7; 95,1] | 98,2 [97,9; 98,5] | — |
| LightGBM | 96,5 [95,0; 97,8] | 98,5 [98,3; 98,8] | 94,7 [93,4; 96,1] |

En test natural, recall@3 es ≥ 99,9 % para RuleRanker, LR y LightGBM.

### Desglose (validación natural, top-1 %)

| Corte | RuleRanker | LR | LightGBM |
|---|---|---|---|
| Monto exacto (n = 3.118) | 100,0 | 100,0 | 100,0 |
| Monto redondeado (n = 4.009) | 99,8 | 99,8 | 99,9 |
| Monto equivocado (n = 1.002) | 97,1 | 98,1 | 99,0 |
| **Monto ausente** (n = 1.871) | **91,2** | **92,8** | **93,9** |
| Sin ninguna pista (absent\|absent\|absent, n = 132) | — | 69,7 | 72,7 |
| Densidad 1 candidata (n = 2.772) | 100,0 | 100,0 | 100,0 |
| Densidad 3–4 (n = 3.273) | 96,6 | 97,3 | 98,1 |
| Densidad 5–7 (n = 964) | 95,5 | 96,6 | 96,8 |
| Argentina / Colombia / México | 98,0 / 98,3 / 97,7 | 98,4 / 98,8 / 98,2 | 98,6 / 98,9 / 98,6 |
| Moneda presente / ausente | 98,1 / 97,9 | 98,4 / 98,4 | 98,6 / 98,8 |

Los IC de cada celda están en el notebook. País y moneda no cambian nada; el error se concentra en consultas sin monto y con más candidatas.

### Calibración y cobertura

- **Calibración de LR (val natural):** Brier por par 0,0138 crudo → 0,0135 calibrado (sigmoide, CV de 5 folds agrupados por cliente); predecir la prevalencia da 0,239. Por consulta (P(top-1 correcto)), Brier 0,0109 → 0,0102 y ECE 0,009 → 0,006. El 90 % de las consultas tiene P ≈ 1 y acierta siempre; la incertidumbre está en el decil inferior (predicho 0,78, observado 0,84).
- **Cobertura (resolver sin preguntar si confianza ≥ τ y margen ≥ δ, elegidos en val):** con τ = 0 los tres modelos ya superan el 95 % y el 98 % de precisión con el 100 % de cobertura. Para 99 % de precisión, las coberturas son: RuleRanker 98,0 % (τ 0,47, δ 0,1), LR calibrado 98,9 % (τ 0,52) y LightGBM 99,5 % (τ 0,49). En test, el umbral de LR elegido para 95 % da 98,2 % de precisión con 100 % de cobertura.
- **Generalización:** en plantillas no vistas no hay degradación (LR 98,9 %, LightGBM 99,1–99,3 %). Entrenar sin ningún monto equivocado baja el top-1 en esos casos de 99,0 % a 97,4 % (LightGBM).
- **Importancia (LightGBM):** distancia de monto al mejor candidato 49,5 %, distancia a la fecha dicha 16,5 %, recencia 10,9 %. El comercio aporta ~2 %.

## Limitaciones

1. **Las etiquetas vienen del generador.** Miden la recuperación de la transacción que el generador eligió con la mezcla de ruido que definimos. Otra mezcla (más pistas ausentes, sesiones más tardías) cambia los números.
2. **La recencia es en parte un artefacto:** la sesión uniforme de 0–30 días hace que la objetivo sea de las más recientes (71 % sin pistas). Con clientes que reclaman más tarde, la recencia pierde valor.
3. **Datos sintéticos poco realistas:** montos uniformes con centavos (sin montos repetidos como suscripciones de 9,99), 24 comercios limpios, canal independiente del tipo, sin hábitos por cliente. Con datos reales (cargos recurrentes del mismo monto y comercio) la ambigüedad sería mucho mayor y el ranker aprendido más valioso.
4. **Estado:** se asume que el estado visible en la sesión es el final del dataset (no hay historial de estados). Declined/Reversed nunca son objetivo por construcción.
5. **Moneda:** los clientes de México operan en USD en el dataset (H9); "$120" es ambiguo y el ranker no exige moneda.
6. **Zona horaria:** los timestamps están desplazados ~6 h (H11). "Ayer" y "el martes" se resuelven sobre la fecha del timestamp tal cual.
7. **El subconjunto hard de val y test es chico** (679 y 1.045): sus IC son anchos.
8. **Las pistas son estructuradas:** el error del paso de extracción con LLM no está modelado. El test escrito a mano sí lo medirá.

## Criterios de decisión

| Criterio | Umbral | Medido | ¿Se cumple? |
|---|---|---|---|
| **VIABLE**: ambigüedad natural suficiente | Fracción relevante con ≥ 2 candidatas plausibles | 72 % con ≥ 2 candidatas en la ventana, pero solo 9,8 % empatadas con monto ±10 % y 2,1 % con monto ±10 % + comercio | Débil |
| **VIABLE**: aprendidos > regla exacta con IC que no se solapan (top-1 o recall@3) | IC disjuntos | 98,7 % [98,5; 98,9] frente a 31,2 % [30,3; 32,2] | Sí, pero solo porque la regla exacta no tolera montos aproximados. Frente a RuleRanker: +0,7 pp natural, +3,3 pp hard. |
| **VIABLE**: curva de cobertura con umbral útil | Umbral que cambie la decisión | Con τ = 0 la precisión ya es 98 %; para 99 % solo se pregunta en 0,5–2 % de los casos | No |
| **TRIVIAL**: la regla exacta > 95 % top-1 con las pistas típicas | > 95 % | 100 % cuando el cliente da el monto exacto. Una regla que tolera pistas vagas (RuleRanker) da 98,0 % con la mezcla simulada. | **Sí** (en espíritu) |
| **INSUFICIENTE**: ninguna pista separa candidatas | — | El monto separa casi todo | No |

**Veredicto: TRIVIAL.** El dataset es válido para **evaluar** el ranker y fijar el umbral de aclaración, pero no justifica un modelo aprendido complejo. Recomendaciones:

1. Usar **RuleRanker** en producción (sin entrenamiento, interpretable, 98 % top-1) o **LR calibrado** si se quiere una probabilidad para el umbral. LightGBM solo aporta en consultas con distractores.
2. Dedicar el esfuerzo al **loop de aclaración**: las consultas sin monto (91–94 % top-1) y sin ninguna pista (~73 %) son donde preguntar "¿recuerdas el monto?" cambia el resultado.
3. Invertir en la **extracción de pistas** y en el **set escrito a mano**: el riesgo real está en el paso de texto libre → pistas, que este dataset no mide.
4. Si se quiere mostrar el valor de un modelo aprendido, reportar el subconjunto hard y declarar que la ambigüedad del dataset sintético es menor que la de un extracto real.

## Reproducir

```bash
# base DuckDB: BANK_DUCKDB=/ruta/bank.duckdb (por defecto dashboard/data/bank.duckdb)
.venv/bin/pip install duckdb pandas pyarrow scikit-learn lightgbm rapidfuzz scipy matplotlib nbconvert ipykernel
.venv/bin/python ml/ranker/generate_queries.py          # ~10 s; escribe data/processed/ranker/
cd ml/ranker && ../../.venv/bin/jupyter nbconvert --to notebook --execute --inplace 01_data_audit.ipynb 02_difficulty.ipynb 03_baselines.ipynb
```
