# ADR-0004: Model per node

Status: Accepted · Label: **[Decision]**

Status (2026-10-02): implemented with changes. The per-node assignment is as decided, a `faq_answer` node (Haiku) was added, and the Claude API client now exists: `anthropic_api` is the production provider with fixed model IDs per node ([llm.toml](../../backend/config/llm.toml), [llm-data.md](../llm-data.md)).

## Context

- **[Official]** Make explicit the trade-offs between autonomy, accuracy, latency, cost and human oversight; report p50/p95 latency and cost per case.
- The nodes differ in difficulty: classifying intent or extracting an amount is simpler than explaining a policy result or summarizing a case for a human.

## Decision

- **Haiku 4.5** for intent, extraction, clarification and confirmation (short, frequent tasks with structured output).
- **Sonnet 5** for the final explanation to the customer and the handoff summary (writing tasks with more context, once per conversation).
- One model per node, with CLI aliases (`haiku` | `sonnet`).
  - Defaults in [backend/config/llm.toml](../../backend/config/llm.toml), versioned; override per environment with `MODEL_<NODO>` (e.g. `MODEL_EXPLAIN=haiku`). **Updated 2026-09-30**: replaces `LLM_MODEL_FAST` and `LLM_MODEL_REASONING`.
  - The trace stores the requested alias **and** the real ID returned by the provider. With `claude -p` (Claude Code 2.1.286), `haiku` → `claude-haiku-4-5-20251001` and `sonnet` → `claude-sonnet-5-5` (measured in [llm-data.md](../llm-data.md)).
  - Provider chosen with `LLM_PROVIDER=anthropic_api|claude_cli|fake` (default `fake`). The `LLMClient` interface allowed adding the Claude API client without touching the nodes; with `anthropic_api` each node uses the fixed ID above instead of an alias.
- Versioned prompts per node; each trace records model and prompt version.
- **Updated 2026-09-30: not every writing node needs an LLM.**
  - `confirm` uses a template (`CONFIRM_MODE=template`).
  - `clarify` uses a template to choose among candidates and the LLM for the rest (`CLARIFY_MODE=auto`).
  - The rule is in [conversation-flow.md](../conversation-flow.md#modos-de-confirm-y-clarify). The harness's "all LLM" variant serves as the comparison.

## Alternatives

| Alternative | Why not |
|---|---|
| Sonnet on every node | More cost and latency on the most frequent nodes, with no evidence that it improves. |
| Haiku on every node | May be enough; verified in the ablation. |
| Local or classical models for intent | Evaluated as baselines ([intent-classifier.md](../ml/intent-classifier.md)). |

## Consequences

- The "model per node" ablation ([evaluation.md](../evaluation.md)) must confirm or reverse this decision with data.
- Two models to version and monitor.
