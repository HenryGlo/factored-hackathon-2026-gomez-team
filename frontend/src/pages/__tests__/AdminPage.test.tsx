import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client";
import type { AdminOverview, AdminSlo } from "../../api/types";
import { SessionProvider } from "../../lib/session";
import AdminPage from "../AdminPage";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

const share = (n: number, of: number) => ({ n, of, share: n / of });
const overview: AdminOverview = {
  days: 7,
  endpoints: [{ method: "POST", route: "/api/conversations/{id}/turns", requests: 40, errors_4xx: 1, errors_5xx: 0, rate_limited: 2, latency_ms_p50: 900, latency_ms_p95: 4200 }],
  nodes: [{ node: "intent", kind: "llm", calls: 30, errors: 0, p50_ms: 400, p95_ms: 1200, cost_usd: 0.0123 }],
  recent_conversations: [{ conversation_id: "conv_1", created_at: "2026-06-18T10:00:00+00:00", updated_at: "2026-06-18T10:05:00+00:00", state: "cerrado", language: "es",
    intent: "cargo_no_reconocido", customer_turns: 3, has_case: true, has_handoff: false, feedback: "down" }],
  outcomes: { days: 7, conversations: 20, resolved_automatically: share(12, 20), resolved_after_clarification: share(3, 20), escalated: share(4, 20), no_action: share(1, 20),
    handoffs: [{ reason_code: "riesgo_alto", priority: "urgente", n: 4 }] },
  llm_cost_daily: [{ day: "2026-06-18", calls: 90, errors: 1, cost_usd: 0.61 }],
  voice_cost_daily: [],
  budget: { today_calls: 90, today_cost_usd: 0.61, daily_calls_limit: 3000, daily_cost_limit_usd: 5, cost_consumed: 0.122, calls_consumed: 0.03 },
};
const slo: AdminSlo = {
  assumption: "supuestos del equipo",
  slos: [
    { id: "turn_latency", description: "p95 del turno por debajo de 6 s", objective: 0.95, window_days: 7, target: { p95_ms: 6000 }, current: { p95_ms: 7400 }, met: false,
      error_budget: { events: 100, bad_events: 9, allowed_bad_events: 5, consumed: 1.8, remaining_bad_events: 0 }, violations: [{ at: "2026-06-18T09:00:00+00:00", turn_id: "turn_9" }] },
    { id: "availability", description: "Respuestas sin 5xx", objective: 0.995, window: "desde el arranque", target: { success_share: 0.995 }, current: { success_share: 1 }, met: true,
      error_budget: { events: 400, bad_events: 0, allowed_bad_events: 2, consumed: 0, remaining_bad_events: 2 }, violations: [] },
  ],
};

