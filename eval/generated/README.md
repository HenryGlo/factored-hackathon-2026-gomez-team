# eval/generated/

Evaluación a escala: miles de flujos de conversación en español y portugués, guardados en el esquema `eval` de la base
local, y una muestra corrida contra el sistema real con las mismas métricas y checkers del harness.

## Para ensayar (un comando)

Con el proyecto levantado (`scripts/dev_up.sh`):

```bash
scripts/eval_generated.sh                        # gratis: genera un lote si no hay y corre 200 flujos con el LLM falso
scripts/eval_generated.sh --sample 1000          # más flujos, sigue gratis
scripts/eval_generated.sh --llm                  # claude -p: consume tu cupo de Claude Code
scripts/eval_generated.sh --api --sample 1000    # API de Claude: ≈ $7 (pide --yes sobre $2)
```

Imprime el reporte (n/N, inseguros, por idioma × categoría, por ruido, por saludo, causas de fallo y las semillas con más
fallos). Sin el dataset del reto usa el sintético. Las corridas con LLM falso miden la parte determinista (reglas,
plantillas, ranker, política); la comprensión de mensajes con errores o paráfrasis necesita un LLM real.

## Cómo se generan los flujos

[generator.py](generator.py) parte de los casos ya escritos y validados de `dev` y `dev_paraphrase` (225 semillas) y varía
solo lo que no debería cambiar el resultado. Lo esperado se copia de la semilla, como en `dev_noisy`:

| Dimensión | Valores |
|---|---|
| Cliente y transacción | fila 0–39 del selector del caso (otro cliente del mismo escenario). Al correr se ajusta a las filas que tenga la base |
| Saludo al inicio | ninguno, "Hola, ", "Buenas tardes, ", "Buen día. " (pt: "Olá, ", "Oi, ", "Boa tarde, "). No en los casos de saludo |
| Ruido | ninguno, errores de tipeo (los de `eval/make_noisy.py`), sin tildes, minúsculas. Nunca toca los marcadores |

Son más de 100.000 combinaciones. `generate --n N` toma N repartidas por igual entre las semillas, sin repetir y con semilla
fija (el mismo comando da el mismo lote).

Opcional, con tokens: `generate --claude K` agrega 2 paráfrasis nuevas de K semillas con el generador de `dev_paraphrase`
(`claude -p`, Sonnet). **No están revisadas a mano**: quedan con `origin = 'parafrasis_claude'` y se pueden correr aparte
(`run --origin parafrasis_claude`). Las paráfrasis de un LLM pueden favorecer a otro LLM.

## Dónde se guardan

Esquema `eval` en la base local (`EVAL_STORE_URL` o, por defecto, `ADMIN_DATABASE_URL`). Lo crea [schema.sql](schema.sql) de
forma idempotente. **No es una migración de Alembic a propósito:** la base desplegada nunca lo tiene, y el código se niega a
escribirlo en un servidor que no sea local (`EVAL_STORE_ALLOW_REMOTE=1` para forzarlo). Los casos corren aparte, en la base
de evaluación `*_test`, que se vacía por caso.

| Tabla | Una fila por |
|---|---|
| `eval.batches` | lote generado (versión del generador, semilla, parámetros, commit) |
| `eval.generated_cases` | flujo: idioma, categoría, selector, semilla de origen, pick, saludo, ruido y el caso completo (`definition`) |
| `eval.runs` | corrida: variante, proveedor LLM, muestra, commit y el resumen de métricas del harness |
| `eval.case_results` | caso corrido: resultado, pasa todo, inseguro, checkers fallidos, causa raíz, costo, latencia, llamadas LLM |
| `eval.v_results` (vista) | resultado con las dimensiones del flujo, para agrupar |

Sin IDs del dataset: los casos usan selectores y marcadores, como los YAML de `eval/cases/`.

Consultas útiles:

