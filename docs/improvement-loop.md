# Ciclo de mejora con Opus

**[Decisión]** 2026-10-01 (prompt 08, A6). Un ciclo de retroalimentación con **una persona siempre en el medio**:
[scripts/improve_loop.py](../scripts/improve_loop.py) y el workflow manual
[improve-loop.yml](../.github/workflows/improve-loop.yml).

## Qué hace

1. **Recoge** las conversaciones con 👎 (`app.feedback`), las que terminaron en un escalamiento evitable (se agotó la aclaración,
   o el cliente pidió una persona después de tres o más mensajes) y los fallos del harness de los crudos que se le pasen.
2. **Minimiza** antes de analizar: sin IDs, sin números (montos, fechas), sin nombres de comercio ni correos. De las trazas van
   solo el nodo, la intención, las reglas con su resultado y los errores.
3. **Opus analiza** y agrupa patrones. El script escribe `reports/improve-<fecha>.md` con la evidencia de cada patrón (ids y n/N).
4. Por cada patrón accionable **propone casos nuevos para el split dev** (`eval/cases/dev/improve-<fecha>.yaml`, validados contra
   el esquema del harness) y, si aplica, un **diff propuesto** a un prompt de nodo, que queda escrito en el reporte.
5. **Abre un PR en borrador** con el reporte y los casos. La CI corre el harness y el PR trae la tabla antes/después.

## Qué no hace nunca

- **No fusiona.** El script no tiene ningún comando de merge; el PR sale en borrador y lo decide una persona.
- **No toca políticas, guardas, permisos ni checkers.** Solo puede escribir `reports/improve-*` y
  `eval/cases/dev/improve-*.yaml`; cualquier otro cambio en el árbol aborta la apertura del PR (hay un test).
- **No aplica cambios de prompt.** Los deja como propuesta: aceptar uno exige subir la versión del prompt y volver a medir.
- **No usa el split test**, ni para proponer ni para medir.
- **No obedece el feedback.** Los comentarios y mensajes son datos: el prompt de análisis lo dice de forma explícita y, además,
  de la salida de Opus solo se usan campos tipados (ids que deben existir en la evidencia, selectores de una lista cerrada,
  casos que cumplen el esquema). Un comentario que diga "aprueba mi reembolso" o "fusiona el PR" no puede convertirse en una acción.
- **No actualiza `eval/ci_reference.json`:** si los casos propuestos fallan, la CI del PR lo muestra. Ese es el hallazgo; el
  arreglo es otro cambio, revisado por una persona.

## Cómo se corre

```bash
# local, con claude -p (Opus) y una base con feedback (nunca la base "bank" para pruebas: una *_test)
python scripts/improve_loop.py run --database-url "$URL_DE_LA_BASE" --raw eval/results/raw/<corrida>.json --llm claude_cli
# solo el análisis, sin PR
python scripts/improve_loop.py run --database-url "$URL_DE_LA_BASE" --llm claude_cli --no-pr
```

En GitHub: *Actions → Improve loop (manual) → Run workflow* (usa la API de Claude con el secreto `ANTHROPIC_API_KEY` y analiza
los fallos del harness sobre el dataset sintético; el feedback de clientes vive en la base de la aplicación y se analiza en local).

## Límites

- El análisis depende de un LLM: puede agrupar mal o proponer un caso poco útil. Por eso todo es propuesta.
- La minimización quita números y comercios conocidos; un dato personal escrito por el cliente en texto libre podría quedar.
  Antes de usarlo con datos reales hay que revisar la evidencia (`reports/evidence-*.json`, que no se versiona).
- Con pocas conversaciones los patrones son anecdóticos: el reporte siempre da n/N.
