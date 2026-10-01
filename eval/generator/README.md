# eval/generator/

## Propósito

Generar reclamos sobre transacciones reales del dataset. Decisión: [ADR-0003](../../docs/decisions/0003-reclamos-generados-sobre-transacciones-reales.md).

## Estado

**[Decisión] Implementado:** [paraphrase.py](paraphrase.py) genera el split de estrés `dev_paraphrase`:

- 2 paráfrasis por caso de dev, con `claude -p --model sonnet` y el prompt [paraphrase_prompt.md](paraphrase_prompt.md).
- `generate` escribe [paraphrase_generated.json](paraphrase_generated.json); `sample` muestra paráfrasis al azar para revisarlas a mano; `build` arma `eval/cases/dev_paraphrase/cases.yaml` sin las descartadas en [paraphrase_review.json](paraphrase_review.json).
- El generador no ve reglas, selectores ni resultados esperados.

## Qué irá aquí (propuesta original)

**[Propuesta]**

- Muestreo de clientes y de una transacción objetivo por caso, estratificado por país, segmento, tipo y estado de transacción.
- Plantillas en español y portugués ("Tengo un cobro de $120 que no reconozco", "Tenho uma cobrança de 120 que não reconheço"), con paráfrasis opcionales.
- Ruido controlado: monto redondeado o aproximado, fecha relativa ("el martes", "hace dos semanas"), comercio parcial o ausente, moneda omitida.
- Casos de dificultad controlada: varias transacciones con monto parecido (ambigüedad), transacción de más de 60 días (R1), estado `Pending` (R2).
- Asignación de split por cliente y por plantilla.
- Versión del generador en cada caso.

## Entradas y salidas

Entrada: esquema `core` en PostgreSQL. Salida: casos en [cases/](../cases/README.md).

## Dependencias

[data_pipeline/](../../data_pipeline/README.md).

## Responsable sugerido

Data scientist.
