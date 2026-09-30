# backend/tools/

## Propósito

Acceso a datos y acciones con permisos por sesión. Contrato completo: [docs/tools-contract.md](../../docs/tools-contract.md).

## Qué irá aquí

**[Decisión]** Un módulo por tool: `search_transactions`, `get_transaction`, `get_existing_case`, `fraud_risk`, `create_dispute_case`, `get_case`, `lock_card`, `get_card_status`, `create_handoff`.

**[Propuesta]** Además:

- Un envoltorio común que inyecta `customer_id` desde la sesión, verifica pertenencia, valida el estado permitido y registra la llamada en la traza.
- Validación y consumo de `confirmation_token` en los tools de escritura.
- Adaptadores a los modelos de [ml/](../../ml/README.md) (ranker y riesgo) con fallback al baseline.

## Entradas y salidas

Entrada: argumentos validados + contexto de sesión. Salida: resultado tipado o error del catálogo.

## Dependencias

[persistence/](../persistence/README.md), [policy/](../policy/README.md) (escrituras), [ml/](../../ml/README.md).

## Responsable sugerido

Software developer; data scientist para los adaptadores de modelos.
