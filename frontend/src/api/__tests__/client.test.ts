import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, sendTurnLinked } from "../client";

function jsonResponse(status: number, body: unknown, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } });
}

afterEach(() => vi.restoreAllMocks());

describe("api client", () => {
  it("sends CSRF and Idempotency-Key on turns", async () => {
    document.cookie = "csrf_token=abc123";
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(200, { turn_id: "t1", blocks: [] }));
    await api.turn("conv_1", { message: "hola" }, "key-1");
    const [url, init] = spy.mock.calls[0] as [string, RequestInit];
    const h = init.headers as Record<string, string>;
    expect(url).toBe("/api/conversations/conv_1/turns");
    expect(h["X-CSRF-Token"]).toBe("abc123");
    expect(h["Idempotency-Key"]).toBe("key-1");
    expect(init.credentials).toBe("same-origin");
  });

  it("sends a start_topic action with its topic and nothing else", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(200, { turn_id: "t1", blocks: [] }));
    await api.turn("conv_1", { action: { type: "start_topic", topic: "estado_reclamo" } }, "key-2");
    const init = spy.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(init.body as string)).toEqual({ action: { type: "start_topic", topic: "estado_reclamo" } });
  });

  it("parses errors with request id, details and Retry-After", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(429,
      { error: { code: "rate_limited", message: "Demasiadas solicitudes", retryable: true, details: { rule: "turns_session" } } },
      { "X-Request-ID": "req-1", "Retry-After": "12" }));
    const err = await api.me().catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 429, code: "rate_limited", requestId: "req-1", retryAfter: 12, retryable: true });
    expect(err.details).toEqual({ rule: "turns_session" });
  });

  it("on a closed conversation creates a linked one and resends the message (no visible 409)", async () => {
    const spy = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(409, { error: { code: "conversation_closed", message: "cerrada", details: { reason: "cliente" } } }))
      .mockResolvedValueOnce(jsonResponse(201, { conversation_id: "conv_2", state: "inicio", language: "es", blocks: [] }))
      .mockResolvedValueOnce(jsonResponse(200, { turn_id: "t9", conversation_id: "conv_2", blocks: [] }));
    const res = await sendTurnLinked("conv_1", { message: "pero yo no lo hice" }, "es");
    expect(res.newConversation?.conversation_id).toBe("conv_2");
    expect(res.response.turn_id).toBe("t9");
    const created = JSON.parse((spy.mock.calls[1][1] as RequestInit).body as string);
    expect(created).toEqual({ language: "es", previous_conversation_id: "conv_1" });
    expect(spy.mock.calls[2][0]).toBe("/api/conversations/conv_2/turns");
  });

  it("does not relink actions: a closed conversation with an action is a real error", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(409, { error: { code: "conversation_closed", message: "cerrada" } }));
    await expect(sendTurnLinked("conv_1", { action: { type: "reject" } }, "es")).rejects.toMatchObject({ code: "conversation_closed" });
  });
});
