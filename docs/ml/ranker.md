# Ficha: ranker de transacciones

Responsable sugerido: data scientist. Código: [ml/ranker/](../../ml/ranker/README.md). Decisión: [ADR-0002](../decisions/0002-ranker-en-vez-de-llm.md).

## Objetivo

**[Decisión]** Dado lo que el cliente dijo (campos extraídos por el LLM) y las transacciones del cliente en la ventana de búsqueda, ordenar las transacciones para que la disputada quede primera, y dar un score que permita decidir si la candidata es "clara" o hay que aclarar.

Ejemplo: "Tengo un cobro de $120 que no reconozco" → consulta `{monto: 120, moneda: null, fecha: null}` → 40 transacciones del cliente en la ventana → la de 120.00 de hace 5 días debe quedar en el rango 1.

## Etiquetas

**[Decisión]** Juicios de relevancia construidos: en cada reclamo **generado** la transacción objetivo es una transacción real del cliente (relevante = 1) y el resto de transacciones del mismo cliente en la ventana son no relevantes (= 0). Ver [ADR-0003](../decisions/0003-reclamos-generados-sobre-transacciones-reales.md). El set de test incluye además casos escritos a mano ([evaluation.md](../evaluation.md)).

No se usan las quejas del dataset como etiquetas: no se ligan a transacciones (match ~1 %, [quality-report.md](../data/quality-report.md)).

## Features

**[Propuesta]** Por par (consulta, transacción):

| Feature | Descripción |
|---|---|
| Diferencia de monto | Absoluta y relativa entre el monto dicho y `amount`; también contra `amount_usd` completado. |
| Monto redondo / coincidencia exacta | Indicadores. |
| Diferencia de fecha | Días entre la fecha o rango dicho y `transaction_date`; recencia si no se dijo fecha. |
| Similitud de comercio | Similitud de texto entre lo dicho y `merchant_name` / `merchant_category` (puede ser nulo). |
| Coincidencia de canal | Canal dicho vs `channel`. |
| Tipo y estado | `transaction_type`, `transaction_status`. |
| Densidad | Cuántas transacciones del cliente tienen montos parecidos (dificultad de la consulta). |
| Campos presentes | Qué campos dio el cliente (monto, fecha, comercio, canal). |

No se usan `is_fraud` ni `fraud_score` en el ranker (evita mezclar identificación con riesgo). No se usan atributos demográficos.

## Modelos

| Modelo | Rol |
|---|---|
| Baseline determinista | Orden por coincidencia de monto y luego recencia. También es el fallback si el ranker falla. |
| Regresión logística | **[Decisión]** Modelo principal: interpretable y calibrable. |
| LightGBM lambdarank | **[Decisión]** Retador. |
| LLM eligiendo la transacción | Comparación opcional en la ablación ([evaluation.md](../evaluation.md)). |

## Métricas

**[Propuesta]** Siempre con numerador y denominador.

- Top-1 accuracy (acierto en el rango 1), Recall@3, MRR.
- Curva cobertura vs precisión según el umbral τ/δ: qué fracción de casos pasa como "clara" y con qué precisión.
- Desglose por idioma, país, segmento y por cantidad de campos dados por el cliente.

## Umbral

**[Propuesta]** τ (score mínimo del primero) y δ (margen sobre el segundo) se eligen en validación para una precisión objetivo en "candidata clara". Pendiente: precisión objetivo y valores (P-09).

## Splits y leakage

**[Propuesta]**

- Split por **cliente** (ningún cliente en train y test a la vez).
- Plantillas del generador separadas entre train y test cuando sea posible, para no premiar memorizar la redacción.
- El set escrito a mano solo se usa en test.
- Ver [evaluation.md](../evaluation.md).

## Resultados

Pendiente: sin resultados todavía.

## Limitaciones

- Las etiquetas vienen de reclamos generados: miden qué tan bien el ranker recupera la transacción que el generador eligió, no el comportamiento de clientes reales.
- Columnas independientes y uniformes (H1 del reporte de calidad): los patrones del cliente no aportan señal realista.
- `merchant_name` puede ser nulo; la similitud de comercio no siempre aplica.
- Moneda ambigua ("$120"), ver P-17.
