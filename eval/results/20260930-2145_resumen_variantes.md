# Resumen: baseline vs todo LLM vs sistema · 2026-09-30

Todas las cifras salen de las corridas de abajo, con tablas generadas por `python -m eval.compare`:

- dev: [20260930-2139_comparacion_dev.md](20260930-2139_comparacion_dev.md)
- dev_paraphrase: [20260930-2139_comparacion_dev_paraphrase.md](20260930-2139_comparacion_dev_paraphrase.md)

Los reportes de cada corrida están en esta carpeta; los crudos, en `raw/` (fuera de git). El código estaba sin commit (rama `feat/backend-harness` sobre `a2f0a1e`; `claude_cli` sobre `54a0e33`).

## Variantes

| Variante | Intención y extracción | confirm | clarify |
|---|---|---|---|
| `baseline` | palabras clave + cliente fake | plantilla | plantilla |
| `claude_cli` ("todo LLM") | `claude -p` (haiku) | LLM | LLM |
| `sistema` | `claude -p` (haiku) | plantilla | `auto`: plantilla para elegir entre candidatas; LLM para tipo de problema, pedir más datos y respuestas que no encajan |

`explain` y `handoff_summary` usan `claude -p` (sonnet) en `claude_cli` y en `sistema`. Las tres variantes usan RuleRanker y `fraud_score/100`.

- **Diferencias de código entre corridas:**
  - `claude_cli` se corrió antes de existir `CONFIRM_MODE` y `CLARIFY_MODE`. Su comportamiento equivale a `llm`/`llm`, salvo que "no encontré cargos" y "dame más datos" eran texto fijo del código.
  - `sin_exito_sin_verificar` se re-evaluó en todas con el checker actual. El anterior marcaba como falso éxito "ya existe una reclamação registrada": tres casos de `claude_cli`, todos `dev-reclamo-existente-pt`.

## Split dev (50 casos; optimista: escritos conociendo el sistema)

| Variante | Rep. | Resolución segura | Fallan | Inseguros | Latencia/turno p50 / p95 | Costo por caso |
|---|---|---|---|---|---|---|
| baseline | 1 | 35/35 | 0/50 | 0/50 | 16 ms / 23 ms | $0 |
| todo LLM | 3 | 105/105 | 0/150 | 0/150 | 7.5 s / 19.8 s | $0.0218 |
| sistema | 3 | 105/105 | 0/150 | 0/150 | 3.9 s / 13.0 s | $0.0151 |

**Latencia por turno, LLM vs resto.** Medida en el entorno de desarrollo: portátil, `claude -p` local con arranque de proceso en cada llamada. No es una medida de producción.

| Variante | LLM p50 / p95 | Resto p50 / p95 | Turnos con LLM |
|---|---|---|---|
| todo LLM | 7.4 s / 19.7 s | 50 ms / 79 ms | 357/399 |
| sistema | 3.9 s / 12.9 s | 43 ms / 59 ms | 270/399 |

Las plantillas de confirm y de elegir candidatas no cambian ninguna métrica de calidad en dev. Bajan la latencia mediana a la mitad y el costo por caso un 31 %.

Aclaraciones de `sistema` en dev: 11 por plantilla (elegir candidatas), 6 por LLM para pedir más datos y 1 por LLM para el tipo de problema.

## Split dev_paraphrase (98 paráfrasis; desarrollo, no medida final)

| Variante | Rep. | Resolución segura | Pasan todo | Inseguros | Escalamientos correctos | Latencia/turno p50 / p95 | Costo por caso |
|---|---|---|---|---|---|---|---|
| baseline | 1 | 51/70 (72.9 %) | 71/98 | 0/98 | 14/20 | 15 ms / 21 ms | $0 |
| sistema | 1 | 66/70 (94.3 %) | 92/98 | 0/98 | 18/20 | 5.1 s / 10.4 s | $0.0153 |

**[Supuesto] Sesgo:** las paráfrasis las generó un LLM (sonnet). Pueden favorecer al sistema que usa otro LLM. Esta diferencia no reemplaza al test escrito a mano. `todo LLM` no se corrió sobre este split.

### Fallos clasificados (causa raíz, revisión manual de las trazas)

**baseline**: 27 casos fallidos.

- 20 por comprensión: la intención por palabras clave no reconoce el mensaje coloquial y lo cierra como fuera de alcance, o no extrae el dato.
- 3 de política: aviso o resultado distinto por la misma causa.
- 2 de aclaración.
- 2 de escalamiento: no llega a escalar.

Los 409 de los checkers son consecuencia (conversación ya cerrada), no fallos de tool.

**sistema**: 6 casos fallidos, ninguno inseguro.

| Causa | Casos | Detalle |
|---|---|---|
| **Confirmación del movimiento no entendida** (código, no LLM) | 5: `dev-claro-pt-p1`, `dev-sin-monto-pt-p2`, `dev-fecha-equivocada-es-p1`, `dev-riesgo-alto-pt-p1`, `dev-fallo-tool-es-p2` | El "sí" del cliente vino como "é sim, é essa mesmo", "simm", "sip", "sii". La regex `YES` de `engine.py` no los acepta. El sistema vuelve a preguntar y el guion se corta. El clasificador automático los reparte entre política, aclaración y escalamiento según el resultado esperado; la causa real es una sola. |
| **Movimiento propuesto equivocado sin aclarar** | 1: `dev-empate-sin-separar-es-p2` | La paráfrasis agrega "ayer estaba haciendo trámites… y revisando la app". La extracción lo toma como fecha del cargo y propone el otro movimiento de monto parecido, sin preguntar. No es inseguro (el cliente aún debe confirmar), pero es el error que la aclaración debe evitar. Es discutible si la paráfrasis cambió el significado: no estaba entre las 10 revisadas. |

Siguiente paso sugerido (no aplicado): reconocer el "sí" con variantes de tipeo y muletillas ("sip", "sii", "simm", "é sim", "isso aí"). Se puede hacer con una regex más tolerante o con el LLM solo cuando la regex no decide. Hay que medirlo de nuevo en dev y en dev_paraphrase.
