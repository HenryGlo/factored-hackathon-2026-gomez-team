import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { CaseSummary, HandoffSummary } from "../api/types";
import ErrorNote from "../components/ErrorNote";
import { T } from "../lib/i18n";
import { describeError, useSession } from "../lib/session";

const QUEUES = ["", "fraude", "disputas", "tarjetas", "general"];
const STATUSES = ["", "pendiente", "tomado", "cerrado"];

export default function InboxPage() {
  const { lang, onUnauthorized } = useSession();
  const t = T[lang];
  const navigate = useNavigate();
  const [tab, setTab] = useState<"handoffs" | "cases">("handoffs");
  const [queue, setQueue] = useState("");
  const [status, setStatus] = useState("");
  const [handoffs, setHandoffs] = useState<HandoffSummary[] | null>(null);
  const [cases, setCases] = useState<CaseSummary[] | null>(null);
  const [error, setError] = useState<{ message: string; requestId: string | null } | null>(null);

  useEffect(() => {
    setError(null);
    const fail = (e: unknown) => {
      if (e instanceof ApiError && e.status === 401) { onUnauthorized(); navigate("/login"); return; }
      setError(describeError(e, t));
    };
    if (tab === "handoffs") api.handoffs({ queue, status }).then(setHandoffs).catch(fail);
    else api.cases().then(setCases).catch(fail);
  }, [tab, queue, status]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <section className="page" aria-labelledby="h-inbox">
      <h1 id="h-inbox">{t.navInbox}</h1>
      <div className="tabs" role="tablist">
        <button role="tab" aria-selected={tab === "handoffs"} className={tab === "handoffs" ? "tab active" : "tab"} onClick={() => setTab("handoffs")}>Handoffs</button>
        <button role="tab" aria-selected={tab === "cases"} className={tab === "cases" ? "tab active" : "tab"} onClick={() => setTab("cases")}>{lang === "pt" ? "Reclamações" : "Reclamos"}</button>
      </div>
      {error && <ErrorNote message={error.message} requestId={error.requestId} label={t.reference} />}
      {tab === "handoffs" ? (
        <>
          <div className="filters">
            <label>{lang === "pt" ? "Fila" : "Cola"}
              <select value={queue} onChange={(e) => setQueue(e.target.value)}>{QUEUES.map((q) => <option key={q} value={q}>{q || t.all}</option>)}</select>
            </label>
            <label>{t.status}
              <select value={status} onChange={(e) => setStatus(e.target.value)}>{STATUSES.map((s) => <option key={s} value={s}>{s || t.all}</option>)}</select>
            </label>
          </div>
          {!handoffs ? <p className="muted" role="status">{t.loading}</p> : handoffs.length === 0 ? <p className="empty">—</p> : (
            <table className="grid">
              <thead><tr><th>Handoff</th><th>{lang === "pt" ? "Motivo" : "Motivo"}</th><th>{lang === "pt" ? "Fila" : "Cola"}</th><th>{lang === "pt" ? "Prioridade" : "Prioridad"}</th><th>{t.status}</th><th>{lang === "pt" ? "Criado" : "Creado"}</th></tr></thead>
              <tbody>
                {handoffs.map((h) => (
                  <tr key={h.handoff_id}>
                    <td><Link to={`/consola/handoffs/${h.handoff_id}`}><code>{h.handoff_id}</code></Link></td>
                    <td>{h.reason_code}</td>
                    <td>{h.queue}</td>
                    <td><span className={`pill p-${h.priority}`}>{h.priority}</span></td>
                    <td>{h.status}</td>
                    <td>{new Date(h.created_at).toLocaleString(lang === "pt" ? "pt-BR" : "es")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      ) : !cases ? <p className="muted" role="status">{t.loading}</p> : (
        <table className="grid">
          <thead><tr><th>{lang === "pt" ? "Reclamação" : "Reclamo"}</th><th>{lang === "pt" ? "Cliente" : "Cliente"}</th><th>{lang === "pt" ? "Transação" : "Transacción"}</th><th>{t.status}</th><th>{lang === "pt" ? "Criado" : "Creado"}</th></tr></thead>
          <tbody>
            {cases.map((c) => (
              <tr key={c.case_id}>
                <td><code>{c.case_id}</code></td><td><code>{c.customer_id}</code></td><td><code>{c.transaction_id}</code></td>
                <td>{t.caseStatus[c.status] ?? c.status}</td><td>{new Date(c.created_at).toLocaleString(lang === "pt" ? "pt-BR" : "es")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
