# eval/judge/

## Propósito

**[Oficial]** Si se usa un modelo para juzgar respuestas, documentar la rúbrica y validar una muestra contra juicios humanos o deterministas.

## Qué irá aquí

**[Propuesta]**

- Rúbrica en Markdown: criterios (explicación fiel a los hechos y a la regla, sin prometer devoluciones, idioma correcto, resumen de handoff sin hechos inventados), escalas y ejemplos.
- Prompt del juez versionado.
- Planilla de anotación humana y cálculo de acuerdo juez-humano (por ejemplo, kappa de Cohen) con n.

## Entradas y salidas

Entrada: salidas del sistema registradas por [harness/](../harness/README.md). Salida: notas por caso y reporte de validación.

## Dependencias

[backend/llm/](../../backend/llm/README.md) (cliente LLM).

## Responsable sugerido

Data scientist; anotación humana por dos miembros del equipo.
