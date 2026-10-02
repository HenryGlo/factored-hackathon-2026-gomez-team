import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api, ApiError, newIdempotencyKey, sendTurnLinked, type TurnBody } from "../api/client";
import type { Action, Block, ConversationDetail, ConversationState, DataAsOf, Lang, TurnResponse } from "../api/types";
import Banky, { stateForPhase, type BankyState } from "../components/Banky";
import BlockView from "../components/blocks/BlockView";
import FeedbackCard from "../components/FeedbackCard";
import ModeChoice, { storedMode, storeMode, useVoiceConfig, type ChatMode } from "../components/ModeChoice";
import ErrorNote from "../components/ErrorNote";
import VoiceComposer from "../components/VoiceComposer";
import ThinkingIndicator, { useTurnPhase } from "../components/ThinkingIndicator";
import { formatDate } from "../lib/format";
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

type Body = TurnBody;

function fromDetail(d: ConversationDetail): Message[] {
  return d.turns.map((t) => (t.role === "customer"
    ? { id: t.turn_id, role: "customer", text: t.message ?? actionLabel(t.action, d.language) }
    : { id: t.turn_id, role: "assistant", blocks: t.blocks, state: d.state }));
}

/** El saludo del backend empieza con "Hola, …"; Banky ya saludó en la primera línea, así que esa palabra se quita (solo
 *  presentación: el resto del texto queda igual). */
