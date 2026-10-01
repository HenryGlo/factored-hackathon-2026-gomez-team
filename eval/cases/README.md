# eval/cases/

## Propósito

Casos de evaluación versionados. Taxonomía y splits: [docs/evaluation.md](../../docs/evaluation.md). Cómo agregar uno: [CONTRIBUTING.md](../../CONTRIBUTING.md).

## Estado

**[Decisión] Implementado:** formato YAML validado ([schema.py](schema.py)) con selectores SQL deterministas ([selectors.py](selectors.py)) en vez de IDs del dataset (P-04). `dev/`: 60 casos. `dev_paraphrase/`: 98 paráfrasis de dev, generadas por LLM (split de estrés, no medida final). `test/`: lo escribe el equipo a mano con el kit de [../manual/](../manual/README.md).

## Qué irá aquí

**[Propuesta]** Subcarpetas por split (`train/`, `dev/`, `test/`), con casos en JSON Lines. Campos de cada caso:

| Campo | Descripción |
|---|---|
| `case_id` | Identificador. |
| `split` | `train`, `dev`, `test`. |
| `categoria` | `normal`, `ambiguo`, `requiere_humano`, `adversario`. |
| `subtipo` | Ver taxonomía. |
| `idioma` | `es`, `pt`. |
| `origen` | `generado` (con versión del generador) o `manual` (con rol del autor). |
| `customer_id` | Cliente de prueba. |
| `turnos` | Mensajes y acciones del cliente, en orden. |
| `transaccion_objetivo` | ID real de la transacción, o `null`. |
| `resultado_esperado` | `reclamo_creado`, `aclaracion`, `abstencion`, `escalado`, `rechazo_seguro`. |
| `reglas_esperadas` | Reglas de política que deben aplicarse (p. ej. `R1`). |
| `motivo_escalamiento_esperado` | Si aplica. |
| `fallas_inyectadas` | Si aplica (`session_expired`, `tool_down`, …). |

Ejemplo (valores ilustrativos): `{"categoria": "normal", "idioma": "es", "turnos": [{"message": "Tengo un cobro de $120 que no reconozco"}, {"action": "select_candidate"}, {"action": "confirm"}], "resultado_esperado": "reclamo_creado"}`.

`test/` incluye el hash y la fecha de congelamiento. Pendiente: si los casos con IDs del dataset se pueden publicar (P-04 en [docs/open-questions.md](../../docs/open-questions.md)); si no, se guardan fuera del repo y aquí solo se documenta cómo regenerarlos.

## Entradas y salidas

Entrada: [generator/](../generator/README.md) y autores humanos. Salida: casos para [harness/](../harness/README.md) y [ml/](../../ml/README.md).

## Dependencias

[generator/](../generator/README.md).

## Responsable sugerido

Data scientist; todo el equipo escribe casos manuales.
