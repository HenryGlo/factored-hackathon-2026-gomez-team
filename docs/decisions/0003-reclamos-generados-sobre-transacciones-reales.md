# ADR-0003: Generated claims over real transactions

Status: Accepted · Label: **[Decision]**

Status (2026-10-02): implemented with changes. The generated cases exist (`eval/cases/dev`, `eval/cases/dev_paraphrase`) and the kit for the hand-written test is ready, but the hand-written test set has not been imported yet (`eval/cases/test` is empty); see [evaluation.md](../evaluation.md) and [STATUS.md](../STATUS.md).

## Context

- The dataset's complaints do not link to transactions (match ~1%) and their text is templated (5 distinct descriptions). See [quality-report.md](../data/quality-report.md).
- There is no Portuguese text in the dataset. **[Official]** Interactions in Spanish and Portuguese must be demonstrated.
- **[Official]** Use valid labels or relevance judgments, avoid leakage and evaluate on held-out cases.

## Decision

1. **Generate** training and evaluation claims by picking a **real transaction** (synthetic, from the dataset) of a customer and writing a claim about it in Spanish and Portuguese, with templates, paraphrases and controlled noise. The chosen transaction is the label.
2. Write **by hand** a test set with realistic and adversarial messages, in both languages.
3. Record the origin of each case (`generado` or `manual`) and the generator version.

## Alternatives

| Alternative | Why not |
|---|---|
| Use the dataset's complaints as labels | They do not link to transactions; templated text. |
| Everything written by hand | Too few cases to train the ranker. |
| Everything generated with an LLM | Risk of evaluating the LLM with its own style; used only for paraphrases and contrasted with the hand-written set. |

## Consequences

- Clean, abundant labels, but the ranker learns the generator's distribution; the hand-written set measures how much it degrades with real text.
- Split by customer and by template to avoid leakage ([evaluation.md](../evaluation.md)).
- Limitation to report: the cases do not come from real customers.
