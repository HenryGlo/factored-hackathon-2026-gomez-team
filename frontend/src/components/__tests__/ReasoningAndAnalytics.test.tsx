import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "../../api/client";
import type { AdminAnalytics as Analytics, AnalyticsCell, TicketReasoning } from "../../api/types";
import { SessionProvider } from "../../lib/session";
import AdminAnalytics from "../AdminAnalytics";
import ReasoningPanel from "../ReasoningPanel";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });
const wrap = (ui: React.ReactNode) => render(<MemoryRouter><SessionProvider>{ui}</SessionProvider></MemoryRouter>);
const cell = (key: string, n: number | null, share: number | null = null): AnalyticsCell => ({ key, label: key, n, share, suppressed: n === null });

const reasoning: TicketReasoning = {
  ticket_id: "hof_1", conversation_id: "conv_1", note: "",
  turns: [{
    turn_id: "turn_1", at: "2026-06-18T10:00:00+00:00", customer: { text: "No reconozco un cargo de 250 dólares", action: null },
    understanding: { intent: "cargo_no_reconocido", source: "LLM (claude-haiku)", certainty: "alta", language: "es", others: [], corrected: false },
    data: { source: "LLM (claude-haiku)", fields: { amount_hint: { value: "250", currency: "USD" } } },
    search: [{ step: "search_transactions", result: "1 resultado(s)" }],
    risk: { band: "alto", probability: 1, missing_score: false, source: "modelo (calibrated@risk-v1)" },
    policy: { result: "escalar", decides: { id: "R6", motivo: "riesgo_alto" }, rules: [{ id: "R4", result: "permitir", reason: "requiere_confirmation_token" }, { id: "R6", result: "escalar", reason: "riesgo_alto" }] },
    guardrails: [{ id: "verificacion", label: "Verificación: el resultado se comprobó en la base" }],
    response: { state_before: "confirmando_movimiento", state_after: "escalado", written_by: "plantilla", blocks: ["Pasé tu caso al equipo de fraude."] },
    other_steps: [], totals: { steps: 9, llm_calls: 2, latency_ms: 1800, cost_usd: 0.0031, errors: [] },
  }],
};

describe("ReasoningPanel", () => {
  it("shows what the assistant understood, the data, the policy, the guardrails and the reply for each message", async () => {
    vi.spyOn(api, "ticketReasoning").mockResolvedValue(reasoning);
    wrap(<ReasoningPanel ticketId="hof_1" />);
    await waitFor(() => expect(screen.getByText("No reconozco un cargo de 250 dólares")).toBeTruthy());
    expect(screen.getByText("1 guarda")).toBeTruthy();
    expect(screen.getByText(/amount_hint/)).toBeTruthy();
    expect(screen.getByText(/decide R6: riesgo_alto/)).toBeTruthy();
    expect(screen.getByText("Verificación: el resultado se comprobó en la base")).toBeTruthy();
    expect(screen.getByText("Pasé tu caso al equipo de fraude.")).toBeTruthy();
  });

  it("shows no conversation data if the server says the ticket is not theirs", async () => {
    vi.spyOn(api, "ticketReasoning").mockRejectedValue(new ApiError(403, "not_assigned", "Toma el ticket", "req_1"));
    wrap(<ReasoningPanel ticketId="hof_1" />);
    await waitFor(() => expect(screen.getByText(/solo lo ve quien atiende el ticket/)).toBeTruthy());
  });
});

