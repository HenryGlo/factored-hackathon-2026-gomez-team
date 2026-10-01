# Contrato de tools

> Lista de tools: **[Decisión]**. Entradas, salidas, errores y permisos: **[Propuesta]**.

## Qué pide el reto

**[Oficial]** Usar tools de forma segura, aplicar el acceso a los registros de cada cliente y los permisos de acción en la capa de servicio o de tools, y reportar solo acciones verificadas. Se aceptan servicios sandbox y tools bancarios simulados si sus contratos y limitaciones están documentados.

## Reglas comunes

**[Propuesta]**

1. **`customer_id` inyectado.** Ningún tool recibe `customer_id` del LLM. El controlador lo toma de la sesión autenticada y lo agrega a la llamada.
2. **Pertenencia.** Todo recurso (transacción, producto, reclamo) se filtra por el `customer_id` de la sesión. Si no pertenece, el error es `not_found`, igual que si no existiera.
3. **Quién puede llamar.** Los tools los invoca el controlador según el estado, no el modelo libremente. El LLM solo propone parámetros (por ejemplo, filtros de búsqueda) que el código valida.
4. **Escrituras.** Requieren `confirmation_token` válido y que la política ([policies.md](policies.md)) haya devuelto `permitir`. Después de escribir se verifica con un tool de lectura.
5. **Reintentos.** Lecturas: hasta `MAX_RETRIES` con backoff. Escrituras: se reintentan solo si son idempotentes por token (el mismo token no crea dos reclamos).
6. **Trazas.** Cada llamada registra argumentos (enmascarados), resultado resumido, latencia, versión del modelo si aplica y errores.
7. **Sandbox.** Las escrituras van al esquema `app` de PostgreSQL, no modifican las tablas del dataset. No hay movimiento de dinero (**[Oficial]**: no se requiere ni se autoriza).

Matriz de permisos:

| Tool | Tipo | Estados permitidos | Requiere token | Requiere política |
|---|---|---|---|---|
| `search_transactions` | lectura | `inicio`, `aclarando` | no | no |
| `get_transaction` | lectura | todos salvo terminales | no | no |
| `get_existing_case` | lectura | `confirmando_movimiento` y posteriores | no | no |
| `fraud_risk` | lectura (interno) | `confirmando_movimiento` y posteriores | no | no |
| `create_dispute_case` | escritura | `ejecutando` | **sí** | **sí** |
| `get_case` | lectura | todos salvo `inicio` | no | no |
| `lock_card` | escritura | `ejecutando` | **sí** | **sí** |
| `get_card_status` | lectura | todos salvo terminales | no | no |
| `create_handoff` | escritura (interna) | cualquier estado → `escalado` | no | no (lo dispara el controlador) |

## Implementación

**[Decisión]** Implementados en [backend/app/tools/](../backend/app/tools/__init__.py):

- **Lectura:** `search_transactions`, `get_transaction`, `list_transactions`, `get_existing_case`, `get_case`, `list_cases`, `list_cards`, `get_card_status` (vista `app.card_status_effective`) y `get_handoff`.
- **Escritura:** `create_dispute_case`, `lock_card` y `create_handoff`.
- **`fraud_risk`:** es el componente `RiskModel` ([backend/app/ml/risk.py](../backend/app/ml/risk.py)); lee el `fraud_score` de la transacción ya obtenida por `get_transaction`.
- **Recursos ajenos o inexistentes:** siempre `not_found`, sin distinguir los casos.
- **Fallos:** las lecturas se reintentan una vez ante un error de infraestructura; después, bloque `error` y handoff `fallo_tool`. Las escrituras no se reintentan: el token ya se consumió o no.
- **Inyección de fallos:** para tests y el harness, `app.state.faults` (en proceso; no se puede fijar por HTTP).

## search_transactions

Busca y ordena transacciones candidatas del cliente de la sesión.

- **Entrada:** `amount?` (decimal), `currency?`, `date_from?`, `date_to?`, `merchant_text?`, `channel?`, `product_id?`, `limit` (1–20, por defecto 5).
- **Salida:** `candidates[]` con `transaction_id`, `transaction_date`, `amount`, `currency`, `merchant_name`, `channel`, `transaction_type`, `transaction_status`, `product_id`, `score`, `rank`; y `ranker_version`, `search_window` y `n_scanned`.
- **Lógica:** SQL filtra el universo del cliente: tipos disputables `Purchase`, `Payment` y `Withdrawal`, **incluidos** `Pending`, `Declined` y `Reversed`, dentro de la ventana. El ranker ([ml/ranker.md](ml/ranker.md)) ordena. **[Supuesto]** La ventana es de 120 días (`search_window_days`, [backend/config/policy.toml](../backend/config/policy.toml)), más larga que el plazo de R1: así los cargos fuera de plazo se encuentran y se escalan en vez de "no encontrarse" (P-10).
- **Errores:** `validation_error` (parámetros fuera de rango), `no_candidates` (resultado vacío, no es fallo), `ranker_unavailable` (fallback: orden por baseline determinista de monto y recencia, marcado en la traza), `db_unavailable`.
- **Permiso:** solo transacciones del `customer_id` de la sesión.

## list_transactions

Consulta de movimientos, **solo lectura**, para `consulta_movimientos`.

- **Entrada:**
  - rango de fechas: por defecto, los últimos 30 días;
  - comercio: por el léxico de alias o por texto;
  - monto mínimo y máximo;
  - estado;
  - límite: 10 por defecto, 50 como máximo.
