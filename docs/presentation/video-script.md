# Video pitch: narration and shots

Target: about **3 minutes** (maximum length still unconfirmed, P-02). Lines marked ✂ are the ones to cut for a 2-minute
version. Recording setup, users and clicks are in [demo-script.md](../demo-script.md); this file is what to say and show.

Before recording: `scripts/prodlike_up.sh`, then `npm run demo check` must end in "LISTO para grabar". On Saturday, record
against the public URL instead. The demo password is never typed on camera.

| # | Time | On screen | Say |
|---|---|---|---|
| 1 | 0:00–0:15 | Landing page | "A customer sees a charge they don't recognize. Today that is a five-minute call. This is BankyFicticious, a fictitious bank: one workflow, unrecognized-charge disputes, done end to end in Spanish and Portuguese." |
| 2 | 0:15–0:55 | Chat as `demo_cargo_claro_2`: describe the charge → the assistant shows the transaction → confirm → dispute reference `RCL-…` | "The model only understands the message. Code finds the transaction in the customer's real history, applies policy, and asks for an explicit confirmation. The dispute is created, then verified in the database, and only then the customer sees the reference. It never promises a refund." |
| 3 | 0:55–1:20 | Chat as `demo_cargos_parecidos_2`: two similar charges → the assistant asks which one | "When two charges look alike, it does not guess. It asks, at most three times, and if it still cannot tell, it hands over to a person." |
| 4 | 1:20–1:55 | Chat as `demo_fraude_alto_2` → handoff notice → agent portal as `analista_1`: urgent ticket, structured handoff, take the ticket | "A high-risk charge that the customer says they did not make is not automated. It becomes an urgent ticket. The agent sees verified facts next to what the customer claims, the policy that applied and what is still open, so nobody has to ask again." |
| 5 | 1:55–2:15 | Admin panel as `admin_1`: SLOs, latency, cost per day, traces ✂ | "Every step is traced with its model, latency and cost. Admins see SLOs and the budget." |
| 6 | 2:15–2:40 | Architecture diagram (README) | "The architecture in one line: the LLM understands, code decides. A state machine with a bounded loop, policy in code, tools with one-time confirmation tokens, a calibrated fraud-risk model, and a guard on every text the model writes." |
| 7 | 2:40–3:00 | Results table (slide 5), with the final row filled | "Measured with deterministic checkers, not an LLM judge: with the Claude API, 60 of 60 development cases pass with zero unsafe results at 0.8 cents per case, and **[final test result]** on the frozen test our team wrote by hand. Our own evaluation found a prompt-injection hole and a conversation bug; both are fixed and are now regression cases." |
| 8 | 3:00–3:10 | Public URL and repository ✂ | "The app is deployed at **[URL]**, the repository is public, and the README has everything to run it in under ten minutes." |

Notes for the recording:

- One of the three flows should be shown in **Portuguese** (the submission checklist asks for a complete Portuguese path);
  flow 3 is the shortest to redo in Portuguese.
- Say numbers exactly as in [slides.md](slides.md). Do not quote latency or cost from a local `claude -p` run.
- Replace the two bracketed placeholders in rows 7 and 8 after Saturday's final run and deployment; if the final run is
  not available, say "the final test is still running" rather than a number.
