// Tipos que reflejan docs/api-contract.md (fuente de verdad). Montos como string decimal; nunca float.

export type Lang = "es" | "pt";
export type Role = "customer" | "analyst" | "admin";
export type ConversationState =
  | "inicio"
  | "aclarando"
  | "confirmando_movimiento"
  | "confirmando_accion"
  | "ejecutando"
  | "cerrado"
  | "escalado";

export interface SessionInfo {
  role: Role;
  display_name: string;
  language: Lang | null;
  expires_at: string;
  idle_timeout_minutes: number;
}

export interface LoginResponse extends SessionInfo {
  csrf_token: string;
}

export interface DataAsOf {
  data_as_of: string | null;
  max_transaction_date: string | null;
}

/** Movimiento tal como lo muestra la UI (candidate_list, transaction_card, transaction_list, /api/me/transactions). */
export interface TxView {
  transaction_id: string;
  date: string;
  amount: string;
  currency: string;
  merchant_name: string | null;
  label: string;
  channel: string | null;
  type: string | null;
  status: string;
  rank?: number;
  amount_label: string;
  date_label: string;
  status_label: string;
}

export type ActionType =
  | "select_candidate"
  | "select_candidates"
  | "select_card"
  | "dispute_transaction"
  | "confirm"
  | "reject"
  | "request_human"
  | "new_request"
  | "end_conversation";

export interface Action {
  type: ActionType;
  transaction_id?: string;
  transaction_ids?: string[];
  product_id?: string;
  confirmation_token?: string;
}

export interface TextBlock {
  type: "text";
  text: string;
}
export interface CandidateListBlock {
  type: "candidate_list";
  prompt: string;
  candidates: TxView[];
  allow_none: boolean;
  round: number;
  max_rounds: number;
  multi_select?: boolean;
  suggested?: string[];
  select_all_label?: string;
}
export interface TransactionListBlock {
  type: "transaction_list";
  period: { from: string; to: string };
  filters: Record<string, unknown>;
  count: number;
  totals: { currency: string; count: number; total: string; total_label?: string }[];
  transactions: TxView[];
  can_dispute: boolean;
}
export interface CardListBlock {
  type: "card_list";
  cards: { product_id: string; label: string; product_type: string; status: string }[];
}
export interface CaseListBlock {
  type: "case_list";
  cases: {
    case_id: string;
    /** referencia corta para el cliente (RCL-XXXXXX); el ID interno queda para la traza y la consola */
    reference_label?: string;
    status: string;
    reason_code: string;
    created_at: string;
    transaction: { label: string; amount: string | null; currency: string | null; date: string | null; amount_label?: string | null; date_label?: string | null };
  }[];
}
export interface TransactionCardBlock {
  type: "transaction_card";
  transaction: TxView;
  source: string;
}
export interface ActionConfirmationBlock {
  type: "action_confirmation";
  action: "create_dispute_case" | "lock_card" | "create_handoff";
  summary: string;
  params: Record<string, unknown>;
  confirmation_token: string;
  expires_at: string;
  disclaimer: string;
}
export interface ResultItem {
  transaction_id: string;
  reference_id: string | null;
  reference_label?: string | null;
  status: "success" | "failed";
  verified: boolean;
  label: string;
}
export interface ResultBlock {
  type: "result";
  action: string;
  status: "success" | "partial" | "failed";
  verified: boolean;
  reference_id: string | null;
  reference_label?: string | null;
  details: unknown;
  items?: ResultItem[];
}
export interface HandoffNoticeBlock {
  type: "handoff_notice";
  handoff_id: string;
  reference_label?: string;
  reason_code: string;
  message: string;
  next_step?: string;
}
export interface NoticeBlock {
  type: "notice";
  level: "info" | "warning";
  code: string;
  text: string;
}
export interface ErrorBlock {
  type: "error";
  code: string;
  message: string;
  retryable: boolean;
}
export interface QuickRepliesBlock {
  type: "quick_replies";
  options: { label: string; action: Action }[];
}

/** Enlace externo (p. ej. la página inicial del banco tras un out_of_scope). */
export interface LinkBlock {
  type: "link";
  label: string;
  url: string;
}

/** Fase real del turno en curso (GET /api/conversations/{id}/phase). */
export type TurnPhase = "understanding" | "searching_transactions" | "checking_policy" | "writing";

