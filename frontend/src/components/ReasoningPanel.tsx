// Cómo decidió el asistente en cada mensaje de un ticket: qué entendió, qué datos usó, qué buscó, el riesgo, las reglas de
// política, las guardas que actuaron y qué respondió (GET /api/tickets/{id}/reasoning). Solo lo ve el agente que tiene el ticket
// asignado; el administrador ve la analítica agregada de estos mismos pasos, nunca un mensaje.
import { useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type { ReasoningTurn, TicketReasoning } from "../api/types";
import { T } from "../lib/i18n";
import { describeError, useSession } from "../lib/session";
import ErrorNote from "./ErrorNote";

function show(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "object") return Object.entries(v as Record<string, unknown>).filter(([, x]) => x !== null && x !== false).map(([k, x]) => `${k}: ${show(x)}`).join(", ");
  return String(v);
}

function Turn({ turn, n, open }: { turn: ReasoningTurn; n: number; open: boolean }) {
  const { lang } = useSession();
  const r = T[lang].reasoning;
  const u = turn.understanding;
  return (
    <details className="reason-turn" open={open}>
      <summary>
        <span className="num">{n}</span>
        <span className="reason-said">{turn.customer.text ?? (turn.customer.action ? `[${turn.customer.action}]` : "—")}</span>
        <span className="reason-pills">
          {u?.intent && <span className="pill">{u.intent}</span>}
          {turn.guardrails.length > 0 && <span className="pill o-bloqueo">{r.guardCount(turn.guardrails.length)}</span>}
          <span className="pill neutral">{turn.response.state_after}</span>
        </span>
      </summary>
      <dl className="reason-grid">
        <dt>{r.understood}</dt>
        <dd>{u ? <><strong>{u.intent ?? "—"}</strong> · {u.source}{u.certainty ? ` · ${r.certainty}: ${u.certainty}` : ""}{u.process_topic ? ` · ${r.topic}: ${u.process_topic}` : ""}
          {u.others.length > 0 && ` · ${r.alsoAsked}: ${u.others.join(", ")}`}{u.corrected && ` · ${r.corrected}`}</> : <span className="muted">{r.noIntent}</span>}</dd>
        <dt>{r.data}</dt>
        <dd>{turn.data && Object.keys(turn.data.fields).length > 0
          ? <><ul className="reason-list">{Object.entries(turn.data.fields).map(([k, v]) => <li key={k}><span className="mono small">{k}</span>: {show(v)}</li>)}</ul><span className="muted small">{turn.data.source}</span></>
          : <span className="muted">{r.noData}</span>}</dd>
        <dt>{r.search}</dt>
        <dd>{turn.search.length > 0 ? <ul className="reason-list">{turn.search.map((s, i) => <li key={i}><span className="mono small">{s.step}</span>: {s.result}</li>)}</ul> : <span className="muted">{r.noSearch}</span>}</dd>
        {turn.risk && <><dt>{r.risk}</dt><dd><strong>{turn.risk.band}</strong>{turn.risk.missing_score ? ` · ${r.noScore}` : ""} <span className="muted small">· {turn.risk.source}</span></dd></>}
        {turn.policy && <>
          <dt>{r.policy}</dt>
          <dd><strong>{turn.policy.result}</strong>{turn.policy.decides ? ` · ${r.decidedBy} ${show((turn.policy.decides as Record<string, unknown>).id)}: ${show((turn.policy.decides as Record<string, unknown>).motivo)}` : ""}
            <ul className="reason-rules">{turn.policy.rules.map((x, i) => <li key={i} className={x.result === "permitir" ? undefined : "flag"}><span className="pill neutral">{x.id}</span> {x.result} · {x.reason}</li>)}</ul></dd>
        </>}
        <dt>{r.guardrails}</dt>
        <dd>{turn.guardrails.length > 0 ? <ul className="reason-list">{turn.guardrails.map((g) => <li key={g.id}>{g.label}</li>)}</ul> : <span className="muted">{r.noGuardrails}</span>}</dd>
        <dt>{r.response}</dt>
        <dd><ul className="reason-list">{turn.response.blocks.map((b, i) => <li key={i}>{b}</li>)}</ul>
          <span className="muted small">{turn.response.state_before ?? "—"} → {turn.response.state_after} · {r.writtenBy}: {turn.response.written_by}</span></dd>
        <dt>{r.cost}</dt>
        <dd className="small">{turn.totals.steps} {r.steps} · {turn.totals.llm_calls} LLM · {turn.totals.latency_ms} ms{turn.totals.cost_usd > 0 ? ` · $${turn.totals.cost_usd.toFixed(4)}` : ""}
          {turn.totals.errors.length > 0 && <span className="s-pending"> · {r.errors}: {turn.totals.errors.length}</span>}</dd>
      </dl>
    </details>
  );
}

export default function ReasoningPanel({ ticketId }: { ticketId: string }) {
  const { lang } = useSession();
  const t = T[lang];
  const r = t.reasoning;
  const [data, setData] = useState<TicketReasoning | null>(null);
  const [notAssigned, setNotAssigned] = useState(false);
  const [error, setError] = useState<{ message: string; requestId: string | null } | null>(null);
  useEffect(() => {
    let alive = true;
    setData(null); setError(null); setNotAssigned(false);
    api.ticketReasoning(ticketId).then((d) => { if (alive) setData(d); }).catch((e) => {
      if (!alive) return;
      if (e instanceof ApiError && e.status === 403) setNotAssigned(true);
      else setError(describeError(e, t));
    });
    return () => { alive = false; };
  }, [ticketId]); // eslint-disable-line react-hooks/exhaustive-deps
  if (notAssigned) return <p className="muted">{r.lockedText}</p>;
  if (error) return <ErrorNote message={error.message} requestId={error.requestId} label={t.reference} />;
  if (!data) return <p className="muted" role="status">{t.loading}</p>;
  if (data.turns.length === 0) return <p className="muted">—</p>;
  // abierto de entrada: el mensaje donde la política decidió pasar el caso; si no hubo, el último con política; si no, el último
  const last = (ok: (x: ReasoningTurn) => boolean) => data.turns.map(ok).lastIndexOf(true);
  const escalated = last((x) => x.policy?.result === "escalar");
  const focus = escalated >= 0 ? escalated : last((x) => x.policy !== null) >= 0 ? last((x) => x.policy !== null) : data.turns.length - 1;
  return (
    <>
      <p className="muted small">{r.hint}</p>
      <div className="reason-turns">{data.turns.map((turn, i) => <Turn key={turn.turn_id} turn={turn} n={i + 1} open={i === focus} />)}</div>
      <p className="muted small">{r.note}</p>
    </>
  );
}
