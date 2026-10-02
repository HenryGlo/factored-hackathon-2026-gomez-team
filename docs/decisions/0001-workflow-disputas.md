# ADR-0001: Dispute workflow instead of credit

Status: Accepted · Label: **[Decision]**

Status (2026-10-02): implemented. The dispute flow runs end to end in [backend/app/controller/engine.py](../../backend/app/controller/engine.py); adjacent intents were added around it (list transactions, case status, process questions, card lock), see [conversation-flow.md](../conversation-flow.md).

## Context

- **[Official]** The challenge asks to choose **one** coherent flow. Examples: account or payment inquiries, card support, **transaction dispute intake**, credit product information and eligibility. Implementing more flows gives no extra points.
- **[Official]** The problem must be backed by data: contact reasons, demand, data quality and operational constraints.
- **[Official]** For credit, conversation, predictive risk and eligibility policy must be kept separate, using approved rules or a labeled synthetic policy service.
- The team's exploration ([quality-report.md](../data/quality-report.md)):
  - Delinquency is random: AUC 0.513 with `credit_score` alone; the best exploratory model reaches 0.623 with temporal leakage. There is no signal for a credible credit risk.
  - "Cargo no reconocido" (unrecognized charge) appears in 12,297 complaints (18.3%), although all subcategories carry a similar weight.
  - `transactions` is the richest table for the flow and `fraud_score` is the only real signal (AUC 0.847).

## Decision

Build the flow for **disputes of unrecognized charges**: identify the transaction, create a case (with confirmation) or escalate with a structured handoff. Never approve refunds.

## Alternatives

| Alternative | Why not |
|---|---|
| Credit (information and eligibility) | No signal in delinquency; requires inventing a complete eligibility policy service. |
| Card support (only) | Fewer decision steps and less room for ML; partially included with `lock_card`. |
| Account or payment inquiries | Simpler, but with little automation control to demonstrate (confirmation, policy, escalation). |

## Consequences

- There is a real, measurable ML problem: identifying the transaction ([ADR-0002](0002-ranker-en-vez-de-llm.md)).
- The dataset has no dispute labels → they must be generated ([ADR-0003](0003-reclamos-generados-sobre-transacciones-reales.md)).
- The demand-based justification is weak because the data is uniform; it must be stated as a limitation.
- The dispute rules (R1–R6) are team assumptions ([policies.md](../policies.md)).