- **Salida:** transacciones, `count` y `spend_by_currency`. El código calcula `count` sobre todo lo que cumple los filtros y `spend_by_currency` con los cargos Approved o Pending; el LLM nunca calcula cifras.

## list_cards

Tarjetas (`Tarjeta Crédito`, `Tarjeta Débito`) del cliente con su estado efectivo y los últimos 4 dígitos. Nunca devuelve el número completo.

## get_transaction

- **Entrada:** `transaction_id`.
- **Salida:** transacción completa (columnas del diccionario, ver [data/inventory.md](data/inventory.md)) sin `is_fraud`, `fraud_score`, latitud ni longitud en la vista del cliente.
- **Errores:** `not_found`, `db_unavailable`.
- **Permiso:** la transacción debe pertenecer al cliente de la sesión.

## get_existing_case

Revisa si ya existe un reclamo del sistema sobre esa transacción (regla R3).

- **Entrada:** `transaction_id`.
- **Salida:** `case` (`case_id`, `status`, `created_at`) o `null`.
- **Fuente:** tabla `app.dispute_cases`. **[Supuesto]** No usa la tabla `complaints` del dataset porque las quejas no se ligan a transacciones (match ~1 %, ver [data/quality-report.md](data/quality-report.md)).
- **Errores:** `not_found` (transacción ajena), `db_unavailable`.

## fraud_risk

- **Entrada:** `transaction_id`.
- **Salida:** `probability` (calibrada), `band` (`bajo` \| `medio` \| `alto`), `model_version`, `inputs_used` (`fraud_score` crudo).
- **Uso:** interno para la regla R6. No se muestra al cliente. Se muestra en la consola y en el handoff.
- **Errores:** `missing_score` (la transacción no tiene `fraud_score`; la política lo trata como "riesgo desconocido", ver R6), `model_unavailable`.
- Ficha del modelo: [ml/fraud-risk.md](ml/fraud-risk.md). Pendiente: cortes de las bandas (P-25).

## create_dispute_case

Registra un reclamo. **No aprueba devoluciones** (R5).

- **Entrada:** `transaction_id`, `reason_code` (`unrecognized` para `cargo_no_reconocido`; `amount_mismatch` o `duplicate` para `cobro_indebido`), `customer_statement` (texto del cliente, truncado y sanitizado), `confirmation_token`.
- **Salida:** `case_id`, `status: "registrado"`, `created_at`.
- **Precondiciones:** token válido y ligado a esta acción y transacción; política = `permitir`; sin reclamo existente.
- **Errores:** `invalid_confirmation`, `policy_denied` (incluye la regla), `duplicate_case` (devuelve el `case_id` existente), `db_unavailable`.
- **Verificación:** el controlador llama a `get_case(case_id)` después; si no lo encuentra, no reporta éxito y escala.

## create_dispute_cases

Varios cargos con **una** confirmación ("los dos más recientes"). Se crea un reclamo por transacción. **[Decisión]** 2026-10-01.

- **Entrada:** `transaction_ids` (2 a `max_multi_charges`), `reason_code`, `customer_statement`, `confirmation_token`. El token se emitió para esa lista exacta (ids ordenados y `reason_code`).
- **Salida:** `[{transaction_id, case_id, status: "registrado"}]`.
- **Atomicidad:** todos o ninguno, en una sola transacción de base. El token se consume una vez.
- **Idempotencia:** únicos (`confirmation_token_id`, `transaction_id`) e (`idempotency_key`, `transaction_id`). Ni el mismo token ni un reintento duplican un reclamo; además rige R3 (un reclamo abierto por transacción).
- **Antes de llamarla:** el controlador revalida la política de cada cargo.
- **Después:** verifica cada reclamo con `get_case` y devuelve un solo `result` con `items[]`.

## get_case

- **Entrada:** `case_id`.
- **Salida:** `case_id`, `transaction_id`, `status`, `created_at`, `policy_rules_applied`.
- **Errores:** `not_found` (inexistente o de otro cliente).

## lock_card

Bloqueo de tarjeta simulado. **[Decisión]** (2026-09-30) Es la intención propia `bloquear_tarjeta` (autoservicio): identificar la tarjeta, confirmación explícita, `lock_card`, verificar con `get_card_status` y ofrecer handoff de reposición. También se recomienda con riesgo alto y se ofrece con riesgo medio o desconocido (R6).

- **Entrada:** `product_id` (debe ser `Tarjeta Crédito` o `Tarjeta Débito` del cliente según `products.product_type`; los valores del dataset están en español, H12), `confirmation_token`.
- **Salida:** `product_id`, `status: "Blocked"`, `locked_at`.
- **Errores:** `invalid_confirmation`, `not_a_card`, `already_blocked`, `not_found`.
- **Efecto:** escribe en `app.card_status_overrides`; no modifica `products`.
- **Verificación:** `get_card_status` después de la escritura.

## get_card_status

- **Entrada:** `product_id`.
- **Salida:** `product_id`, `product_type`, `status` (valor del override si existe; si no, `products.product_status`).
- **Errores:** `not_found`, `not_a_card`.

## create_handoff

- **Entrada:** objeto de [handoff-schema.md](handoff-schema.md). Lo arma el controlador; el LLM (Sonnet 5) solo redacta el campo `summary`.
- **Salida:** `handoff_id`, `queue`, `status: "pendiente"`, `created_at`.
- **Errores:** `validation_error` (falta un campo obligatorio), `db_unavailable`. **[Propuesta]** Si falla tras reintentos, se informa al cliente que no se pudo transferir y se registra un error crítico en la traza; nunca se dice que se transfirió.
- **Permiso:** solo el controlador lo invoca.
