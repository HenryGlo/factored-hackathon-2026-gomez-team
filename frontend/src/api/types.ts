// Tipos que reflejan docs/api-contract.md (fuente de verdad). Montos como string decimal; nunca float.

export type Lang = "es" | "pt";
export type Role = "customer" | "analyst";
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
