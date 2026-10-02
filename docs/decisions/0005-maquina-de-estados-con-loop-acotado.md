# ADR-0005: State machine with a bounded loop instead of a single agent

Status: Accepted · Label: **[Decision]**

Status (2026-10-02): implemented with changes. The controller and the 3-round limit (`max_clarify_rounds = 3` in [policy.toml](../../backend/config/policy.toml)) are in [engine.py](../../backend/app/controller/engine.py); since 2026-10-01 a finished flow returns the conversation to `inicio` with "¿algo más?" (anything else?), only a goodbye or inactivity leads to `cerrado`, and `ejecutando` is transient within a turn ([conversation-flow.md](../conversation-flow.md#ciclo-de-vida-cargo-en-foco-y-varios-cargos)).

## Context

- **[Official]** "AI should not be autonomous just because it can be." It must be defined which actions require confirmation, when to abstain and when to transfer, and permissions and policies must be enforced outside the model's text.
- **[Official]** Demonstrate traceability, bounded retries and safe fallback.
- A single agent with all the tools decides the order of steps inside the prompt: it is harder to guarantee that it confirms before acting and that it does not ask questions indefinitely.

## Decision

A **controller with an explicit state machine** (`inicio`, `aclarando`, `confirmando_movimiento`, `confirmando_accion`, `ejecutando`, `cerrado`, `escalado`) decides the next node. The clarification loop is **bounded to 3 rounds**, counted in code; when they run out, the case is escalated. See [conversation-flow.md](../conversation-flow.md).

## Alternatives

| Alternative | Why not |
|---|---|
| Single agent with tools (variant C of the ablation) | Less control and auditability; compared in the ablation. |
| Stateless prompt chain (variant B) | Does not handle multi-turn clarification well. |
| Rules only, no LLM (variant A) | Does not understand free-form language or Portuguese; it is the baseline. |

## Consequences

- Predictable, auditable behavior: every transition is recorded in the trace.
- Less flexibility for requests outside the flow, which are declined or escalated.
- The 3-round limit is a team choice; it is reviewed with the dev results.
