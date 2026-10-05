// Herramientas de análisis del administrador, todas de solo lectura y sin mensajes de clientes:
// simulador de umbrales (qué habría decidido la política con otros valores), temas de lo que el asistente no supo atender
// y comercios con más reclamos. Los grupos de pocos casos llegan sin número y se muestran como "< N".
import { useState, type FormEvent } from "react";
import { api } from "../api/client";
import type { AdminMerchants, AdminSimulation, AdminTopics, AnalyticsCount, Lang } from "../api/types";
import { T } from "../lib/i18n";
import { describeError, useSession } from "../lib/session";
import { useApi } from "../lib/useApi";
import ErrorNote from "./ErrorNote";
import { Loading } from "./States";

type Origin = "all" | "real" | "synthetic";
const pct = (x: number, lang: Lang) => `${(x * 100).toLocaleString(lang === "pt" ? "pt-BR" : "es", { maximumFractionDigits: 1 })} %`;
const count = (c: AnalyticsCount, min: number) => (c.suppressed ? `< ${min}` : String(c.n));

function Simulator({ days, origin }: { days: number; origin: Origin }) {
  const { lang } = useSession();
  const t = T[lang];
  const s = t.insights.sim;
  const base = useApi<AdminSimulation>(() => api.adminSimulate(days, origin, {}), [days, origin]);
  const [form, setForm] = useState<{ window: string; risk: string; max: string } | null>(null);
  const [result, setResult] = useState<AdminSimulation | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ message: string; requestId: string | null } | null>(null);
  const cur = base.data?.current;
  const f = form ?? (cur ? { window: String(cur.dispute_window_days), risk: String(cur.risk_threshold), max: String(cur.self_service_max_usd) } : null);

  async function run(e: FormEvent) {
    e.preventDefault();
    if (!f) return;
    setBusy(true); setError(null);
    try {
      setResult(await api.adminSimulate(days, origin, { dispute_window_days: Number(f.window), risk_threshold: Number(f.risk), self_service_max_usd: Number(f.max) }));
    } catch (err) {
      setError(describeError(err, t));
    } finally {
      setBusy(false);
    }
  }
  const r = result ?? base.data;
  const OUT = ["permitir", "informar", "escalar"] as const;
  return (
    <section className="card" aria-labelledby="adm-sim">
      <h3 id="adm-sim">{s.title}</h3>
      <p className="muted small">{s.hint}</p>
      {base.error && <ErrorNote message={base.error.message} requestId={base.error.requestId} label={t.reference} onRetry={base.reload} retryLabel={t.retry} />}
      {base.loading && !base.data && <Loading label={t.loading} rows={2} />}
      {f && cur && (
        <form className="filters sim-form" onSubmit={run}>
          <label>{s.window}<input type="number" min={1} max={365} step={1} value={f.window} onChange={(e) => setForm({ ...f, window: e.target.value })} required />
            <span className="muted small">{s.now}: {cur.dispute_window_days}</span></label>
          <label>{s.risk}<input type="number" min={0.01} max={0.99} step={0.01} value={f.risk} onChange={(e) => setForm({ ...f, risk: e.target.value })} required />
            <span className="muted small">{s.now}: {cur.risk_threshold.toFixed(2)}</span></label>
          <label>{s.max}<input type="number" min={0} step={10} value={f.max} onChange={(e) => setForm({ ...f, max: e.target.value })} required />
            <span className="muted small">{s.now}: {cur.self_service_max_usd}</span></label>
          <button className="btn primary" type="submit" disabled={busy}>{s.run}</button>
        </form>
      )}
      {error && <ErrorNote message={error.message} requestId={error.requestId} label={t.reference} />}
      {r && (
        <>
          <table className="grid compact">
            <thead><tr><th>{s.decision}</th><th>{s.today}</th><th>{s.proposed}</th></tr></thead>
            <tbody>{OUT.map((k) => (
              <tr key={k}><th scope="row">{s.outcomes[k]}</th><td>{count(r.before[k], r.min_group)}</td>
                <td>{count(r.after[k], r.min_group)}{r.after[k].share !== null ? ` · ${pct(r.after[k].share as number, lang)}` : ""}</td></tr>
            ))}</tbody>
          </table>
          <p className="small"><strong>{s.changed}:</strong> {count(r.changed, r.min_group)} {s.of} {r.evaluated}.
            {r.changes.map((c, i) => <span key={i}> {s.outcomes[c.from as "permitir"] ?? c.from} → {s.outcomes[c.to as "permitir"] ?? c.to} ({c.rule}): {count(c, r.min_group)}.</span>)}
            {r.changes.length === 0 && result && <span> {s.noChange}</span>}</p>
          {(r.not_reproducible.suppressed || (r.not_reproducible.n ?? 0) > 0) && <p className="notice warning small">{s.stale(count(r.not_reproducible, r.min_group))}</p>}
          <p className="muted small">{s.note}</p>
        </>
      )}
    </section>
  );
}

