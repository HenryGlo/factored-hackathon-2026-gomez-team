# Changelog del set de evaluación

Cambios en los casos de `eval/cases/` (dev, dev_paraphrase, test). Cada cambio dice qué casos, por qué y en qué PR, para que
un resultado se pueda comparar con el set con el que se midió. El esquema está en [schema.py](schema.py).

## 2026-10-01 · dev 81, dev_paraphrase 96 (PR "test: R5 field audit and evaluation regressions")

- **Movidos de dev_paraphrase a dev, con el resultado esperado de su nuevo sentido** (la paráfrasis agregó información;
  hallados en el punto de control 1, [llm-data.md](../../docs/llm-data.md)):
  - `dev-pendiente-pt-p2`: "eu nunca comprei nada aí" sobre un cargo pendiente → R2b: escalamiento a fraude
    (`cargo_pendiente_no_reconocido`, aviso `pending_unrecognized`), sin reclamo.
  - `dev-empate-sin-separar-es-p2`: "ayer" separa dos cargos de monto parecido → propone el de ayer sin preguntar y se
    resuelve sobre ese (`transaction: second`, 0 aclaraciones). Usa `today_after: second` (nuevo en el esquema): "hoy" es
    el día siguiente a esa transacción, así "ayer" la señala en el dataset real y en el sintético.
- **Regresiones del hallazgo de seguridad del `tema`** ([security.md](../../docs/security.md#hallazgos-de-la-evaluación)):
  `dev-inyeccion-reembolso-pt` y `dev-inyeccion-tema-es`, además del `dev-inyeccion-reembolso-es` existente.
- **`dev-chao-y-vuelve-es`:** "chao" cierra; el siguiente mensaje recibe 409 y sigue en una conversación enlazada
  (`new_conversation` con `link_previous: true`, nuevo en el esquema).

## 2026-10-01 · dev 76 (#14)

16 casos de saludos y fuera de alcance (es/pt): saludo solo, saludo con pedido, "gracias", préstamo, tasa de CDT/CDB,
chiste, mensaje mixto, fuera de alcance con instrucción maliciosa. Campos nuevos: `fast_path`, `out_of_scope`, `open_at_end`.

## 2026-10-01 · dev_paraphrase 96 (#20)

Se quitaron `dev-pendiente-pt-p2` y `dev-empate-sin-separar-es-p2` porque cambiaban el significado del caso original
(después se movieron a dev, arriba).

## 2026-10-01 · dev 60 (#11)

6 casos de preguntas sobre el proceso después de un reclamo y de un bloqueo (es/pt). Campo nuevo: `faq_ids`.

## 2026-10-01 · dev 54 (#5)

4 casos de "sí"/"no" con tipeos y una respuesta ambigua que no debe confirmar.

## 2026-09-30 · dev 50, dev_paraphrase 98 (#2)

Set inicial: 50 casos dev escritos por el equipo; dev_paraphrase generado con `claude -p --model sonnet` (2 paráfrasis por
caso con mensajes); kit del test escrito a mano (`eval/manual/`).
