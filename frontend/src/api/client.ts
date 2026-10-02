// Cliente HTTP de la API. Misma origen (proxy de Vite en desarrollo): la cookie de sesión es httpOnly y el CSRF va de la
// cookie legible csrf_token a la cabecera X-CSRF-Token (doble envío). Ver docs/api-contract.md.
import type {
  Action,
  AdminLogs,
  AdminOverview,
  AdminRoi,
  AdminSlo,
  CaseSummary,
  FeedbackBody,
  ConversationDetail,
  DemoInfo,
  Handoff,
  HandoffSummary,
  Lang,
  LoginResponse,
  MyCases,
  MyConversationDetail,
  MyConversations,
  MyTransactions,
  NewConversationResponse,
  SessionInfo,
  TicketDetail,
  TicketList,
  Trace,
  TurnPhase,
  TurnResponse,
  VoiceConfig,
  VoiceTranscript,
} from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public requestId: string | null,
    public retryable = false,
    public details: Record<string, unknown> | null = null,
    public retryAfter: number | null = null,
  ) {
    super(message);
  }
}

export function readCookie(name: string): string {
  const m = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return m ? decodeURIComponent(m[1]) : "";
}

export function newIdempotencyKey(): string {
  return crypto.randomUUID();
}

async function send(method: "GET" | "POST", path: string, body: BodyInit | undefined, headers: Record<string, string>): Promise<Response> {
  if (method === "POST") headers["X-CSRF-Token"] = readCookie("csrf_token");
  let res: Response;
  try {
    res = await fetch(path, { method, headers, credentials: "same-origin", body });
  } catch {
    throw new ApiError(0, "network_error", "network", null, true);
  }
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    const err = data?.error ?? {};
    const retryAfter = res.headers.get("Retry-After");
    throw new ApiError(res.status, err.code ?? "http_error", err.message ?? `HTTP ${res.status}`, res.headers.get("X-Request-ID"), Boolean(err.retryable),
      err.details ?? null, retryAfter ? Number(retryAfter) : null);
  }
  return res;
}

async function request<T>(method: "GET" | "POST", path: string, body?: unknown, extraHeaders: Record<string, string> = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json", ...extraHeaders };
  if (method === "POST") headers["Content-Type"] = "application/json";
  const res = await send(method, path, body === undefined ? undefined : JSON.stringify(body), headers);
  if (res.status === 204) return undefined as T;
  return (await res.json().catch(() => null)) as T;
}

/** Un mensaje (con `via: "voice"` si es una transcripción revisada por el cliente) o una acción. */
export type TurnBody = { message: string; via?: "voice" } | { action: Action };

