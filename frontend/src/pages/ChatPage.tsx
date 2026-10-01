import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api, ApiError, newIdempotencyKey, sendTurnLinked } from "../api/client";
import type { Action, Block, ConversationDetail, ConversationState, DataAsOf, Lang, TurnResponse } from "../api/types";
import BlockView from "../components/blocks/BlockView";
import ErrorNote from "../components/ErrorNote";
import ThinkingIndicator, { useTurnPhase } from "../components/ThinkingIndicator";
import { T } from "../lib/i18n";
import { describeError, useSession } from "../lib/session";

const MAX_CHARS = 2000;
const STORE_KEY = "conversation_id";

interface Message {
  id: string;
  role: "customer" | "assistant" | "system";
  text?: string;
  blocks?: Block[];
  state?: ConversationState;
}

type Body = { message: string } | { action: Action };

function fromDetail(d: ConversationDetail): Message[] {
  return d.turns.map((t) => (t.role === "customer"
    ? { id: t.turn_id, role: "customer", text: t.message ?? actionLabel(t.action) }
    : { id: t.turn_id, role: "assistant", blocks: t.blocks, state: d.state }));
}

function actionLabel(a: Action | null): string {
  if (!a) return "";
  return a.type === "confirm" ? "✓" : a.type === "reject" ? "✗" : "•";
}

