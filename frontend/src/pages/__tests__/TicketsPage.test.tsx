import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client";
import type { Ticket, TicketDetail } from "../../api/types";
import { SessionProvider } from "../../lib/session";
import TicketPage from "../TicketPage";
import TicketsPage from "../TicketsPage";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

const ticket = (over: Partial<Ticket> = {}): Ticket => ({
  ticket_id: "hof_1", reference_label: "ATN-111AAA", conversation_id: "conv_1", customer_id: "C1", language: "es", reason_code: "riesgo_alto", priority: "urgente",
  queue: "fraude", status: "nuevo", assignee: null, created_at: "2026-06-18T10:00:00+00:00", updated_at: "2026-06-18T10:00:00+00:00", first_response_at: null,
  resolved_at: null, age_minutes: 50, summary: "Cargo de riesgo alto que el cliente no hizo.", sla: { target_hours: 1, due_at: "2026-06-18T11:00:00+00:00", state: "por_vencer" }, ...over,
});

function at(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <SessionProvider>
        <Routes>
          <Route path="/agentes" element={<TicketsPage />} />
          <Route path="/agentes/tickets/:id" element={<TicketPage />} />
        </Routes>
      </SessionProvider>
    </MemoryRouter>,
  );
}

describe("TicketsPage", () => {
  it("shows priority, SLA state and assignee, and sends the filters to the API", async () => {
    const spy = vi.spyOn(api, "tickets").mockResolvedValue({ tickets: [ticket()], total: 1, by_status: { nuevo: 1, en_curso: 0, esperando_cliente: 0, resuelto: 0 },
      sla_hours: { urgente: 1, alta: 4, media: 24 }, assumption: "supuestos" });
    at("/agentes");
    await screen.findByText("ATN-111AAA");
    expect(screen.getAllByText("Urgente").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Por vencer").length).toBeGreaterThan(0);
    expect(screen.getByText("Sin asignar", { selector: ".ticket-side span" })).toBeTruthy();
    expect(spy).toHaveBeenLastCalledWith(expect.objectContaining({ open: "true", sla: "" }));
    fireEvent.change(screen.getByLabelText("SLA"), { target: { value: "vencido" } });
    await waitFor(() => expect(spy).toHaveBeenLastCalledWith(expect.objectContaining({ sla: "vencido" })));
    fireEvent.change(screen.getByLabelText("Asignado"), { target: { value: "me" } });
    await waitFor(() => expect(spy).toHaveBeenLastCalledWith(expect.objectContaining({ assignee: "me" })));
  });
});

describe("TicketPage", () => {
  const detail: TicketDetail = {
    ...ticket(),
    events: [{ event_id: "e1", actor_username: "analista_2", kind: "nota", from_value: null, to_value: null, note: "Llamé al cliente", created_at: "2026-06-18T10:20:00+00:00" }],
    handoff: {
      handoff_id: "hof_1", created_at: "2026-06-18T10:00:00+00:00", conversation_id: "conv_1", trace_turn_ids: [], customer_ref: { display_name: "Ana G.", segment: "Plus", country: "México" },
      language: "es", reason_code: "riesgo_alto", priority: "urgente", queue: "fraude", request: "Disputa de un cargo no reconocido",
      customer_claims: [{ claim: "No hizo el cargo", turn_id: "t1" }], verified_facts: [{ fact: "monto", value: "120.00 USD", source_tool: "get_transaction" }],
      policy_evaluations: [{ id: "R6", resultado: "escalar", motivo: "riesgo alto" }], actions_taken: [], open_questions: ["¿Se bloquea la tarjeta?"], summary: "Resumen del caso.", status: "pendiente",
    },
  };

  it("separates what the customer says from verified facts and lets the agent take the ticket and add a note", async () => {
    vi.spyOn(api, "ticket").mockResolvedValue(detail);
    vi.spyOn(api, "conversation").mockResolvedValue({ conversation_id: "conv_1", state: "inicio", language: "es", turns: [] });
    const assign = vi.spyOn(api, "ticketAssign").mockResolvedValue({});
    const note = vi.spyOn(api, "ticketNote").mockResolvedValue({});
    at("/agentes/tickets/hof_1");
    await screen.findByText("“No hizo el cargo”");
    expect(screen.getByText("120.00 USD")).toBeTruthy();
    expect(screen.getByText("¿Se bloquea la tarjeta?")).toBeTruthy();
    expect(screen.getByText("Llamé al cliente")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Tomar el ticket" }));
    await waitFor(() => expect(assign).toHaveBeenCalledWith("hof_1", "me"));
    fireEvent.change(await screen.findByLabelText("Agregar una nota interna"), { target: { value: " Reviso mañana " } });
    fireEvent.click(screen.getByRole("button", { name: "Agregar nota" }));
    await waitFor(() => expect(note).toHaveBeenCalledWith("hof_1", "Reviso mañana"));
  });
});
