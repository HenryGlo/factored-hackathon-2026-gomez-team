import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "../../api/client";
import type { ConversationSummary, MyConversationDetail } from "../../api/types";
import { SessionProvider } from "../../lib/session";
import ConversationPage from "../ConversationPage";
import ConversationsPage from "../ConversationsPage";

afterEach(() => { cleanup(); vi.restoreAllMocks(); sessionStorage.clear(); });

const conv = (id: string, over: Partial<ConversationSummary> = {}): ConversationSummary => ({
  conversation_id: id, created_at: "2026-06-17T10:00:00+00:00", updated_at: "2026-06-17T10:05:00+00:00", closed_at: "2026-06-17T10:05:00+00:00",
  state: "cerrado", closed_reason: "cliente", language: "es", intent: "cargo_no_reconocido", outcomes: ["reclamo"], references: ["RCL-3F9A1C"],
  summary: `Reclamo ${id}`, customer_turns: 3, previous_conversation_id: null, ...over,
});

function at(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <SessionProvider>
        <Routes>
          <Route path="/conversaciones" element={<ConversationsPage />} />
          <Route path="/conversaciones/:id" element={<ConversationPage />} />
          <Route path="/chat" element={<p>chat abierto</p>} />
        </Routes>
      </SessionProvider>
    </MemoryRouter>,
  );
}

describe("ConversationsPage", () => {
  it("lists conversations with summary, status and reference, and loads the next page with the cursor", async () => {
    const spy = vi.spyOn(api, "myConversations")
      .mockResolvedValueOnce({ conversations: [conv("conv_1")], next_cursor: "abc" })
      .mockResolvedValueOnce({ conversations: [conv("conv_2", { state: "inicio", closed_reason: null, outcomes: ["sin_accion"], references: [] })], next_cursor: null });
    at("/conversaciones");
    await screen.findByText("Reclamo conv_1");
    expect(screen.getByText("RCL-3F9A1C")).toBeTruthy();
    expect(screen.getByText("Cerrada por ti")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Cargar más" }));
    await screen.findByText("Reclamo conv_2");
    expect(spy.mock.calls[1][0]).toMatchObject({ cursor: "abc" });
    expect(screen.getByText("Abierta")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Cargar más" })).toBeNull();
  });
});

describe("ConversationPage", () => {
  const detail: MyConversationDetail = {
    ...conv("conv_1"),
    turns: [
      { turn_id: "t1", seq: 1, role: "assistant", message: null, action: null, blocks: [{ type: "text", text: "Hola, ¿en qué te ayudo?" }], state_after: "inicio", created_at: "2026-06-17T10:00:00+00:00" },
      { turn_id: "t2", seq: 2, role: "customer", message: "No reconozco un cobro", action: null, blocks: [], state_after: "inicio", created_at: "2026-06-17T10:01:00+00:00" },
      { turn_id: "t3", seq: 3, role: "assistant", message: null, action: null, state_after: "confirmando_accion", created_at: "2026-06-17T10:01:01+00:00",
        blocks: [{ type: "action_confirmation", action: "create_dispute_case", summary: "Voy a registrar un reclamo.", params: {}, confirmation_token: "tok", expires_at: "", disclaimer: "" }] },
    ],
  };

  it("shows the transcript read-only: old confirmation buttons cannot be used", async () => {
    vi.spyOn(api, "myConversation").mockResolvedValue(detail);
    at("/conversaciones/conv_1");
    await screen.findByText("No reconozco un cobro");
    expect((screen.getByRole("button", { name: "Confirmar" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("continues the topic in a new linked conversation and opens the chat", async () => {
    vi.spyOn(api, "myConversation").mockResolvedValue(detail);
    const create = vi.spyOn(api, "newConversation").mockResolvedValue({ conversation_id: "conv_new", state: "inicio", language: "es", session_date: "2026-06-18", blocks: [],
      data_as_of: { data_as_of: null, max_transaction_date: null }, previous_conversation_id: "conv_1", focus: true });
    at("/conversaciones/conv_1");
    fireEvent.click(await screen.findByRole("button", { name: "Continuar sobre este tema" }));
    await screen.findByText("chat abierto");
    expect(create).toHaveBeenCalledWith({ language: "es", previous_conversation_id: "conv_1" });
    expect(sessionStorage.getItem("conversation_id")).toBe("conv_new");
  });

  it("says not found for someone else's conversation (404)", async () => {
    vi.spyOn(api, "myConversation").mockRejectedValue(new ApiError(404, "not_found", "no", "req"));
    at("/conversaciones/conv_x");
    await waitFor(() => expect(screen.getByText("No encontramos esa conversación.")).toBeTruthy());
  });
});
