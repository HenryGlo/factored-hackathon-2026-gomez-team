import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { Handoff } from "../api/types";
import ErrorNote from "../components/ErrorNote";
import { T } from "../lib/i18n";
import { describeError, useSession } from "../lib/session";

function show(v: unknown): string {
  return v === null || v === undefined ? "—" : typeof v === "object" ? JSON.stringify(v) : String(v);
}

export default function HandoffPage() {
  const { id = "" } = useParams();
  const { lang } = useSession();
  const t = T[lang];
  const [h, setH] = useState<Handoff | null>(null);
  const [error, setError] = useState<{ message: string; requestId: string | null } | null>(null);
  useEffect(() => { api.handoff(id).then(setH).catch((e) => setError(describeError(e, t))); }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (error) return <section className="page"><ErrorNote message={error.message} requestId={error.requestId} label={t.reference} /></section>;
  if (!h) return <p className="muted center" role="status">{t.loading}</p>;
  return (
    <section className="page handoff-detail" aria-labelledby="h-hof">
      <p><Link to="/consola">← {t.navInbox}</Link></p>
      <h1 id="h-hof">{h.request}</h1>
      <p className="meta"><code>{h.handoff_id}</code> · {h.reason_code} · {h.queue} · <span className={`pill p-${h.priority}`}>{h.priority}</span> · {h.status} · {h.language}</p>
      <div className="card"><h2>{lang === "pt" ? "Resumo" : "Resumen"}</h2><p className="bubble-text">{h.summary}</p></div>
      <div className="two-col">
        <div className="card">
          <h2>{lang === "pt" ? "O que o cliente afirma" : "Lo que afirma el cliente"}</h2>
          <ul className="plain">{h.customer_claims.map((c, i) => <li key={i}>“{c.claim}”</li>)}</ul>
        </div>
        <div className="card">
          <h2>{lang === "pt" ? "O que foi verificado" : "Lo verificado"}</h2>
          <table className="grid compact">
            <tbody>{h.verified_facts.map((f, i) => <tr key={i}><th>{f.fact}</th><td>{show(f.value)}</td><td className="muted small">{f.source_tool}</td></tr>)}</tbody>
          </table>
        </div>
      </div>
      <div className="two-col">
        <div className="card">
          <h2>{lang === "pt" ? "Ações confirmadas" : "Acciones confirmadas"}</h2>
          {h.actions_taken.length === 0 ? <p className="muted">—</p> : (
            <ul className="plain">{h.actions_taken.map((a, i) => <li key={i}>{a.action} · {a.status} · {a.verified ? t.verified : t.notVerified} {a.reference_id && <code>{a.reference_id}</code>}</li>)}</ul>
          )}
        </div>
        <div className="card">
          <h2>{lang === "pt" ? "Perguntas em aberto" : "Preguntas abiertas"}</h2>
          <ul className="plain">{h.open_questions.map((q, i) => <li key={i}>{q}</li>)}</ul>
        </div>
      </div>
      <div className="card">
        <h2>{lang === "pt" ? "Regras avaliadas" : "Reglas evaluadas"}</h2>
        <table className="grid compact">
          <tbody>{h.policy_evaluations.map((r, i) => <tr key={i}><th>{show(r.id ?? r.rule)}</th><td>{show(r.resultado ?? r.result)}</td><td>{show(r.motivo)}</td><td className="small mono">{show(r.evidencia ?? r.evidence)}</td></tr>)}</tbody>
        </table>
      </div>
      <div className="card">
        <h2>{lang === "pt" ? "Rastros" : "Trazas"}</h2>
        <ul className="plain">{h.trace_turn_ids.map((tid) => <li key={tid}><Link to={`/consola/trazas/${tid}`}><code>{tid}</code></Link></li>)}</ul>
      </div>
    </section>
  );
}
