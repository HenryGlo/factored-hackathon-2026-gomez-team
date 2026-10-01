import { Fragment, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { Trace } from "../api/types";
import ErrorNote from "../components/ErrorNote";
import { T } from "../lib/i18n";
import { describeError, useSession } from "../lib/session";

export default function TracePage() {
  const { turnId = "" } = useParams();
  const { lang } = useSession();
  const t = T[lang];
  const [trace, setTrace] = useState<Trace | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  const [error, setError] = useState<{ message: string; requestId: string | null } | null>(null);
  useEffect(() => { api.trace(turnId).then(setTrace).catch((e) => setError(describeError(e, t))); }, [turnId]); // eslint-disable-line react-hooks/exhaustive-deps

  if (error) return <section className="page"><ErrorNote message={error.message} requestId={error.requestId} label={t.reference} /></section>;
  if (!trace) return <p className="muted center" role="status">{t.loading}</p>;
  return (
    <section className="page" aria-labelledby="h-trace">
      <p><Link to="/consola">← {t.navInbox}</Link></p>
      <h1 id="h-trace">{lang === "pt" ? "Rastro do turno" : "Traza del turno"}</h1>
      <p className="meta"><code>{trace.turn_id}</code> · {trace.state_before ?? "—"} → {trace.state_after} · {trace.totals.latency_ms} ms · ${Number(trace.totals.cost_usd).toFixed(4)}</p>
      <table className="grid trace">
        <thead><tr><th>#</th><th>{lang === "pt" ? "Nó" : "Nodo"}</th><th>{lang === "pt" ? "Tipo" : "Tipo"}</th><th>{lang === "pt" ? "Implementação / modelo" : "Implementación / modelo"}</th><th>ms</th><th>USD</th><th /></tr></thead>
        <tbody>
          {trace.steps.map((s) => (
            <Fragment key={s.step_seq}>
              <tr className={s.error ? "has-error" : undefined}>
                <td>{s.step_seq}</td>
                <td className="mono">{s.node}</td>
                <td><span className={`pill k-${s.kind}`}>{s.kind.toUpperCase()}</span></td>
                <td className="mono small">{s.model_id ?? s.model ?? s.implementation ?? s.tool ?? ""}{s.prompt_version ? ` · ${s.prompt_version}` : ""}</td>
                <td>{s.latency_ms ?? 0}</td>
                <td>{s.cost_usd ? Number(s.cost_usd).toFixed(4) : ""}</td>
                <td><button className="btn ghost small" aria-expanded={open === s.step_seq} onClick={() => setOpen(open === s.step_seq ? null : s.step_seq)}>
                  {open === s.step_seq ? "−" : "+"}<span className="sr-only"> {s.node}</span></button></td>
              </tr>
              {open === s.step_seq && (
                <tr className="detail"><td colSpan={7}>
                  {s.error && <p className="notice error">{s.error}</p>}
                  <pre>{JSON.stringify({ payload: s.payload, rules: s.rules }, null, 2)}</pre>
                </td></tr>
              )}
            </Fragment>
          ))}
        </tbody>
      </table>
    </section>
  );
}
