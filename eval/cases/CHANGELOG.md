# Changelog del set de evaluación

Cambios en los casos de `eval/cases/` (dev, dev_paraphrase, test). Cada cambio dice qué casos, por qué y en qué PR, para que
un resultado se pueda comparar con el set con el que se midió. El esquema está en [schema.py](schema.py).

## 2026-10-04 · "no, ese no lo reconozco" en la confirmación

- Nuevos en dev (133): `dev-rodeo-no-coma-no-es-mio-es`, `-pt`. `dev_noisy` regenerado. `eval/ci_reference.json`: 133/133.

## 2026-10-03 · modo voz manos libres

- Nuevos en dev (131): `dev-voz-sin-tocar-es`, `-pt` — el cliente dice el nombre de la respuesta rápida ("ver mis movimientos") y
  elige el cargo por el nombre del comercio, sin acciones de botón salvo la confirmación final.
- `dev_noisy` regenerado (120). `eval/ci_reference.json`: 131/131.

## 2026-10-02 · búsqueda honesta, pedir un dato y errores de tipeo (prompt 11)

- Nuevos en dev (129), en `dev/busqueda.yaml`: 18 casos es/pt — sin referencias (pide un dato; luego da el dato; pide ver sus
  movimientos), comercio inexistente, comercio por alias de extracto (`{comercio_alias}`), solo monto, solo fecha, error de
  tipeo + comercio, el mensaje exacto de la revisión ("n oreconocido en Facebook") y agotar los intentos.
- Split nuevo `dev_noisy` (118 casos), generado desde dev con `python -m eval.make_noisy` (semilla fija).
- Cuatro checkers nuevos (22 en total): `sin_candidatos_sin_referencias`, `candidatos_coinciden`,
  `disputa_no_fuera_de_alcance`, `sin_contadores_internos`.
- `eval/ci_reference.json`: 129/129.

## 2026-10-02 · saludos repetidos y checker `sin_mensajes_repetidos`

- Nuevos en dev (111): `dev-saludo-repetido-es`, `-pt`, `dev-como-estas-es`, `dev-tudo-bem-pt`, `dev-saludo-tras-reclamo-es`, `-pt`.
- Checker nuevo `sin_mensajes_repetidos` (18 checkers), aplicado a todos los casos. Sobre el código anterior fallaba en 1 caso de
  dev (`dev-aclaracion-agotada-es`) y 9 de dev_paraphrase: la pregunta de aclaración se repetía idéntica.
- `eval/ci_reference.json`: 111/111.

## 2026-10-02 · casos de los fallos que encontró la prueba de humo de prodlike

- Nuevos en dev (105): `dev-rodeo-no-reconozco-en-confirmacion-es`, `-pt` ("no reconozco ese cargo" como respuesta a
  "¿es este el movimiento?") y `dev-rodeo-no-reconozco-tras-algo-mas-es` ("No reconozco un cargo…" después de "¿algo más?").
- `eval/ci_reference.json`: 105/105 en `baseline` y `sistema` con LLM falso.

## 2026-10-01 (noche) · riesgo por defecto con el score calibrado (decisión del líder)

- Todas las variantes pasan a `RISK_MODEL=calibrated` (`risk-v1`).
- `dev-riesgo-medio-es` vuelve a ser `dev-riesgo-medio-calibrado-es`: un `fraud_score` entre 35 y 70 es banda alta con el
  calibrado y escala a fraude (prioridad alta), sin crear el reclamo.
- Las corridas anteriores de este día (incluida la de cierre en local, 102/102) se midieron con el score crudo.

## 2026-10-01 · riesgo por defecto con el score crudo (decisión del umbral pendiente)

- Todas las variantes vuelven a `RISK_MODEL=raw_fraud_score`.
- `dev-riesgo-medio-calibrado-es` pasa a ser `dev-riesgo-medio-es`: con el score crudo, un `fraud_score` entre 35 y 70 crea el
  reclamo y ofrece el bloqueo (antes esperaba el escalamiento del score calibrado). Si el líder elige un corte menor, este caso
  cambia otra vez y queda anotado aquí.

## 2026-10-01 · dev 102 (clientes que dan rodeos, issue #27)

18 casos multiturno es/pt en `dev/rodeos.yaml`: historia larga antes del pedido, referencias indirectas (por tipo de comercio,
"me cobraron dos veces"), corrección del monto o la fecha a mitad del flujo, "no, el otro", cancelar y retomar, queja mezclada
con el pedido, pregunta respondida con otra pregunta (en la confirmación del movimiento y en la de la acción) y mensajes muy
cortos ("ese", "essa mesma").

## 2026-10-01 · dev 84 (riesgo calibrado, issue #26)

- `dev-riesgo-medio-calibrado-es` (selector nuevo `riesgo_medio_tarjeta`: `fraud_score` entre 35 y 70; con el score calibrado
  escala a fraude), `dev-riesgo-alto-no-lo-hice-es` y `dev-riesgo-alto-nao-fui-eu-pt` (riesgo alto + el cliente afirma que no
  lo hizo → prioridad `urgente`). Campo nuevo `handoff_priority`.
- Dataset sintético de la CI: escenario `riesgo_medio` (45 clientes más, 515 en total).
- Todas las variantes usan ahora el riesgo calibrado (`RISK_MODEL=calibrated`).

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
