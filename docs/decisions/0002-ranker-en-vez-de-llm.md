# ADR-0002: Ranker instead of LLM to identify the transaction

Status: Accepted · Label: **[Decision]**

Status (2026-10-02): implemented with changes. The LLM only extracts fields and a ranker behind an interface orders the candidates, but the ranker in use is the rule-based `RuleRanker` (`rule@v3`, `ranker = "rule"` in [ml.toml](../../backend/config/ml.toml), the only value the registry accepts); the logistic regression and LightGBM models have not been trained or integrated. See [ranker.md](../ml/ranker.md).

## Context

- A customer describes the charge vaguely ("Tengo un cobro de $120 que no reconozco": I have a $120 charge I don't recognize) and may have dozens of transactions in the search window.
- **[Official]** Evaluate at least one learned component against a baseline, with valid labels and no leakage. Justify where AI is appropriate and where deterministic logic is preferable.
- Passing all transactions to the LLM raises cost and latency, exposes more data to the external provider and can produce nonexistent IDs.

## Decision

The LLM only **extracts** fields (amount, date, merchant, channel). An **ML ranker** orders the candidate transactions: logistic regression as the main model and LightGBM lambdarank as the challenger, against a deterministic baseline of amount and recency. A threshold in code decides whether the candidate is clear. Model card: [ranker.md](../ml/ranker.md).

## Alternatives

| Alternative | Why not |
|---|---|
| LLM picks the transaction among the customer's | More expensive and slower, hard to calibrate, can hallucinate; kept as a comparison variant in the ablation. |
| Rules only (exact amount + recency) | Fragile with approximate amounts and relative dates; kept as baseline and fallback. |
| Semantic search with embeddings | `merchant_name` is short and sometimes null; the problem is mostly numeric and temporal. |

## Consequences

- Learned component measurable with Top-1, Recall@3 and MRR.
- Score usable as a threshold to clarify or abstain.
- Requires constructed relevance labels ([ADR-0003](0003-reclamos-generados-sobre-transacciones-reales.md)).
- If the ranker fails, the system falls back to the baseline and records it.
