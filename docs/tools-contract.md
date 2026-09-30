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

## search_transactions

Busca y ordena transacciones candidatas del cliente de la sesión.

- **Entrada:** `amount?` (decimal), `currency?`, `date_from?`, `date_to?`, `merchant_text?`, `channel?`, `product_id?`, `limit` (1–20, por defecto 5).
- **Salida:** `candidates[]` con `transaction_id`, `transaction_date`, `amount`, `currency`, `merchant_name`, `channel`, `transaction_type`, `transaction_status`, `product_id`, `score`, `rank`; y `ranker_version`, `search_window` y `n_scanned`.
- **Lógica:** SQL filtra el universo del cliente dentro de la ventana de búsqueda; el ranker ([ml/ranker.md](ml/ranker.md)) ordena. **[Supuesto]** Ventana de búsqueda más larga que el plazo de R1, para poder identificar cargos fuera de plazo y escalarlos en vez de "no encontrarlos". Pendiente: tamaño de la ventana (P-10).
- **Errores:** `validation_error` (parámetros fuera de rango), `no_candidates` (resultado vacío, no es fallo), `ranker_unavailable` (fallback: orden por baseline determinista de monto y recencia, marcado en la traza), `db_unavailable`.
- **Permiso:** solo transacciones del `customer_id` de la sesión.

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

## get_case

- **Entrada:** `case_id`.
- **Salida:** `case_id`, `transaction_id`, `status`, `created_at`, `policy_rules_applied`.
- **Errores:** `not_found` (inexistente o de otro cliente).

## lock_card

Bloqueo de tarjeta simulado. **[Supuesto]** Solo se ofrece cuando el cliente sospecha fraude y lo pide; Pendiente confirmar si entra en el MVP (P-21).

- **Entrada:** `product_id` (debe ser `Credit Card` o `Debit Card` del cliente, según `products.product_type`), `confirmation_token`.
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
