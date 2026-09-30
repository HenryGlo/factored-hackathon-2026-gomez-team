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
| `alto` (`fraud_score/100` ≥ 0,70) | `escalar` al equipo de fraude (motivo `riesgo_alto`, cola `fraude`, prioridad alta), aunque R1–R3 permitan el reclamo, y se **recomienda** bloquear la tarjeta del cargo. |
| `desconocido` (sin `fraud_score`) | **No** se trata como baja. En `cargo_no_reconocido` se **ofrece** el bloqueo. Si además el monto en USD (`amount_usd_filled`) supera el umbral de autoservicio (`self_service_max_usd` = 500), se escala (motivo `riesgo_desconocido`, cola `fraude`). |
| `medio` (≥ 0,35) | Se crea el reclamo y se **ofrece** el bloqueo como opción; el cliente decide. No obliga a escalar. |
| `bajo` | Sin efecto. |

- **Traza:** registra la banda, la probabilidad y si el score faltaba (`score_faltante`).
- **Tarjeta:** el bloqueo solo se ofrece si el producto del cargo es una tarjeta del cliente y no está bloqueada.
- **Umbrales:** están en [backend/config/ml.toml](../backend/config/ml.toml) y [backend/config/policy.toml](../backend/config/policy.toml). Son supuestos que se revisan con la calibración (prompt 04, E2).

## Otras condiciones de escalamiento

**[Propuesta]** No son reglas de política de negocio sino del controlador:

- 3 vueltas de aclaración sin identificar la transacción.
- El cliente pide hablar con una persona.
- Fallo de tool o del LLM tras reintentos, o acción no verificada.
- Intento repetido de acceso no autorizado en la conversación (Pendiente: umbral, P-27).
