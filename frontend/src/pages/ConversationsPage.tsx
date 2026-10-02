// "Mis conversaciones": GET /api/me/conversations (paginado con cursor). El resumen viene armado con hechos por el backend.
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { ConversationSummary, MyConversations } from "../api/types";
import ErrorNote from "../components/ErrorNote";
import { formatDateTime } from "../lib/format";
import { Empty, Loading } from "../components/States";
import { T } from "../lib/i18n";
import { useSession } from "../lib/session";
import { useApi } from "../lib/useApi";

export function ConversationMeta({ c, lang }: { c: ConversationSummary; lang: "es" | "pt" }) {
  const h = T[lang].history;
  const closed = c.state === "cerrado" || c.state === "escalado";
  return (
    <span className="conv-meta">
      <span className={`pill ${closed ? "neutral" : ""}`}>{closed ? (c.closed_reason ? h.closedBy[c.closed_reason] ?? h.closed : h.closed) : h.open}</span>
      {c.outcomes.filter((o) => o !== "sin_accion").map((o) => <span key={o} className={`pill o-${o}`}>{h.outcomes[o] ?? o}</span>)}
      {c.references.map((r) => <code key={r}>{r}</code>)}
    </span>
  );
}

export default function ConversationsPage() {
  const { lang } = useSession();
  const t = T[lang];
  const h = t.history;
  const [more, setMore] = useState<{ busy: boolean; failed: boolean }>({ busy: false, failed: false });
  const { data, loading, error, reload, setData } = useApi<MyConversations>(() => api.myConversations({ lang }), []);

  async function loadMore() {
    if (!data?.next_cursor || more.busy) return;
    setMore({ busy: true, failed: false });
    try {
      const next = await api.myConversations({ lang, cursor: data.next_cursor });
      setData({ conversations: [...data.conversations, ...next.conversations], next_cursor: next.next_cursor });
      setMore({ busy: false, failed: false });
    } catch {
      setMore({ busy: false, failed: true });
    }
  }

  return (
    <section className="page" aria-labelledby="h-conv">
      <h1 id="h-conv">{h.nav}</h1>
      {error && <ErrorNote message={error.message} requestId={error.requestId} label={t.reference} onRetry={reload} retryLabel={t.retry} />}
      {loading && !data && <Loading label={t.loading} />}
      {data && (data.conversations.length === 0 ? <Empty title={h.empty} banky="greeting"><Link className="btn primary" to="/chat">{h.emptyCta}</Link></Empty> : (
        <>
          <ul className="conv-list">
            {data.conversations.map((c) => (
              <li key={c.conversation_id}>
                <Link className="card conv-card" to={`/conversaciones/${c.conversation_id}`} aria-label={h.view(c.summary)}>
                  <span className="conv-date">{formatDateTime(c.created_at, lang)} · {h.messages(c.customer_turns)}</span>
                  <span className="conv-summary">{c.summary}</span>
                  <ConversationMeta c={c} lang={lang} />
                </Link>
              </li>
            ))}
          </ul>
          {more.failed && <p className="notice error" role="alert">{t.genericError}</p>}
          {data.next_cursor && <p className="center-row"><button className="btn secondary" disabled={more.busy} onClick={() => void loadMore()}>{more.busy ? t.loading : h.more}</button></p>}
        </>
      ))}
    </section>
  );
}