function withoutGreetingWord(blocks: Block[]): Block[] {
  let done = false;
  return blocks.map((b) => {
    if (done || b.type !== "text") return b;
    done = true;
    const rest = b.text.replace(/^\s*¡?(hola|olá|oi)\b[!,.\s]*/i, "");
    return rest && rest !== b.text ? { ...b, text: rest.replace(/^([¿¡"«\s]*)(\p{L})/u, (_, pre: string, ch: string) => pre + ch.toUpperCase()) } : b;
  });
}

/** Expresión de Banky según lo que trae el turno: feliz con un resultado verificado, empático ante un traspaso o un aviso. */
function bankyFor(blocks: Block[] | undefined): BankyState {
  for (const b of blocks ?? []) {
    if (b.type === "result") return b.status === "success" && b.verified ? "happy" : "worried";
    if (b.type === "handoff_notice") return "handoff";
    if (b.type === "notice" && b.code === "no_match") return "searching";      // buscó y no encontró: lo dice
    if (b.type === "notice" && b.code === "need_detail") return "listening";   // falta un dato: lo pide y escucha
    if (b.type === "error" || (b.type === "notice" && b.level === "warning")) return "worried";
  }
  return "idle";
}

function actionLabel(a: Action | null, lang: Lang): string {
  if (!a) return "";
  return T[lang].history.actionLabels[a.type] ?? a.type;
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
  const [mode, setMode] = useState<ChatMode | null>(storedMode);
  const voice = useVoiceConfig();
  const voiceEnabled = Boolean(voice.config?.enabled);
  const chooseMode = useCallback((m: ChatMode) => { setMode(m); storeMode(m); if (m === "text") inputRef.current?.focus(); }, []);
  const voiceOn = mode === "voice" && voiceEnabled;
  const voiceOnRef = useRef(voiceOn);
  voiceOnRef.current = voiceOn;
  const [listening, setListening] = useState(false);
  const [voiceNote, setVoiceNote] = useState<string | null>(null);
  const [speech, setSpeech] = useState<{ turnId: string; playing: boolean } | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const stopSpeech = useCallback(() => {
    audioRef.current?.pause();
    if (audioRef.current?.src) URL.revokeObjectURL(audioRef.current.src);
    audioRef.current = null;
    setSpeech((s) => (s ? { ...s, playing: false } : s));
  }, []);

  /** La voz falló o no se puede usar: se explica (si hay motivo) y la conversación sigue por texto. */
  const voiceFallback = useCallback((message: string) => {
    stopSpeech();
    setVoiceNote(message || null);
    setMode("text");
    storeMode("text");
  }, [stopSpeech]);

  /** Lee en voz alta un turno del asistente; el texto ya está en pantalla y hace de subtítulos. */
  const speak = useCallback(async (convId: string, turnId: string) => {
    stopSpeech();
    try {
      const blob = await api.voiceTts(convId, turnId);
      const audio = new Audio(URL.createObjectURL(blob));
      audioRef.current = audio;
      audio.onended = () => setSpeech((s) => (s ? { ...s, playing: false } : s));
      setSpeech({ turnId, playing: true });
      await audio.play();
    } catch (e) {
      setSpeech(null);
      if (e instanceof ApiError) voiceFallback(e.code === "voice_budget_exceeded" ? T[lang].voice.budget : T[lang].voice.fallback);
      /* si el navegador bloquea la reproducción automática, el texto sigue en pantalla */
    }
  }, [lang, stopSpeech, voiceFallback]);

  useEffect(() => stopSpeech, [stopSpeech]);

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
      if (voiceOnRef.current) void speak(r.conversation_id, r.turn_id);
    } catch (e) {
      setMessages((m) => m.filter((x) => x.id !== `c-${key}`));
      handleError(e, () => void send(body, echo, convId, key));   // reintento con la MISMA Idempotency-Key
    } finally {
      setSending(false);
    }
  }, [applyTurn, conversationId, handleError, lang, sending, speak]);

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
  }, [messages, sending, state]);

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

  const lastAssistantMsg = [...messages].reverse().find((m) => m.role === "assistant");
  const lastAssistant = lastAssistantMsg?.id;
  // el Banky de la cabecera refleja lo que pasa AHORA: la fase real del turno en curso o el resultado del último turno
  const headState: BankyState = listening ? "listening" : speech?.playing ? "talking" : sending ? stateForPhase(phase) : messages.length <= 1 ? "greeting" : bankyFor(lastAssistantMsg?.blocks);
  const closed = state === "cerrado";

  return (
    <section className="chat" aria-label={t.navChat}>
      <div className="chat-head">
        <div className="chat-id">
          <Banky state={headState} size={40} label={t.chat.bankyStates[headState]} />
          <div>
            <strong>{t.chat.bankyName}</strong>
            <p className="muted small">{t.chat.bankyRole}{dataAsOf?.max_transaction_date && <> · {t.dataAsOf} {formatDate(dataAsOf.max_transaction_date, lang)}</>}</p>
          </div>
        </div>
        <div className="chat-tools">
          {voiceEnabled && (
          <div className="segmented" role="group" aria-label={t.chat.modeLabel}>
            <button type="button" aria-pressed={!voiceOn} onClick={() => { stopSpeech(); chooseMode("text"); }}>{t.chat.modeText}</button>
            <button type="button" aria-pressed={voiceOn} onClick={() => { setVoiceNote(null); chooseMode("voice"); }}>{t.chat.modeVoice}</button>
          </div>
          )}
          <button className="btn ghost small" disabled={sending} onClick={() => void send({ action: { type: "request_human" } }, t.humanHelp)}>{t.humanHelp}</button>
          <button className="btn ghost small" disabled={sending} onClick={() => void startConversation({ previous: conversationId ?? undefined }).catch(handleError)}>{t.newConversation}</button>
        </div>
      </div>

      <div className="messages" role="log" aria-live="polite" aria-relevant="additions" aria-busy={sending}>
        {messages.map((m) => (
          <div key={m.id} className={`msg ${m.role}`}>
            {m.role === "assistant" && <Banky state={bankyFor(m.blocks)} size={44} />}
            {m.role === "assistant" ? (
              <div className={m.id.startsWith("greet-") ? "bubble assistant welcome" : "bubble assistant"}>
                <span className="sr-only">{t.assistant}:</span>
                {/* bienvenida en UN solo mensaje: la presentación de Banky y, debajo, lo que puede hacer (texto del backend) */}
                {m.id.startsWith("greet-") && <p className="bubble-text welcome-hello"><strong>{t.chat.hello}</strong></p>}
                {(m.id.startsWith("greet-") ? withoutGreetingWord(m.blocks ?? []) : m.blocks ?? []).map((b, i) => (
                  <BlockView key={i} block={b} lang={lang} state={m.id === lastAssistant ? state : (m.state ?? state)}
                    active={m.id === lastAssistant && !sending && !closed && cooldown === 0}
                    onAction={(action, label) => void send({ action }, label)} />
                ))}
                {m.id.startsWith("greet-") && !voice.loading && <ModeChoice lang={lang} mode={mode} voiceEnabled={voiceEnabled} onChoose={chooseMode} />}
              </div>
            ) : m.role === "system" ? (
              <p className="system-note">{m.text}</p>
            ) : (
              <div className="bubble customer"><span className="sr-only">{t.you}:</span>{m.text}</div>
            )}
          </div>
        ))}
        {sending && <ThinkingIndicator phase={phase} label={phase ? (t.chat.phases[phase] ?? t.typing) : t.typing} />}
        {closed && conversationId && !sending && (
          <div className="chat-closed">
            <p className="system-note">{t.chat.closedNote}</p>
            <FeedbackCard key={conversationId} conversationId={conversationId} lang={lang} onUnauthorized={() => { onUnauthorized(); navigate("/login"); }} />
            <button className="btn secondary" onClick={() => void startConversation({ previous: conversationId }).catch(handleError)}>{t.newConversation}</button>
          </div>
        )}
        <div ref={endRef} />
      </div>

      {error && <ErrorNote message={error.message} requestId={error.requestId} label={t.reference}
        onRetry={error.retry && cooldown === 0 ? () => { const r = error.retry!; setError(null); r(); } : undefined} retryLabel={t.retry} />}

      {voiceNote && <p className="notice warning voice-note" role="status">{voiceNote}</p>}
      {speech && voiceOn && (
        <p className="speaking" role="status">
          <span aria-hidden="true">🔊</span> {speech.playing ? t.voice.speaking : t.voice.confirmNote}
          {speech.playing
            ? <button type="button" className="btn ghost small" onClick={stopSpeech}>{t.voice.stopAudio}</button>
            : conversationId && <button type="button" className="btn ghost small" onClick={() => void speak(conversationId, speech.turnId)}>{t.voice.replay}</button>}
        </p>
      )}
      {!closed && voiceOn && voice.config && (
        <VoiceComposer lang={lang} config={voice.config} disabled={sending || cooldown > 0} onListening={(on) => { setListening(on); if (on) stopSpeech(); }}
          onFallback={voiceFallback} onSend={(text) => { setVoiceNote(null); void send({ message: text, via: "voice" }, text); }} />
      )}
      {!closed && !voiceOn && (
      <form className="composer" onSubmit={submit}>
        <label htmlFor="msg" className="sr-only">{t.messagePlaceholder}</label>
        <textarea id="msg" ref={inputRef} rows={1} value={input} placeholder={t.messagePlaceholder}
          maxLength={MAX_CHARS} onChange={(e) => setInput(e.target.value)} onKeyDown={onKey} disabled={cooldown > 0}
          aria-describedby={input.length > MAX_CHARS - 200 ? "chars" : undefined} />
        <button className="btn primary send" type="submit" disabled={!input.trim() || sending || cooldown > 0}>
          <svg className="send-icon" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 19V5M5.5 11.5 12 5l6.5 6.5" /></svg>
          <span className="send-label">{cooldown > 0 ? `${cooldown}s` : t.send}</span>
        </button>
        {input.length > MAX_CHARS - 200 && <span id="chars" className="muted small chars">{t.charsLeft(MAX_CHARS - input.length)}</span>}
      </form>
      )}
    </section>
  );
}
