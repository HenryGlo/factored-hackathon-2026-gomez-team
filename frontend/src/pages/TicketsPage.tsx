// Bandeja de tickets de los agentes de soporte (GET /api/tickets): filtros por estado, prioridad, SLA y asignado.
// El orden (prioridad y antigüedad) lo decide el backend. La pestaña "Reclamos" lista los reclamos creados por el sistema.
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { CaseSummary, Ticket, TicketList, Lang } from "../api/types";
import ErrorNote from "../components/ErrorNote";
import { formatDateTime } from "../lib/format";
import { Empty, Loading } from "../components/States";
import { T } from "../lib/i18n";
import { useSession } from "../lib/session";
import { useApi } from "../lib/useApi";

const STATUSES = ["nuevo", "en_curso", "esperando_cliente", "resuelto"] as const;
const PRIORITIES = ["urgente", "alta", "media"];
const SLAS = ["a_tiempo", "por_vencer", "vencido", "cumplido", "incumplido"];

export function PriorityPill({ ticket, lang }: { ticket: Pick<Ticket, "priority">; lang: Lang }) {
  return <span className={`pill p-${ticket.priority}`}>{T[lang].agent.priority[ticket.priority] ?? ticket.priority}</span>;
}

export function SlaPill({ ticket, lang }: { ticket: Pick<Ticket, "sla">; lang: Lang }) {
  return <span className={`pill sla-${ticket.sla.state}`}>{T[lang].agent.sla[ticket.sla.state] ?? ticket.sla.state}</span>;
}

function Cases() {
  const { lang } = useSession();
  const t = T[lang];
  const { data, loading, error, reload } = useApi<CaseSummary[]>(() => api.cases(), []);
  if (error) return <ErrorNote message={error.message} requestId={error.requestId} label={t.reference} onRetry={reload} retryLabel={t.retry} />;
  if (loading && !data) return <Loading label={t.loading} />;
  if (!data?.length) return <Empty title={t.agent.noCasesStaff} />;
  return (
    <table className="grid">
      <thead><tr><th>{t.agent.navCases}</th><th>{t.agent.customer}</th><th>ID</th><th>{t.status}</th><th>{t.from}</th></tr></thead>
      <tbody>
        {data.map((c) => (
          <tr key={c.case_id}>
            <td><code>{c.case_id}</code></td><td><code>{c.customer_id}</code></td><td><code>{c.transaction_id}</code></td>
            <td>{t.caseStatus[c.status] ?? c.status}</td><td>{formatDateTime(c.created_at, lang)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function TicketsPage() {
  const { lang } = useSession();
  const t = T[lang];
  const a = t.agent;
  const [tab, setTab] = useState<"tickets" | "cases">("tickets");
  const [f, setF] = useState({ status: "", priority: "", sla: "", assignee: "", open: "true" });
  const { data, loading, error, reload } = useApi<TicketList>(() => api.tickets(f), [f.status, f.priority, f.sla, f.assignee, f.open]);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });

  return (
    <section className="page wide" aria-labelledby="h-tickets">
      <h1 id="h-tickets">{a.title}</h1>
      <div className="tabs" role="tablist">
        <button role="tab" aria-selected={tab === "tickets"} className={tab === "tickets" ? "tab active" : "tab"} onClick={() => setTab("tickets")}>{a.nav}</button>
        <button role="tab" aria-selected={tab === "cases"} className={tab === "cases" ? "tab active" : "tab"} onClick={() => setTab("cases")}>{a.navCases}</button>
      </div>
      {tab === "cases" ? <Cases /> : (
        <>
          {data && (
            <ul className="stat-row" aria-label={a.filters.status}>
              {STATUSES.map((s) => (
                <li key={s}>
                  <button type="button" className="stat" aria-pressed={f.status === s} onClick={() => setF({ ...f, status: f.status === s ? "" : s, open: s === "resuelto" ? "" : f.open })}>
                    <span className="stat-n">{data.by_status[s] ?? 0}</span><span>{a.status[s]}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          <div className="filters">
            <label>{a.filters.priority}
              <select value={f.priority} onChange={set("priority")}><option value="">{t.all}</option>{PRIORITIES.map((p) => <option key={p} value={p}>{a.priority[p]}</option>)}</select>
            </label>
            <label>{a.filters.sla}
              <select value={f.sla} onChange={set("sla")}><option value="">{t.all}</option>{SLAS.map((p) => <option key={p} value={p}>{a.sla[p]}</option>)}</select>
            </label>
            <label>{a.filters.assignee}
              <select value={f.assignee} onChange={set("assignee")}><option value="">{t.all}</option><option value="me">{a.assignee.me}</option><option value="unassigned">{a.assignee.unassigned}</option></select>
            </label>
            <label className="inline check"><input type="checkbox" checked={f.open === "true"} onChange={(e) => setF({ ...f, open: e.target.checked ? "true" : "" })} />{a.onlyOpen}</label>
          </div>
          {error && <ErrorNote message={error.message} requestId={error.requestId} label={t.reference} onRetry={reload} retryLabel={t.retry} />}
          {loading && !data && <Loading label={t.loading} rows={4} />}
          {data && (data.tickets.length === 0 ? <Empty title={a.empty} banky="happy" /> : (
            <ul className="ticket-list" aria-busy={loading}>
              {data.tickets.map((k) => (
                <li key={k.ticket_id}>
                  <Link className={`card ticket-row pr-${k.priority}`} to={`/agentes/tickets/${k.ticket_id}`}>
                    <span className="ticket-main">
                      <span className="ticket-ref"><code>{k.reference_label}</code> <PriorityPill ticket={k} lang={lang} /> <span className="pill neutral">{a.status[k.status] ?? k.status}</span>{k.origin === "synthetic" && <span className="pill o-bloqueo">{T[lang].reasoning.synthetic}</span>}</span>
                      <span className="ticket-reason">{a.reasons[k.reason_code] ?? k.reason_code} · <span className="muted">{k.queue}</span></span>
                      <span className="muted small ticket-summary">{k.summary}</span>
                    </span>
                    <span className="ticket-side">
                      <SlaPill ticket={k} lang={lang} />
                      <span className="muted small">{a.cols.due}: {formatDateTime(k.sla.due_at, lang)}</span>
                      <span className="muted small">{a.cols.age}: {a.age(k.age_minutes)}</span>
                      <span className="small">{k.assignee ? k.assignee.username : a.unassigned}</span>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          ))}
          <p className="muted small">{a.assumption}</p>
        </>
      )}
    </section>
  );
}