describe("AdminAnalytics", () => {
  it("shows counts, hides small groups as '< 5' and flags synthetic conversations", async () => {
    const data: Analytics = {
      days: 30, origin: "all", min_group: 5, note: "",
      totals: { conversations: 43, synthetic_conversations: 40, assistant_turns: 117, llm_calls: 76 },
      understanding: { intents: [cell("cargo_no_reconocido", 32, 0.667), cell("pedir_humano", null)], source: [cell("LLM", 40, 1)], certainty: [] },
      data: { extractions: 44, fields: [cell("amount_hint", 29, 0.659)] },
      guardrails: [cell("verificacion", 27, 0.231)], risk: [cell("bajo", 29, 0.9)],
      policy: { results: [cell("permitir", 29, 0.9)], rules: [{ rule: "R6", total: 30, results: [cell("permitir", 29), cell("escalar", null)] }] },
      clarification: { decisions: [], rounds: [] }, funnel: [cell("inicio", 43, 1)],
      outcomes: { languages: ["es"], by_language: { es: [cell("reclamo registrado", 10, 0.4)] } }, handoff_reasons: [], feedback: [],
    };
    const spy = vi.spyOn(api, "adminAnalytics").mockResolvedValue(data);
    wrap(<AdminAnalytics />);
    await waitFor(() => expect(screen.getByText("Cargo no reconocido")).toBeTruthy());
    expect(spy).toHaveBeenCalledWith(30, "all");
    expect(screen.getByText("< 5")).toBeTruthy();                                   // pedir_humano, sin número
    expect(screen.getByText(/40 de 43 conversaciones son sintéticas/)).toBeTruthy();
    expect(screen.getByText(/Permitir: 29 · Escalar: < 5/)).toBeTruthy();
    expect(screen.getByText(/ningún mensaje ni conversación individual/)).toBeTruthy();
  });
});

describe("AdminInsights", () => {
  it("simulates thresholds, lists topics as terms only and flags merchants above their normal weight", async () => {
    const { default: AdminInsights } = await import("../AdminInsights");
    const { fireEvent } = await import("@testing-library/react");
    const c = (n: number | null, share: number | null = null) => ({ n, share, suppressed: n === null });
    const sim = (after: number, changes: { from: string; to: string; rule: string; n: number | null; share: null; suppressed: boolean }[]) => ({
      days: 30, origin: "all", min_group: 5, evaluated: 100, note: "",
      current: { dispute_window_days: 60, risk_threshold: 0.5, self_service_max_usd: 500 }, proposed: { dispute_window_days: 30, risk_threshold: 0.5, self_service_max_usd: 500 },
      before: { permitir: c(80, 0.8), informar: c(8, 0.08), escalar: c(12, 0.12) }, after: { permitir: c(100 - after - 8, 0.6), informar: c(8, 0.08), escalar: c(after, after / 100) },
      changes, changed: c(changes.reduce((s, x) => s + (x.n ?? 0), 0)), not_reproducible: c(0),
    });
    const spy = vi.spyOn(api, "adminSimulate").mockImplementation(async (_d, _o, p) => (p.dispute_window_days ? sim(32, [{ from: "permitir", to: "escalar", rule: "R1", n: 20, share: null, suppressed: false }]) : sim(12, [])));
    vi.spyOn(api, "adminTopics").mockResolvedValue({ days: 30, origin: "all", min_group: 5, classified_turns: 400, not_understood: c(40, 0.1), by_intent: [],
      clusters: [{ terms: ["prestamo", "tasa"], ...c(14, 0.35) }], unclustered: c(null), note: "" });
    vi.spyOn(api, "adminMerchants").mockResolvedValue({ days: 30, origin: "all", min_group: 5, disputes: 78, other_merchants: c(30), note: "",
      merchants: [{ merchant: "Cine Premium", n: 12, share: 0.154, purchase_share: 0.04, lift: 3.85, flag: true }] });
    wrap(<AdminInsights />);
    await waitFor(() => expect(screen.getByText("prestamo")).toBeTruthy());
    expect(screen.getByText("Cine Premium")).toBeTruthy();
    expect(screen.getByText("revisar")).toBeTruthy();
    const days = await screen.findByLabelText(/Plazo del reclamo/);
    fireEvent.change(days, { target: { value: "30" } });
    fireEvent.click(screen.getByRole("button", { name: "Simular" }));
    await waitFor(() => expect(spy).toHaveBeenLastCalledWith(30, "all", { dispute_window_days: 30, risk_threshold: 0.5, self_service_max_usd: 500 }));
    await waitFor(() => expect(screen.getByText(/Reclamo automático → Pasa a una persona \(R1\): 20\./)).toBeTruthy());
  });
});