function Topics({ days, origin }: { days: number; origin: Origin }) {
  const { lang } = useSession();
  const t = T[lang];
  const x = t.insights.topics;
  const { data: d, loading, error, reload } = useApi<AdminTopics>(() => api.adminTopics(days, origin), [days, origin]);
  return (
    <section className="card" aria-labelledby="adm-topics">
      <h3 id="adm-topics">{x.title}</h3>
      <p className="muted small">{x.hint}</p>
      {error && <ErrorNote message={error.message} requestId={error.requestId} label={t.reference} onRetry={reload} retryLabel={t.retry} />}
      {loading && !d && <Loading label={t.loading} rows={2} />}
      {d && (
        <>
          <p className="small"><strong>{count(d.not_understood, d.min_group)}</strong> {x.of(d.classified_turns)}{d.not_understood.share !== null ? ` (${pct(d.not_understood.share, lang)})` : ""}</p>
          {d.clusters.length === 0 ? <p className="muted">{x.none(d.min_group)}</p> : (
            <ul className="topic-list">
              {d.clusters.map((c, i) => (
                <li key={i}><span className="num">{count(c, d.min_group)}</span>
                  <span className="topic-terms">{c.terms.map((term) => <span key={term} className="pill neutral">{term}</span>)}</span></li>
              ))}
            </ul>
          )}
          <p className="muted small">{x.unclustered}: {count(d.unclustered, d.min_group)}. {x.note}</p>
        </>
      )}
    </section>
  );
}

function Merchants({ days, origin }: { days: number; origin: Origin }) {
  const { lang } = useSession();
  const t = T[lang];
  const m = t.insights.merchants;
  const { data: d, loading, error, reload } = useApi<AdminMerchants>(() => api.adminMerchants(days, origin), [days, origin]);
  return (
    <section className="card" aria-labelledby="adm-merchants">
      <h3 id="adm-merchants">{m.title}</h3>
      <p className="muted small">{m.hint}</p>
      {error && <ErrorNote message={error.message} requestId={error.requestId} label={t.reference} onRetry={reload} retryLabel={t.retry} />}
      {loading && !d && <Loading label={t.loading} rows={2} />}
      {d && (d.merchants.length === 0 ? <p className="muted">{m.none(d.min_group)}</p> : (
        <table className="grid compact">
          <thead><tr><th>{m.merchant}</th><th>{m.disputes}</th><th>{m.share}</th><th>{m.purchases}</th><th>{m.lift}</th></tr></thead>
          <tbody>{d.merchants.map((r) => (
            <tr key={r.merchant} className={r.flag ? "has-error" : undefined}>
              <th scope="row">{r.merchant}</th><td>{r.n}</td><td>{pct(r.share, lang)}</td><td>{r.purchase_share !== null ? pct(r.purchase_share, lang) : "—"}</td>
              <td>{r.lift !== null ? `× ${r.lift.toLocaleString(lang === "pt" ? "pt-BR" : "es")}` : "—"}{r.flag && <span className="pill p-alta"> {m.review}</span>}</td>
            </tr>
          ))}</tbody>
        </table>
      ))}
      {d && <p className="muted small">{m.total(d.disputes)} · {m.others}: {count(d.other_merchants, d.min_group)}. {m.note}</p>}
    </section>
  );
}

export default function AdminInsights() {
  const { lang } = useSession();
  const a = T[lang].analytics;
  const i = T[lang].insights;
  const [days, setDays] = useState(30);
  const [origin, setOrigin] = useState<Origin>("all");
  return (
    <section aria-labelledby="adm-insights" className="analytics">
      <header className="admin-head">
        <h2 id="adm-insights">{i.title}</h2>
        <div className="actions">
          <div className="segmented" role="group" aria-label={a.origin}>
            {(["all", "real", "synthetic"] as const).map((o) => <button key={o} type="button" aria-pressed={origin === o} onClick={() => setOrigin(o)}>{a.origins[o]}</button>)}
          </div>
          <div className="segmented" role="group" aria-label={a.period}>
            {[7, 30, 90].map((n) => <button key={n} type="button" aria-pressed={days === n} onClick={() => setDays(n)}>{n} d</button>)}
          </div>
        </div>
      </header>
      <p className="muted small">{i.readOnly}</p>
      <Simulator days={days} origin={origin} />
      <div className="two-col">
        <Topics days={days} origin={origin} />
        <Merchants days={days} origin={origin} />
      </div>
    </section>
  );
}