export type Block =
  | TextBlock
  | LinkBlock
  | CandidateListBlock
  | TransactionListBlock
  | CardListBlock
  | CaseListBlock
  | TransactionCardBlock
  | ActionConfirmationBlock
  | ResultBlock
  | HandoffNoticeBlock
  | NoticeBlock
  | ErrorBlock
  | QuickRepliesBlock;

export interface NewConversationResponse {
  conversation_id: string;
  state: ConversationState;
  language: Lang;
  session_date: string;
  blocks: Block[];
  data_as_of: DataAsOf;
  previous_conversation_id: string | null;
  focus: boolean;
}

export interface TurnResponse {
  turn_id: string;
  conversation_id: string;
  state: ConversationState;
  language: Lang;
  clarification_round: number;
  input: { message?: string; action?: Action };
  blocks: Block[];
  data_as_of: DataAsOf;
  trace_id: string;
  replayed?: boolean;
}

export interface MyTransactions {
  period: { from: string; to: string };
  session_date: string;
  filters: { merchant: string | null; status: string | null };
  count: number;
  totals: { currency: string; count: number; total: string; total_label: string }[];
  transactions: TxView[];
  data_as_of: DataAsOf;
}

export interface MyCases {
  cases: {
    case_id: string;
    /** referencia corta para el cliente (RCL-XXXXXX); el ID interno queda para la traza y la consola */
    reference_label?: string;
    status: string;
    reason_code: string;
    created_at: string;
    transaction: {
      transaction_id: string;
      label: string;
      amount: string | null;
      currency: string | null;
      date: string | null;
      amount_label: string | null;
      date_label: string | null;
    };
  }[];
}

// ---- consola (analyst)
export interface CaseSummary {
  case_id: string;
  customer_id: string;
  transaction_id: string;
  status: string;
  created_at: string;
}
export interface HandoffSummary {
  handoff_id: string;
  conversation_id: string;
  customer_id: string;
  reason_code: string;
  priority: string;
  queue: string;
  status: string;
  language: Lang;
  created_at: string;
}
export interface Handoff {
  handoff_id: string;
  created_at: string;
  conversation_id: string;
  trace_turn_ids: string[];
  customer_ref: Record<string, unknown>;
  language: Lang;
  reason_code: string;
  priority: string;
  queue: string;
  request: string;
  customer_claims: { claim: string; turn_id: string }[];
  verified_facts: { fact: string; value: unknown; source_tool: string; tool_call_id?: string }[];
  candidate_transactions?: unknown[];
  policy_evaluations: Record<string, unknown>[];
  actions_taken: { action: string; status: string; verified: boolean; reference_id: string | null }[];
  open_questions: string[];
  summary: string;
  summary_model?: Record<string, unknown>;
  status: string;
}
export interface TraceStep {
  step_seq: number;
  node: string;
  kind: "llm" | "ml" | "code";
  implementation: string | null;
  tool: string | null;
  model: string | null;
  model_id: string | null;
  prompt_version: string | null;
  latency_ms: number | null;
  cost_usd: string | number | null;
  payload: Record<string, unknown> | null;
  rules: Record<string, unknown>[] | null;
  error: string | null;
}
export interface Trace {
  turn_id: string;
  conversation_id: string;
  state_before: string | null;
  state_after: string;
  steps: TraceStep[];
  totals: { latency_ms: number; cost_usd: string };
}
export interface ConversationDetail {
  conversation_id: string;
  customer_id?: string;
  state: ConversationState;
  language: Lang;
  turns: { turn_id: string; seq: number; role: string; message: string | null; action: Action | null; blocks: Block[] }[];
}

// ---- voz y valoración (prompt 08, A2 y A3)
export interface VoiceConfig {
  enabled: boolean;
  reason: "voice_disabled" | "voice_not_configured" | null;
  max_audio_bytes: number;
  max_tts_chars: number;
  audio_types: string[];
}
export type FeedbackCategory = "no_me_entendio" | "respuesta_incorrecta" | "lento" | "otro";
export interface FeedbackBody {
  rating: "up" | "down";
  category: FeedbackCategory | null;
  comment: string | null;
}