describe("AdminPage", () => {
  it("shows SLOs with error budget and violations, outcomes with n/N, cost against the budget and searchable logs", async () => {
    vi.spyOn(api, "adminOverview").mockResolvedValue(overview);
    vi.spyOn(api, "adminSlo").mockResolvedValue(slo);
    vi.spyOn(api, "adminRoi").mockResolvedValue({ label: "estimación con supuestos del equipo", assumptions: {}, estimate: { human_cost_per_case_usd: 1.35, saving_per_case_usd: 1.07,
      monthly_saving_usd: 10214, break_even_cases_per_month: 478 }, measured: { conversations: 20, not_escalated_share: 0.8, llm_cost_per_conversation_usd: 0.007 } });
    vi.spyOn(api, "adminImprovements").mockResolvedValue({ source: "github.com/x", unavailable: null, reports: [{ date: "2026-10-01", path: "reports/improve-20261001.md",
      report_url: "https://github.com/x/blob/improve/20261001/reports/improve-20261001.md", proposed_cases: 8, prompt_changes: 2, llm: "claude_cli",
      patterns: [{ title: "Cargo no reconocido coloquial se clasifica como fuera de alcance", evidence: "2/5", actionable: true }],
      pr_url: "https://github.com/x/pull/48", pr_number: 48, pr_state: "draft", pr_title: "test(eval): improvement-loop proposal 20261001" }] });
    const logs = vi.spyOn(api, "adminLogs").mockResolvedValue({ events: [{ ts: "2026-06-18T10:00:00.123+00:00", level: "error", event: "http_request", route: "/api/x", status: 500, request_id: "req_abc" }], kept: 1, note: "búfer" });
    render(<MemoryRouter><SessionProvider><AdminPage /></SessionProvider></MemoryRouter>);

    await screen.findByText("Latencia del turno");
    expect(screen.getByText("No cumple")).toBeTruthy();
    expect(screen.getByText("Cumple")).toBeTruthy();
    expect(screen.getByText("p95 7400 ms")).toBeTruthy();
    expect(screen.getByText("9 eventos malos de 5 permitidos (100 eventos)")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "1 violación" }));
    expect(screen.getByText("turn_id=turn_9")).toBeTruthy();

    await screen.findByText(/12\/20/);                                   // resultados con n/N
    expect(screen.getByText(/\$0\.6100 \/ \$5\.00/)).toBeTruthy();       // costo frente al presupuesto
    expect(screen.getAllByRole("tab").map((x) => x.textContent)).toEqual(["Operación", "Rendimiento", "Decisiones", "Herramientas", "Mejora y ROI"]);
    expect(screen.queryByText("req_abc")).toBeNull();                    // cada sección en su pestaña
    fireEvent.click(screen.getByRole("tab", { name: "Mejora y ROI" }));
    expect(screen.getByText("estimación con supuestos del equipo")).toBeTruthy();
    // mejora continua con datos reales: patrones con su evidencia n/N, casos y cambios propuestos, y el PR con su estado
    await screen.findByText("Cargo no reconocido coloquial se clasifica como fuera de alcance");
    expect(screen.getByText("2/5")).toBeTruthy();
    expect(screen.getByText("8 casos de prueba propuestos · 2 cambios de prompt propuestos · Analizado con", { exact: false })).toBeTruthy();
    expect(screen.getByText("Borrador")).toBeTruthy();
    expect(screen.getByRole("link", { name: /PR #48/ }).getAttribute("href")).toBe("https://github.com/x/pull/48");
    expect(screen.getByRole("link", { name: /PR #48/ }).getAttribute("rel")).toBe("noopener noreferrer");
    expect(screen.queryByText("Latencia del turno")).toBeNull();
    fireEvent.click(screen.getByRole("tab", { name: "Rendimiento" }));
    await screen.findByText("req_abc");

    fireEvent.change(screen.getByLabelText("Código de referencia (request_id)"), { target: { value: "req_abc" } });
    fireEvent.click(screen.getByRole("button", { name: "Buscar" }));
    await waitFor(() => expect(logs).toHaveBeenLastCalledWith(expect.objectContaining({ request_id: "req_abc" })));
  });

  it("says clearly when the reports are not available (it is not an error)", async () => {
    vi.spyOn(api, "adminOverview").mockResolvedValue(overview);
    vi.spyOn(api, "adminSlo").mockResolvedValue(slo);
    vi.spyOn(api, "adminRoi").mockRejectedValue(new Error("x"));
    vi.spyOn(api, "adminLogs").mockResolvedValue({ events: [], kept: 0, note: "" });
    vi.spyOn(api, "adminImprovements").mockResolvedValue({ reports: [], source: "github.com/x", unavailable: "github_private_or_not_found" });
    render(<MemoryRouter initialEntries={["/admin?seccion=mejora"]}><SessionProvider><AdminPage /></SessionProvider></MemoryRouter>);
    expect(await screen.findByText(/el repositorio es privado para este entorno/)).toBeTruthy();
    expect(document.querySelector("#adm-improve")?.closest("section")?.querySelector('[role="alert"]')).toBeNull();
  });
});