export default function ChatPage() {
  const { lang: uiLang, onUnauthorized } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const routeState = location.state as { disputeTransactionId?: string } | null;
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [lang, setLang] = useState<Lang>(uiLang);
  const [state, setState] = useState<ConversationState>("inicio");
  const [messages, setMessages] = useState<Message[]>([]);
  const [dataAsOf, setDataAsOf] = useState<DataAsOf | null>(null);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<{ message: string; requestId: string | null; retry?: () => void } | null>(null);
  const [cooldown, setCooldown] = useState(0);
  const t = T[lang];
  const phase = useTurnPhase(conversationId, sending);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const started = useRef(false);

  const handleError = useCallback((e: unknown, retry?: () => void) => {
    if (e instanceof ApiError && e.status === 401) {
      onUnauthorized();
      navigate("/login");
      return;
    }
    if (e instanceof ApiError && e.code === "message_too_long") {
      setError({ message: t.tooLong(Number(e.details?.max_chars ?? MAX_CHARS)), requestId: e.requestId });
      return;
    }
    if (e instanceof ApiError && e.status === 429) {
      const s = e.retryAfter ?? 10;
      setCooldown(s);
      setError({ message: t.rateLimited(s), requestId: e.requestId, retry });
      return;
    }
    setError({ ...describeError(e, t), retry });
  }, [navigate, onUnauthorized, t]);

  const startConversation = useCallback(async (opts: { previous?: string; disputeTransactionId?: string } = {}) => {
    setError(null);
    const conv = await api.newConversation({ language: uiLang, previous_conversation_id: opts.previous, dispute_transaction_id: opts.disputeTransactionId });
    setConversationId(conv.conversation_id);
    sessionStorage.setItem(STORE_KEY, conv.conversation_id);
    setLang(conv.language);
    setState(conv.state);
    setDataAsOf(conv.data_as_of);
    setMessages([{ id: `greet-${conv.conversation_id}`, role: "assistant", blocks: conv.blocks, state: conv.state }]);
    return conv;
  }, [uiLang]);

  const applyTurn = useCallback((r: TurnResponse) => {
    setState(r.state);
    setLang(r.language);
    setDataAsOf(r.data_as_of);
    setMessages((m) => [...m, { id: r.turn_id, role: "assistant", blocks: r.blocks, state: r.state }]);
  }, []);

  const send = useCallback(async (body: Body, echo: string, convId = conversationId, key = newIdempotencyKey()) => {
    if (!convId || sending) return;
    setSending(true);
    setError(null);
    setMessages((m) => [...m, { id: `c-${key}`, role: "customer", text: echo }]);
    try {
      let r: TurnResponse;
      if ("message" in body) {
        const res = await sendTurnLinked(convId, body, lang);
        if (res.newConversation) {           // la conversación anterior se cerró: seguimos en una enlazada, sin error
          setConversationId(res.newConversation.conversation_id);
          sessionStorage.setItem(STORE_KEY, res.newConversation.conversation_id);
          setMessages((m) => [...m.slice(0, -1), { id: `sys-${key}`, role: "system", text: T[lang].continuedConversation }, m[m.length - 1]]);
        }
        r = res.response;
      } else {
        r = await api.turn(convId, body, key);
      }
      applyTurn(r);
    } catch (e) {
      setMessages((m) => m.filter((x) => x.id !== `c-${key}`));
      handleError(e, () => void send(body, echo, convId, key));   // reintento con la MISMA Idempotency-Key
    } finally {
      setSending(false);
    }
  }, [applyTurn, conversationId, handleError, lang, sending]);

  // arranque: disputa desde "Mis movimientos", conversación guardada, o una nueva
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    const dispute = routeState?.disputeTransactionId;
    (async () => {
      try {
        if (dispute) {
          navigate(location.pathname, { replace: true, state: {} });
          const conv = await startConversation({ disputeTransactionId: dispute });
          await send({ action: { type: "dispute_transaction", transaction_id: dispute } }, T[uiLang].disputeThis, conv.conversation_id);
          return;
        }
        const saved = sessionStorage.getItem(STORE_KEY);
        if (saved) {
          const d = await api.conversation(saved).catch(() => null);
          if (d && d.state !== "cerrado" && d.state !== "escalado") {
            setConversationId(d.conversation_id);
            setLang(d.language);
            setState(d.state);
            setMessages(fromDetail(d));
            return;
          }
        }
        await startConversation();
      } catch (e) {
        handleError(e, () => void startConversation().catch(handleError));
      }
    })();
  }, [handleError, location.pathname, routeState, navigate, send, startConversation, uiLang]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, sending]);

  useEffect(() => {
    if (cooldown <= 0) return;
    const id = setTimeout(() => setCooldown((s) => s - 1), 1000);
    return () => clearTimeout(id);
  }, [cooldown]);

  function submit(e?: FormEvent) {
    e?.preventDefault();
    const text = input.trim();
    if (!text || sending || cooldown > 0) return;
    if (text.length > MAX_CHARS) {
      setError({ message: t.tooLong(MAX_CHARS), requestId: null });
      return;
    }
    setInput("");
    void send({ message: text }, text);
  }

  function onKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant")?.id;
  const closed = state === "cerrado";

  return (
    <section className="chat" aria-label={t.navChat}>
      <div className="chat-head">
        {dataAsOf?.max_transaction_date && (
          <p className="muted small">{t.dataAsOf} {new Date(dataAsOf.max_transaction_date).toLocaleDateString(lang === "pt" ? "pt-BR" : "es")}</p>
        )}
        <div className="chat-tools">
          <button className="btn ghost small" disabled={sending} onClick={() => void send({ action: { type: "request_human" } }, t.humanHelp)}>{t.humanHelp}</button>
          <button className="btn ghost small" disabled={sending} onClick={() => void startConversation({ previous: conversationId ?? undefined }).catch(handleError)}>{t.newConversation}</button>
        </div>
      </div>

      <div className="messages" role="log" aria-live="polite" aria-relevant="additions" aria-busy={sending}>
        {messages.map((m) => (
          <div key={m.id} className={`msg ${m.role}`}>
            {m.role === "assistant" ? (
              <div className="bubble assistant">
                <span className="sr-only">{t.assistant}:</span>
                {(m.blocks ?? []).map((b, i) => (
                  <BlockView key={i} block={b} lang={lang} state={m.id === lastAssistant ? state : (m.state ?? state)}
                    active={m.id === lastAssistant && !sending && !closed && cooldown === 0}
                    onAction={(action, label) => void send({ action }, label)} />
                ))}
              </div>
            ) : m.role === "system" ? (
              <p className="system-note">{m.text}</p>
            ) : (
              <div className="bubble customer"><span className="sr-only">{t.you}:</span>{m.text}</div>
            )}
          </div>
        ))}
        {sending && <ThinkingIndicator phase={phase} label={phase === "searching_transactions" ? t.searching : t.typing} />}
        <div ref={endRef} />
      </div>

      {error && <ErrorNote message={error.message} requestId={error.requestId} label={t.reference}
        onRetry={error.retry && cooldown === 0 ? () => { const r = error.retry!; setError(null); r(); } : undefined} retryLabel={t.retry} />}

      <form className="composer" onSubmit={submit}>
        <label htmlFor="msg" className="sr-only">{t.messagePlaceholder}</label>
        <textarea id="msg" ref={inputRef} rows={1} value={input} placeholder={closed ? t.newConversation : t.messagePlaceholder}
          maxLength={MAX_CHARS} onChange={(e) => setInput(e.target.value)} onKeyDown={onKey} disabled={cooldown > 0}
          aria-describedby={input.length > MAX_CHARS - 200 ? "chars" : undefined} />
        <button className="btn primary" type="submit" disabled={!input.trim() || sending || cooldown > 0}>
          {cooldown > 0 ? `${cooldown}s` : t.send}
        </button>
        {input.length > MAX_CHARS - 200 && <span id="chars" className="muted small chars">{t.charsLeft(MAX_CHARS - input.length)}</span>}
      </form>
    </section>
  );
}