// ---- historial del cliente (prompt 08, A1)
export interface ConversationSummary {
  conversation_id: string;
  created_at: string;
  updated_at: string;
  closed_at: string | null;
  state: ConversationState;
  closed_reason: "cliente" | "inactividad" | null;
  language: Lang;
  intent: string | null;
  outcomes: string[];
  references: string[];
  summary: string;
  customer_turns: number;
  previous_conversation_id: string | null;
}
export interface MyConversations {
  conversations: ConversationSummary[];
  next_cursor: string | null;
}
export interface HistoryTurn {
  turn_id: string;
  seq: number;
  role: string;
  message: string | null;
  action: Action | null;
  blocks: Block[];
  state_after: ConversationState;
  created_at: string;
}
export interface MyConversationDetail extends ConversationSummary {
  turns: HistoryTurn[];
}

// ---- tickets de los agentes de soporte (prompt 08, A4)
export type TicketStatus = "nuevo" | "en_curso" | "esperando_cliente" | "resuelto";
export type TicketPriority = "urgente" | "alta" | "media";
export type SlaState = "a_tiempo" | "por_vencer" | "vencido" | "cumplido" | "incumplido";
export interface Ticket {
  ticket_id: string;
  reference_label: string;
  conversation_id: string;
  customer_id: string;
  language: Lang;
  reason_code: string;
  priority: TicketPriority;
  queue: string;
  status: TicketStatus;
  assignee: { user_id: string; username: string } | null;
  created_at: string;
  updated_at: string;
  first_response_at: string | null;
  resolved_at: string | null;
  age_minutes: number;
  summary: string;
  sla: { target_hours: number; due_at: string; state: SlaState };
}
export interface TicketEvent {
  event_id: number | string;
  actor_username: string;
  kind: string;
  from_value: string | null;
  to_value: string | null;
  note: string | null;
  created_at: string;
}
export interface TicketDetail extends Ticket {
  handoff: Handoff;
  events: TicketEvent[];
}
export interface TicketList {
  tickets: Ticket[];
  total: number;
  by_status: Record<TicketStatus, number>;
  sla_hours: Record<TicketPriority, number>;
  assumption: string;
}

// ---- panel de administración (prompt 08, A5)
export interface Share { n: number; of: number; share: number }
export interface AdminOutcomes {
  days: number;
  conversations: number;
  resolved_automatically: Share;
  resolved_after_clarification: Share;
  escalated: Share;
  no_action: Share;
  handoffs: { reason_code: string; priority: string; n: number }[];
}
export interface AdminOverview {
  days: number;
  endpoints: { method: string; route: string; requests: number; errors_4xx: number; errors_5xx: number; rate_limited: number; latency_ms_p50: number | null; latency_ms_p95: number | null }[];
  nodes: { node: string; kind: "llm" | "ml" | "code"; calls: number; errors: number; p50_ms: number | null; p95_ms: number | null; cost_usd: number }[];
  recent_conversations: { conversation_id: string; created_at: string; updated_at: string; state: string; language: Lang; intent: string | null; customer_turns: number; has_case: boolean; has_handoff: boolean; feedback: "up" | "down" | null }[];
  outcomes: AdminOutcomes;
  llm_cost_daily: { day: string; calls: number; errors: number; cost_usd: number }[];
  voice_cost_daily: { day: string; cost_usd: number; [k: string]: unknown }[];
  budget: { today_calls: number; today_cost_usd: number; daily_calls_limit: number; daily_cost_limit_usd: number; cost_consumed: number; calls_consumed: number };
  note?: string;
}
export interface Slo {
  id: string;
  description: string;
  objective: number;
  window_days?: number;
  window?: string;
  target: Record<string, number>;
  current: Record<string, number | null>;
  met: boolean;
  error_budget: { events: number; bad_events: number; allowed_bad_events: number; consumed: number; remaining_bad_events: number };
  violations: { at: string; [k: string]: unknown }[];
  note?: string;
}
export interface AdminSlo { slos: Slo[]; assumption: string }
export interface LogEvent {
  ts: string;
  level: string;
  logger?: string;
  event: string;
  request_id?: string;
  conversation_id?: string;
  turn_id?: string;
  method?: string;
  route?: string;
  status?: number;
  latency_ms?: number;
  [k: string]: unknown;
}
export interface AdminLogs { events: LogEvent[]; kept: number; note: string }
export interface AdminRoi {
  label: string;
  assumptions: Record<string, number>;
  estimate: { human_cost_per_case_usd: number; saving_per_case_usd: number; monthly_saving_usd: number; break_even_cases_per_month: number };
  measured: { conversations: number; not_escalated_share: number; llm_cost_per_conversation_usd: number };
}
