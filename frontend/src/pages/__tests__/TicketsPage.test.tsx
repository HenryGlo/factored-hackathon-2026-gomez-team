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

  it("keeps the conversation, the reasoning and the traces locked until the agent takes the ticket, with a single take button", async () => {
    vi.spyOn(api, "ticket").mockResolvedValue({ ...detail, assigned_to_me: false });
    const conversation = vi.spyOn(api, "conversation");
    const reasoning = vi.spyOn(api, "ticketReasoning");
    at("/agentes/tickets/hof_1");
    await screen.findByText("La conversación se abre al tomar el ticket");
    expect(screen.getByText("Resumen del caso.")).toBeTruthy();                       // el resumen basta para decidir
    expect(screen.getAllByRole("button", { name: /Tomar/ })).toHaveLength(1);         // un solo botón para tomarlo
    expect(screen.queryByText("Cómo decidió Banky en cada mensaje")).toBeNull();
    expect(screen.queryByRole("log")).toBeNull();
    expect(conversation).not.toHaveBeenCalled();
    expect(reasoning).not.toHaveBeenCalled();
  });

  it("lets the author delete their note after confirming, and shows a deleted note without its text", async () => {
    const mineNote = { event_id: "e2", actor_username: "analista_1", kind: "nota", from_value: null, to_value: null, note: "Nota mía", created_at: "2026-06-18T10:30:00+00:00", can_delete: true };
    const deleted = { event_id: "e3", actor_username: "analista_1", kind: "nota", from_value: null, to_value: null, note: null, created_at: "2026-06-18T10:40:00+00:00",
      deleted_at: "2026-06-18T10:45:00+00:00", deleted_by: "analista_1", can_delete: false };
    vi.spyOn(api, "ticket").mockResolvedValue({ ...detail, events: [...detail.events, mineNote, deleted] });
    const del = vi.spyOn(api, "ticketNoteDelete").mockResolvedValue({});
    at("/agentes/tickets/hof_1");
    await screen.findByText("Nota mía");
    expect(screen.getAllByRole("button", { name: "Borrar" })).toHaveLength(1);        // solo la propia y sin borrar
    expect(screen.getByText(/Nota borrada por analista_1/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Borrar" }));
    expect(del).not.toHaveBeenCalled();                                              // pide confirmación
    fireEvent.click(screen.getByRole("button", { name: "No" }));
    fireEvent.click(screen.getByRole("button", { name: "Borrar" }));
    fireEvent.click(screen.getByRole("button", { name: "Sí, borrar" }));
    await waitFor(() => expect(del).toHaveBeenCalledWith("hof_1", "e2"));
  });

  it("says who handles the ticket when it belongs to another agent", async () => {
    vi.spyOn(api, "ticket").mockResolvedValue({ ...detail, assignee: { user_id: "usr_a2", username: "analista_2" }, assigned_to_me: false });
    at("/agentes/tickets/hof_1");
    await screen.findByText("La conversación la ve analista_2, que atiende este ticket");
    expect(screen.getAllByRole("button", { name: /Tomar/ })).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Tomarlo yo" })).toBeTruthy();
  });

  it("opens everything for the agent who holds the ticket and offers to release it instead of taking it", async () => {
    vi.spyOn(api, "ticket").mockResolvedValue({ ...detail, assignee: { user_id: "usr_a1", username: "analista_1" }, assigned_to_me: true });
    const conversation = vi.spyOn(api, "conversation").mockResolvedValue({ conversation_id: "conv_1", state: "inicio", language: "es", turns: [] });
    const reasoning = vi.spyOn(api, "ticketReasoning").mockResolvedValue({ ticket_id: "hof_1", conversation_id: "conv_1", turns: [], note: "" });
    at("/agentes/tickets/hof_1");
    await screen.findByText("Cómo decidió Banky en cada mensaje");
    await waitFor(() => expect(conversation).toHaveBeenCalledWith("conv_1"));
    expect(reasoning).toHaveBeenCalledWith("hof_1");
    expect(screen.queryByRole("button", { name: /Tomar/ })).toBeNull();
    expect(screen.getByRole("button", { name: "Liberar" })).toBeTruthy();
    expect(screen.queryByText("La conversación se abre al tomar el ticket")).toBeNull();
  });
});
