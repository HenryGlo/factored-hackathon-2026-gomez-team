# Políticas R1–R6

> ⚠️ **[Supuesto]** Estas reglas son **supuestos de práctica del equipo**, no políticas oficiales del banco ni del reto. El material oficial no define reglas de disputa. Sirven para demostrar control de automatización y se deben validar (P-14).

## Qué pide el reto

**[Oficial]**

- Definir qué solicitudes puede responder el sistema, qué acciones requieren confirmación y cuándo debe abstenerse o transferir a una persona.
- Aplicar permisos y políticas **fuera del texto generado por el modelo**.
- Las explicaciones deben basarse en fuentes, reglas de política y registros de ejecución.

## Cómo se aplican

**[Decisión]** Las reglas se evalúan en código, como funciones puras con id: [backend/app/policy/rules.py](../backend/app/policy/rules.py) (nodo N7). Cada decisión guarda todas las reglas evaluadas con su evidencia, en la traza y en `app.dispute_cases.policy_rules_applied`. Parámetros: [backend/config/policy.toml](../backend/config/policy.toml). El LLM nunca decide si una regla se cumple; recibe el resultado para explicarlo. Cada evaluación queda en la traza con la regla, el resultado y la evidencia.

Salidas posibles de la política: `permitir`, `informar` (no actuar, explicar), `denegar`, `escalar`.

Orden de evaluación **[Propuesta]**: R4 y R5 son restricciones permanentes; luego R2 → R3 → R1 → R6. El primer resultado distinto de `permitir` decide.

## Reglas

### R1 — Plazo del reclamo

Se crea un reclamo solo si el cargo confirmado tiene **≤ 60 días**.

- Días = `REFERENCE_DATE` − fecha de `transaction_date`. **[Supuesto]** Como el dataset termina el 2026-06-17, la demo usa una fecha de referencia simulada; Pendiente: cuál (P-08).
- Si tiene más de 60 días → `escalar` (motivo `fuera_de_plazo`).
- Ejemplo: "Tengo un cobro de $120 que no reconozco", confirmado, de hace 5 días → `permitir`. De hace 75 días → `escalar`.

### R2 — Pendiente es informativo

Si el cargo confirmado está en estado `Pending`, no se crea reclamo: se informa que aún no está procesado y puede cambiar → `informar` (`notice: pending_transaction`).

**[Supuesto]** Tratamiento de otros estados de `transaction_status` (valores del diccionario: Approved, Declined, Pending, Reversed): `Declined` y `Reversed` también son `informar` porque no hay cargo vigente (P-23).

### R2b — Cargo pendiente que el cliente afirma no haber hecho

**[Supuesto]** Regla del equipo (2026-10-01), no política oficial (P-14).

- **Cuándo aplica:** el cargo está en `Pending` y el cliente **afirma** que no lo hizo ("yo no lo hice", "no fui yo", "ni siquiera tengo carro"). No basta con que diga que no lo reconoce o no lo recuerda; con eso sigue aplicando R2.
- **Resultado:** `escalar` a la cola `fraude` con motivo `cargo_pendiente_no_reconocido` y prioridad alta. Se ofrece bloquear la tarjeta por precaución (con confirmación, R4). No se abre el reclamo formal todavía.
- **Qué se le dice al cliente:** que el reclamo formal se podrá abrir cuando el cargo se confirme y que el equipo de fraude ya tiene el caso (número del handoff).
- **Cómo se detecta:** el campo `afirma_no_haberlo_hecho` de la extracción (`extract@v2`), o la regla de palabras clave `ASSERTS_NOT_DONE` ([keyword_rules.py](../backend/app/ml/keyword_rules.py)); basta con cualquiera de los dos.
  - Vale también para el mensaje que sigue a un "cargo pendiente" informado, gracias al [cargo en foco](conversation-flow.md#ciclo-de-vida-cargo-en-foco-y-varios-cargos).
  - Las señales de contexto del cliente quedan en `customer_claims` del handoff.
- **Orden:** R2b se evalúa en el lugar de R2 y decide antes que R3, R1 y R6.

### R3 — No duplicar reclamos

Si `get_existing_case` devuelve un reclamo para esa transacción → `informar` con el número y estado del reclamo existente.

### R4 — Confirmar antes de actuar

Toda acción con efecto (`create_dispute_case`, `lock_card`) requiere un `confirmation_token` válido emitido en un bloque `action_confirmation` y enviado por el cliente con la acción `confirm` ([api-contract.md](api-contract.md)). Sin token → `denegar`. Texto libre no cuenta como confirmación.

### R5 — No aprobar devoluciones

El sistema nunca aprueba, promete ni simula devoluciones o abonos. Solo registra reclamos. Si el cliente pide una devolución, se explica que el reclamo será revisado por el banco. No existe ningún tool que haga devoluciones. **[Oficial]** No se requiere ni se autoriza movimiento de dinero.

### R6 — Riesgo por bandas

**[Supuesto]** (acordado el 2026-09-30, P-25). Se evalúa después de R1–R3.

| Banda | Qué hace |
|---|---|
| `alto` (probabilidad calibrada ≥ umbral por costo; equivale a `fraud_score` ≥ 30) | `escalar` al equipo de fraude (motivo `riesgo_alto`, cola `fraude`), aunque R1–R3 permitan el reclamo, y se **recomienda** bloquear la tarjeta del cargo. Prioridad `alta`; **`urgente` si además el cliente afirma que no hizo el cargo**. |
| `desconocido` (sin `fraud_score`) | **No** se trata como baja. En `cargo_no_reconocido` se **ofrece** el bloqueo. Si además el monto en USD (`amount_usd_filled`) supera el umbral de autoservicio (`self_service_max_usd` = 500), se escala (motivo `riesgo_desconocido`, cola `fraude`). |
| `medio` (probabilidad ≥ la mitad del umbral alto) | Se crea el reclamo y se **ofrece** el bloqueo como opción; el cliente decide. No obliga a escalar. Con el calibrador actual casi no ocurre: la probabilidad salta de ~0,03 % a 100 % cerca de `fraud_score` = 30. |
| `bajo` | Sin efecto. |

- **Traza:** registra la banda, la probabilidad y si el score faltaba (`score_faltante`).
- **Tarjeta:** el bloqueo solo se ofrece si el producto del cargo es una tarjeta del cliente y no está bloqueada.
- **Umbrales (2026-10-01, cierra P-25):** salen del score calibrado `risk-v1` (`models/risk/risk-v1.json`), elegido por costo esperado con una partición temporal ([experimento](experiments/EXP-20261001-risk-calibration.md), [ficha](ml/fraud-risk.md)). Antes: `fraud_score/100` ≥ 0,70 alto y ≥ 0,35 medio (`RISK_MODEL=raw_fraud_score` los recupera). Los costos de cada error son supuestos del equipo.
- **El riesgo solo cambia la ruta y la prioridad del caso.** El sistema nunca declara un fraude ni decide sobre dinero: la banda es una señal de **movimiento anómalo**, no un fraude confirmado, y así se escribe en el handoff (`nota_riesgo`) y en los textos.

## Otras condiciones de escalamiento

**[Propuesta]** No son reglas de política de negocio sino del controlador:

- 3 vueltas de aclaración sin identificar la transacción.
- El cliente pide hablar con una persona.
- Fallo de tool o del LLM tras reintentos, o acción no verificada.
- Intento repetido de acceso no autorizado en la conversación (Pendiente: umbral, P-27).