export const api = {
  csrf: () => request<unknown>("GET", "/api/auth/csrf"),
  login: async (username: string, password: string, language?: Lang) => {
    await api.csrf();
    return request<LoginResponse>("POST", "/api/auth/login", { username, password, ...(language ? { language } : {}) });
  },
  logout: () => request<void>("POST", "/api/auth/logout"),
  me: () => request<SessionInfo>("GET", "/api/auth/me"),
  demoInfo: () => request<DemoInfo>("GET", "/api/demo/info"),

  newConversation: (body: { language?: Lang; previous_conversation_id?: string; dispute_transaction_id?: string }) =>
    request<NewConversationResponse>("POST", "/api/conversations", body, { "Idempotency-Key": newIdempotencyKey() }),
  turn: (conversationId: string, body: TurnBody, idempotencyKey = newIdempotencyKey()) =>
    request<TurnResponse>("POST", `/api/conversations/${encodeURIComponent(conversationId)}/turns`, body, { "Idempotency-Key": idempotencyKey }),
  conversation: (id: string) => request<ConversationDetail>("GET", `/api/conversations/${encodeURIComponent(id)}`),
  feedback: (id: string, body: FeedbackBody) => request<{ feedback_id: string }>("POST", `/api/conversations/${encodeURIComponent(id)}/feedback`, body),
  voiceConfig: () => request<VoiceConfig>("GET", "/api/voice/config"),
  /** Audio → texto. Solo transcribe: el texto se muestra, se puede corregir y se envía como un turno normal con via: "voice". */
  voiceStt: async (audio: Blob, language: Lang) => {
    const res = await send("POST", `/api/voice/stt?language=${language}`, audio, { Accept: "application/json", "Content-Type": audio.type.split(";")[0] || "audio/webm" });
    return (await res.json()) as VoiceTranscript;
  },
  /** Lee en voz alta un turno del asistente (no acepta texto libre). */
  voiceTts: async (conversationId: string, turnId: string) => {
    const res = await send("POST", "/api/voice/tts", JSON.stringify({ conversation_id: conversationId, turn_id: turnId }), { Accept: "audio/mpeg", "Content-Type": "application/json" });
    return res.blob();
  },
  phase: (id: string) => request<{ phase: TurnPhase | null }>("GET", `/api/conversations/${encodeURIComponent(id)}/phase`),

  myTransactions: (q: { from?: string; to?: string; merchant?: string; status?: string; lang?: Lang }) => {
    const p = new URLSearchParams(Object.entries(q).filter(([, v]) => v) as [string, string][]);
    return request<MyTransactions>("GET", `/api/me/transactions?${p}`);
  },
  myCases: (lang?: Lang) => request<MyCases>("GET", `/api/me/cases${lang ? `?lang=${lang}` : ""}`),

  myConversations: (q: { cursor?: string | null; lang?: Lang; limit?: number }) => {
    const p = new URLSearchParams({ limit: String(q.limit ?? 20), ...(q.cursor ? { cursor: q.cursor } : {}), ...(q.lang ? { lang: q.lang } : {}) });
    return request<MyConversations>("GET", `/api/me/conversations?${p}`);
  },
  myConversation: (id: string, lang?: Lang) =>
    request<MyConversationDetail>("GET", `/api/me/conversations/${encodeURIComponent(id)}${lang ? `?lang=${lang}` : ""}`),

  cases: (status?: string) => request<CaseSummary[]>("GET", `/api/cases${status ? `?status=${encodeURIComponent(status)}` : ""}`),
  handoffs: (q: { status?: string; queue?: string }) => {
    const p = new URLSearchParams(Object.entries(q).filter(([, v]) => v) as [string, string][]);
    return request<HandoffSummary[]>("GET", `/api/handoffs?${p}`);
  },
  handoff: (id: string) => request<Handoff>("GET", `/api/handoffs/${encodeURIComponent(id)}`),
  tickets: (q: { status?: string; priority?: string; assignee?: string; sla?: string; open?: string }) => {
    const p = new URLSearchParams(Object.entries(q).filter(([, v]) => v) as [string, string][]);
    return request<TicketList>("GET", `/api/tickets?${p}`);
  },
  ticket: (id: string) => request<TicketDetail>("GET", `/api/tickets/${encodeURIComponent(id)}`),
  ticketAssign: (id: string, assignee: string | null) => request<unknown>("POST", `/api/tickets/${encodeURIComponent(id)}/assign`, { assignee }),
  ticketStatus: (id: string, status: string) => request<unknown>("POST", `/api/tickets/${encodeURIComponent(id)}/status`, { status }),
  ticketNote: (id: string, note: string) => request<unknown>("POST", `/api/tickets/${encodeURIComponent(id)}/notes`, { note }),
  adminOverview: (days = 7) => request<AdminOverview>("GET", `/api/admin/overview?days=${days}`),
  adminSlo: () => request<AdminSlo>("GET", "/api/admin/slo"),
  adminLogs: (q: { request_id?: string; conversation_id?: string; level?: string; route?: string; limit?: string }) => {
    const p = new URLSearchParams(Object.entries(q).filter(([, v]) => v) as [string, string][]);
    return request<AdminLogs>("GET", `/api/admin/logs?${p}`);
  },
  adminRoi: (days = 30) => request<AdminRoi>("GET", `/api/admin/metrics/roi?days=${days}`),
  trace: (turnId: string) => request<Trace>("GET", `/api/traces/${encodeURIComponent(turnId)}`),
};

/**
 * Envía un turno. Si la conversación se cerró (despedida o inactividad), crea una conversación ENLAZADA
 * (previous_conversation_id: hereda el cargo en foco) y reenvía el mensaje: el cliente no ve el 409.
 */
export async function sendTurnLinked(
  conversationId: string,
  body: TurnBody,
  language: Lang,
): Promise<{ response: TurnResponse; newConversation: NewConversationResponse | null }> {
  try {
    return { response: await api.turn(conversationId, body), newConversation: null };
  } catch (e) {
    if (e instanceof ApiError && e.status === 409 && e.code === "conversation_closed" && "message" in body) {
      const conv = await api.newConversation({ language, previous_conversation_id: conversationId });
      return { response: await api.turn(conv.conversation_id, body), newConversation: conv };
    }
    throw e;
  }
}
