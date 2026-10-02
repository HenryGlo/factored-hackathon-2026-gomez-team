// Detalle del ticket (GET /api/tickets/{id}): el handoff estructurado (lo que dice el cliente frente a los hechos verificados,
// preguntas pendientes, política aplicada), la conversación, la línea de tiempo de trazas, las acciones y las notas internas.
import { useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { ConversationDetail, TicketDetail, Trace } from "../api/types";
import BlockView from "../components/blocks/BlockView";
import ErrorNote from "../components/ErrorNote";
import { formatDateTime } from "../lib/format";
import { Loading } from "../components/States";
import { T } from "../lib/i18n";
import { describeError, useSession } from "../lib/session";
import { useApi } from "../lib/useApi";
import { PriorityPill, SlaPill } from "./TicketsPage";

const STATUSES = ["nuevo", "en_curso", "esperando_cliente", "resuelto"];
const MAX_TRACES = 8;

function show(v: unknown): string {
  return v === null || v === undefined ? "—" : typeof v === "object" ? JSON.stringify(v) : String(v);
}

/** Pasos de cada turno con su tipo, latencia y costo; la barra es proporcional a la latencia dentro del turno. */
function TraceTimeline({ turnIds }: { turnIds: string[] }) {
  const { lang } = useSession();
  const a = T[lang].agent;
  const [traces, setTraces] = useState<Trace[] | null>(null);
  const key = turnIds.join(",");
  useEffect(() => {
    let alive = true;
    Promise.all(turnIds.slice(-MAX_TRACES).map((id) => api.trace(id).catch(() => null)))
      .then((xs) => { if (alive) setTraces(xs.filter((x): x is Trace => x !== null)); });
    return () => { alive = false; };
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!traces) return <p className="muted" role="status">{T[lang].loading}</p>;
  if (traces.length === 0) return <p className="muted">—</p>;
  return (
    <ol className="trace-turns">
      {traces.map((tr) => {
        const max = Math.max(1, ...tr.steps.map((s) => s.latency_ms ?? 0));
        return (
          <li key={tr.turn_id}>
            <p className="trace-head">
              <span className="mono small">{tr.state_before ?? "—"} → {tr.state_after}</span>
              <span className="muted small">{tr.totals.latency_ms} ms · ${Number(tr.totals.cost_usd).toFixed(4)}</span>
              <Link className="small" to={`/agentes/trazas/${tr.turn_id}`}>{a.fullTrace}</Link>
            </p>
            <ol className="trace-steps">
              {tr.steps.map((s) => (
                <li key={s.step_seq} className={s.error ? "has-error" : undefined}>
                  <span className={`pill k-${s.kind}`}>{s.kind.toUpperCase()}</span>
                  <span className="mono small trace-node">{s.node}</span>
                  <span className="trace-bar" aria-hidden="true"><i style={{ width: `${Math.max(2, ((s.latency_ms ?? 0) / max) * 100)}%` }} /></span>
                  <span className="small trace-num">{s.latency_ms ?? 0} ms{s.cost_usd && Number(s.cost_usd) > 0 ? ` · $${Number(s.cost_usd).toFixed(4)}` : ""}</span>
                </li>
              ))}
            </ol>
          </li>
        );
      })}
    </ol>
  );
}

function Transcript({ conversationId }: { conversationId: string }) {
  const { lang } = useSession();
  const t = T[lang];
  const { data, loading, error } = useApi<ConversationDetail>(() => api.conversation(conversationId), [conversationId]);
  if (error) return <ErrorNote message={error.message} requestId={error.requestId} label={t.reference} />;
  if (loading && !data) return <p className="muted" role="status">{t.loading}</p>;
  return (
    <div className="messages transcript" role="log">
      {data?.turns.map((turn) => (
        <div key={turn.turn_id} className={`msg ${turn.role === "customer" ? "customer" : "assistant"}`}>
          {turn.role === "customer"
            ? <div className="bubble customer">{turn.message ?? (turn.action ? t.history.actionLabels[turn.action.type] ?? turn.action.type : "")}</div>
            : <div className="bubble assistant">{turn.blocks.map((b, i) => <BlockView key={i} block={b} lang={data.language} state="cerrado" active={false} onAction={() => undefined} />)}</div>}
        </div>
      ))}
    </div>
  );
}

export default function TicketPage() {
  const { id = "" } = useParams();
  const { lang } = useSession();
  const t = T[lang];
  const a = t.agent;
  const { data: k, loading, error, reload } = useApi<TicketDetail>(() => api.ticket(id), [id]);
  const [status, setStatus] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<{ message: string; requestId: string | null } | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => { if (k) setStatus(k.status); }, [k]);

  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    setActionError(null);
    setSaved(false);
    try {
      await fn();
      setSaved(true);
      reload();
    } catch (e) {
      setActionError(describeError(e, t));
    } finally {
      setBusy(false);
    }
  }

  function addNote(e: FormEvent) {
    e.preventDefault();
    const text = note.trim();
    if (!text) return;
    void act(async () => { await api.ticketNote(id, text); setNote(""); });
  }

  if (error) return <section className="page"><Link className="back" to="/agentes">← {a.back}</Link><ErrorNote message={error.message} requestId={error.requestId} label={t.reference} onRetry={reload} retryLabel={t.retry} /></section>;
  if (!k) return <section className="page wide">{loading && <Loading label={t.loading} rows={6} />}</section>;
  const h = k.handoff;
  return (
    <section className="page wide ticket" aria-labelledby="h-ticket">
      <Link className="back" to="/agentes">← {a.back}</Link>
      <header className="ticket-header">
        <div>
          <h1 id="h-ticket">{h.request} <code>{k.reference_label}</code></h1>
          <p className="conv-meta">
            <PriorityPill ticket={k} lang={lang} /> <span className="pill neutral">{a.status[k.status] ?? k.status}</span> <SlaPill ticket={k} lang={lang} />
            <span className="muted small">{a.cols.due}: {formatDateTime(k.sla.due_at, lang)} · {a.cols.age}: {a.age(k.age_minutes)}</span>
          </p>
          <p className="muted small">{a.reasons[k.reason_code] ?? k.reason_code} · {a.queue}: {k.queue} · {a.customer}: {show(h.customer_ref.display_name)} ({show(h.customer_ref.segment)}, {show(h.customer_ref.country)}) · {k.language.toUpperCase()}</p>
        </div>
        <div className="ticket-actions">
          <p className="small">{a.filters.assignee}: <strong>{k.assignee ? k.assignee.username : a.unassigned}</strong></p>
          <div className="actions">
            <button className="btn primary" disabled={busy} onClick={() => void act(() => api.ticketAssign(id, "me"))}>{a.take}</button>
            {k.assignee && <button className="btn ghost" disabled={busy} onClick={() => void act(() => api.ticketAssign(id, null))}>{a.release}</button>}
          </div>
          <form className="row" onSubmit={(e) => { e.preventDefault(); void act(() => api.ticketStatus(id, status)); }}>
            <label>{a.changeStatus}
              <select value={status} onChange={(e) => setStatus(e.target.value)}>{STATUSES.map((s) => <option key={s} value={s}>{a.status[s]}</option>)}</select>
            </label>
            <button className="btn secondary" type="submit" disabled={busy || status === k.status}>{a.save}</button>
          </form>
          {saved && <p className="small ok-text" role="status">{a.saved}</p>}
          {actionError && <ErrorNote message={actionError.message} requestId={actionError.requestId} label={t.reference} />}
        </div>
      </header>

      <div className="card"><h2>{a.summary}</h2><p className="bubble-text">{h.summary}</p></div>

      <div className="two-col">
        <div className="card claims">
          <h2>{a.claims}</h2>
          <p className="muted small">{a.claimsHint}</p>
          {h.customer_claims.length === 0 ? <p className="muted">{a.noClaims}</p> : <ul className="plain">{h.customer_claims.map((c, i) => <li key={i}>“{c.claim}”</li>)}</ul>}
        </div>
        <div className="card facts">
          <h2>{a.facts}</h2>
          <p className="muted small">{a.factsHint}</p>
          {h.verified_facts.length === 0 ? <p className="muted">{a.noFacts}</p> : (
            <table className="grid compact"><tbody>{h.verified_facts.map((f, i) => <tr key={i}><th scope="row">{f.fact}</th><td>{show(f.value)}</td><td className="muted small">{f.source_tool}</td></tr>)}</tbody></table>
          )}
        </div>
      </div>

      <div className="two-col">
        <div className="card">
          <h2>{a.questions}</h2>
          <ul className="plain bullets">{h.open_questions.map((q, i) => <li key={i}>{q}</li>)}</ul>
        </div>
        <div className="card">
          <h2>{a.actions}</h2>
          {h.actions_taken.length === 0 ? <p className="muted">{a.noActions}</p> : (
            <ul className="plain">{h.actions_taken.map((x, i) => <li key={i}>{x.action} · {x.status} · {x.verified ? t.verified : t.notVerified} {x.reference_id && <code>{x.reference_id}</code>}</li>)}</ul>
          )}
        </div>
      </div>

      <div className="card">
        <h2>{a.policy}</h2>
        {h.policy_evaluations.length === 0 ? <p className="muted">{a.noPolicy}</p> : (
          <table className="grid compact"><tbody>{h.policy_evaluations.map((r, i) => (
            <tr key={i}><th scope="row">{show(r.id ?? r.rule)}</th><td>{show(r.resultado ?? r.result)}</td><td>{show(r.motivo)}</td><td className="small mono">{show(r.evidencia ?? r.evidence)}</td></tr>
          ))}</tbody></table>
        )}
      </div>

      <div className="two-col">
        <div className="card">
          <h2>{a.conversation}</h2>
          <Transcript conversationId={k.conversation_id} />
        </div>
        <div className="card">
          <h2>{a.traces}</h2>
          <p className="muted small">{a.tracesHint}</p>
          <TraceTimeline turnIds={h.trace_turn_ids} />
        </div>
      </div>

      <div className="card">
        <h2>{a.notes}</h2>
        <p className="muted small">{a.notesHint}</p>
        {k.events.length === 0 ? <p className="muted">{a.noEvents}</p> : (
          <ol className="events">
            {k.events.map((ev) => (
              <li key={ev.event_id}>
                <span className="muted small">{formatDateTime(ev.created_at, lang)} · {ev.actor_username}</span>
                <span><span className="pill neutral">{a.eventKinds[ev.kind] ?? ev.kind}</span> {ev.kind !== "nota" && <>{ev.from_value ?? "—"} → {ev.to_value ?? "—"}</>} {ev.note}</span>
              </li>
            ))}
          </ol>
        )}
        <form className="form" onSubmit={addNote}>
          <label>{a.addNote}<textarea rows={2} maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} /></label>
          <div className="actions"><button className="btn secondary" type="submit" disabled={busy || !note.trim()}>{a.addNoteBtn}</button></div>
        </form>
      </div>
    </section>
  );
}