```sql
-- tasa de acierto por ruido y por idioma en la última corrida
SELECT noise, language, count(*) n, avg(all_pass::int) ok FROM eval.v_results
WHERE run_id = (SELECT max(run_id) FROM eval.runs) GROUP BY 1, 2 ORDER BY 1, 2;
-- comparar dos variantes sobre los mismos flujos
SELECT variant, count(*), avg(all_pass::int), sum(unsafe::int), avg(cost_usd) FROM eval.v_results GROUP BY 1;
```

## Cuántos correr (y cuánto cuesta)

Generar no cuesta tokens; correr con un LLM sí. Referencia por caso de `eval/results/` (2026-10-01): unos 2,6 turnos y 3
llamadas LLM.

| Muestra | LLM falso | API (`sistema_api`) | `claude -p` |
|---|---|---|---|
| 200 | $0, ≈ 5 min | ≈ $1,50 | ≈ 55 min y cupo (medido: 17 s por flujo, ≈ $0,02 equivalente) |
| 1.000 | $0, ≈ 25 min | ≈ $7,50 | ≈ 5 h y cupo (pide `--yes`) |

- **Inseguros:** con 0 inseguros en n casos, la tasa real es menor que 3/n con 95 % de confianza (300 → < 1 %, 1.000 → < 0,3 %).
- **Tasa de acierto:** ±3 puntos con ~1.000 casos; ±5 con ~400.
- **Por estrato:** la muestra es estratificada por idioma × categoría (12 estratos, mínimo 5 por estrato).

Recomendado: el lote completo (5.000) con LLM falso como regresión, 1.000 con la API para métricas, 200 para iterar. Antes de
correr, `run` estima el costo, pide `--yes` sobre $2 de API o 300 casos con `claude -p`, y hace una llamada de prueba al LLM:
si no responde (por ejemplo, la CLI sin sesión iniciada) no corre. El reporte marca como no válida una corrida con más del
5 % de llamadas LLM fallidas: esa corrida mide las reglas de respaldo, no el modelo.

## Comandos

```bash
.venv/bin/python -m eval.generated generate --n 5000 [--seed S] [--claude K] [--if-missing]
.venv/bin/python -m eval.generated run --variant <eval/variants/*.toml> [--set CLAVE=VALOR] --sample N [--batch B] [--origin O] [--yes]
.venv/bin/python -m eval.generated report [--run N]
.venv/bin/python -m eval.generated status
```

El reporte completo del harness (por caso) queda en `eval/results/generated/` (fuera de git; los datos están en la base).

## Primeras corridas (2026-10-02 y 03, `claude -p`, una repetición)

| Corrida | Flujos | Pasan todo | Inseguros | Nota |
|---|---|---|---|---|
| Combinatorios, muestra de 200 (commit `409d19c`) | 200 | 199/200 | 0/200 | Sin LLM (respaldo por reglas), los mismos flujos: 194/200. Con errores de tipeo: 38/39 frente a 33/39 |
| Paráfrasis nuevas de Claude (commit `809a7d7`) | 188 | 177/188 | 2/188 | Los 2 «inseguros» son paráfrasis que añadieron «no fui yo» a un cargo pendiente: el bot escaló a fraude, que es lo correcto. Sin ellas: 177/186 y 0 inseguros |

Los 9 fallos del bot en las paráfrasis no son inseguros; 5 son la respuesta a «¿Es este el movimiento?» con frases como
«no, ese cargo no lo reconozco, yo no fui» (en un caso el bot cierra con «no hace falta un reclamo»). Las paráfrasis sin
revisar encuentran más fallos que la combinatoria, pero hay que leer cada fallo: algunas cambian el sentido.

## Límites

- Los flujos derivan de casos escritos por el equipo: amplían la cobertura de clientes, saludos y ruido, no inventan
  escenarios nuevos. El test escrito a mano sigue siendo la medida final y no se mezcla con esto.
- Al cambiar de cliente, un caso cuyo texto dependía de un detalle de su transacción original (por ejemplo, la moneda)
  puede fallar sin que el sistema esté mal: la tabla "semillas con más fallos" ayuda a encontrarlos.
