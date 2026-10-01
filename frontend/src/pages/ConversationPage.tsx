// Una conversación propia en solo lectura (GET /api/me/conversations/{id}) con los mismos bloques que mostró el chat.
// "Continuar sobre este tema" crea una conversación nueva enlazada (previous_conversation_id) y abre el chat.
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { MyConversationDetail } from "../api/types";
import Banky from "../components/Banky";
import BlockView from "../components/blocks/BlockView";
import ErrorNote from "../components/ErrorNote";
import { formatDateTime } from "../lib/format";
import { T } from "../lib/i18n";
import { describeError, useSession } from "../lib/session";
import { useApi } from "../lib/useApi";
import { ConversationMeta } from "./ConversationsPage";

export default function ConversationPage() {
  const { id = "" } = useParams();
  const { lang } = useSession();
  const t = T[lang];
  const h = t.history;
  const navigate = useNavigate();
  const { data, loading, error, reload } = useApi<MyConversationDetail>(() => api.myConversation(id, lang), [id]);
  const [busy, setBusy] = useState(false);
  const [continueError, setContinueError] = useState<{ message: string; requestId: string | null } | null>(null);

  async function continueTopic() {
    setBusy(true);
    setContinueError(null);
    try {
      const conv = await api.newConversation({ language: lang, previous_conversation_id: id });
      sessionStorage.setItem("conversation_id", conv.conversation_id);
      navigate("/chat");
    } catch (e) {
      setContinueError(describeError(e, t));
      setBusy(false);
    }
  }

  return (
    <section className="page" aria-labelledby="h-conv-detail">
      <Link className="back" to="/conversaciones">← {h.back}</Link>
      {loading && !data && <p className="muted" role="status">{t.loading}</p>}
      {error && (error.status === 404
        ? <p className="empty">{h.notFound}</p>
        : <ErrorNote message={error.message} requestId={error.requestId} label={t.reference} onRetry={reload} retryLabel={t.retry} />)}
      {data && (
        <>
          <header className="conv-header">
            <h1 id="h-conv-detail">{data.summary}</h1>
            <p className="muted small">{formatDateTime(data.created_at, lang)} · {h.readOnly}{data.previous_conversation_id && <> · <Link to={`/conversaciones/${data.previous_conversation_id}`}>{h.continues}</Link></>}</p>
            <ConversationMeta c={data} lang={lang} />
            <div className="actions">
              <button className="btn primary" disabled={busy} onClick={() => void continueTopic()}>{h.continueTopic}</button>
            </div>
            {continueError && <ErrorNote message={continueError.message} requestId={continueError.requestId} label={t.reference} />}
          </header>
          <div className="messages transcript" role="log" aria-label={data.summary}>
            {data.turns.map((turn) => (
              <div key={turn.turn_id} className={`msg ${turn.role === "customer" ? "customer" : "assistant"}`}>
                {turn.role === "customer" ? (
                  <div className="bubble customer"><span className="sr-only">{t.you}:</span>{turn.message ?? (turn.action ? h.actionLabels[turn.action.type] ?? turn.action.type : "")}</div>
                ) : (
                  <>
                    <Banky size={36} />
                    <div className="bubble assistant">
                      <span className="sr-only">{t.assistant}:</span>
                      {turn.blocks.map((b, i) => <BlockView key={i} block={b} lang={lang} state={turn.state_after} active={false} onAction={() => undefined} />)}
                    </div>
                  </>
                )}
              </div>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
