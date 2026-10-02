# Architecture decisions (ADR)

Format of each ADR: **Context**, **Decision**, **Alternatives**, **Consequences**. Possible status: `Accepted`, `Superseded by ADR-XXXX`, `Proposed`.

| # | Title | Status | In the code (2026-10-02) |
|---|---|---|---|
| [0001](0001-workflow-disputas.md) | Dispute workflow instead of credit | Accepted | Implemented |
| [0002](0002-ranker-en-vez-de-llm.md) | Ranker instead of LLM to identify the transaction | Accepted | Implemented with changes (rule-based ranker) |
| [0003](0003-reclamos-generados-sobre-transacciones-reales.md) | Generated claims over real transactions | Accepted | Implemented with changes (hand-written test set pending) |
| [0004](0004-modelo-por-nodo.md) | Model per node | Accepted | Implemented with changes (Claude API provider added) |
| [0005](0005-maquina-de-estados-con-loop-acotado.md) | State machine with a bounded loop instead of a single agent | Accepted | Implemented with changes (conversation lifecycle) |
| [0006](0006-hosting-en-render.md) | Demo hosting on Render (alternative: ECS Express Mode + RDS) — in Spanish | Accepted | Blueprint ready; deployment pending (Saturday) |

To add an ADR: copy the structure of an existing one with the next number, open a PR and link it in this table. An accepted ADR is not edited: it is replaced with a new one. The "Status (2026-10-02)" line in each ADR only records how the decision stands in the code; it does not change the decision.
