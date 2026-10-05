// Analítica agregada de los pasos de decisión del asistente (GET /api/admin/analytics): solo conteos y proporciones. El
// administrador no ve mensajes ni conversaciones; los grupos de pocos casos llegan sin número y se muestran como «< N».
import { useState } from "react";
import { api } from "../api/client";
import type { AdminAnalytics as Analytics, AnalyticsCell, Lang } from "../api/types";
import { localeOf } from "../lib/format";
import { T } from "../lib/i18n";
import { useSession } from "../lib/session";
import { useApi } from "../lib/useApi";
import ErrorNote from "./ErrorNote";
import { Loading } from "./States";

const pct = (x: number, lang: Lang) => `${(x * 100).toLocaleString(localeOf(lang), { maximumFractionDigits: 1 })} %`;

function Bars({ rows: raw, min, lang, tone, names }: { rows: AnalyticsCell[]; min: number; lang: Lang; tone?: (key: string) => "accent" | "warn" | "err"; names?: Record<string, string> }) {
  if (raw.length === 0) return <p className="muted">—</p>;
  const rows = raw.map((x) => ({ ...x, label: names?.[x.key] ?? x.label }));      // la etiqueta del backend viene en español
  return (
    <ul className="bars">
      {rows.map((x) => (
        <li key={x.key}>
          <span className="bar-label"><span>{x.label}</span><strong>{x.suppressed ? `< ${min}` : `${x.n}${x.share !== null ? ` · ${pct(x.share, lang)}` : ""}`}</strong></span>
          <div className={`meter ${tone ? tone(x.key) : "accent"}`} role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round((x.share ?? 0) * 100)} aria-label={x.label}>
            <i style={{ width: `${Math.min(1, x.share ?? 0) * 100}%` }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

export default function AdminAnalytics() {
  const { lang } = useSession();
  const t = T[lang];
  const a = t.analytics;
  const b = t.backend;
  const guardNames = (rows: AnalyticsCell[]) => Object.fromEntries(rows.map((x) => [x.key, x.key.startsWith("respaldo:") ? b.fallbackIn(x.key.slice(9)) : b.guardrails[x.key] ?? x.label]));
  const [days, setDays] = useState(30);
  const [origin, setOrigin] = useState<"all" | "real" | "synthetic">("all");
  const { data: d, loading, error, reload } = useApi<Analytics>(() => api.adminAnalytics(days, origin), [days, origin]);
  return (
    <section aria-labelledby="adm-analytics" className="analytics">
      <header className="admin-head">
        <h2 id="adm-analytics">{a.title}</h2>
        <div className="actions">
          <div className="segmented" role="group" aria-label={a.origin}>
            {(["all", "real", "synthetic"] as const).map((o) => <button key={o} type="button" aria-pressed={origin === o} onClick={() => setOrigin(o)}>{a.origins[o]}</button>)}
          </div>
          <div className="segmented" role="group" aria-label={a.period}>
            {[7, 30, 90].map((n) => <button key={n} type="button" aria-pressed={days === n} onClick={() => setDays(n)}>{n} d</button>)}
          </div>
        </div>
      </header>
      <p className="muted small">{a.privacy(d?.min_group ?? 5)}</p>
      {error && <ErrorNote message={error.message} requestId={error.requestId} label={t.reference} onRetry={reload} retryLabel={t.retry} />}
      {loading && !d && <Loading label={t.loading} rows={4} />}
      {d && (
        <>
          {d.totals.synthetic_conversations > 0 && origin !== "real" && <p className="notice warning small">{a.syntheticNote(d.totals.synthetic_conversations, d.totals.conversations)}</p>}
          <dl className="kv analytics-totals">
            <div><dt>{a.conversations}</dt><dd className="big">{d.totals.conversations}</dd></div>
            <div><dt>{a.turns}</dt><dd className="big">{d.totals.assistant_turns}</dd></div>
            <div><dt>{a.llmCalls}</dt><dd className="big">{d.totals.llm_calls}</dd></div>
            <div><dt>{a.llmPerTurn}</dt><dd className="big">{d.totals.assistant_turns ? (d.totals.llm_calls / d.totals.assistant_turns).toFixed(2) : "—"}</dd></div>
          </dl>
          <div className="two-col">
            <section className="card"><h3>{a.intents}</h3><p className="muted small">{a.intentsHint}</p><Bars rows={d.understanding.intents} min={d.min_group} lang={lang} names={b.intents} /></section>
            <section className="card"><h3>{a.funnel}</h3><p className="muted small">{a.funnelHint}</p><Bars rows={d.funnel} min={d.min_group} lang={lang} names={b.states} /></section>
          </div>
          <div className="two-col">
            <section className="card"><h3>{a.dataFields}</h3><p className="muted small">{a.dataHint(d.data.extractions)}</p><Bars rows={d.data.fields} min={d.min_group} lang={lang} names={b.fields} /></section>
            <section className="card"><h3>{a.guardrails}</h3><p className="muted small">{a.guardrailsHint(d.totals.assistant_turns)}</p>
              <Bars rows={d.guardrails} min={d.min_group} lang={lang} names={guardNames(d.guardrails)} tone={(k) => (k.startsWith("respaldo") || k === "handoff_fallido" ? "err" : k === "sospecha_manipulacion" || k === "token_invalido" ? "warn" : "accent")} /></section>
          </div>
          <div className="two-col">
            <section className="card"><h3>{a.policy}</h3><p className="muted small">{a.policyHint}</p>
              <Bars rows={d.policy.results} min={d.min_group} lang={lang} names={b.policy} tone={(k) => (k === "escalar" ? "warn" : "accent")} />
              <table className="grid compact"><thead><tr><th>{a.rule}</th><th>{a.evaluated}</th><th>{a.results}</th></tr></thead>
                <tbody>{d.policy.rules.map((x) => (
                  <tr key={x.rule}><th scope="row">{x.rule}</th><td>{x.total}</td><td>{x.results.map((y) => `${b.policy[y.key] ?? y.label}: ${y.suppressed ? `< ${d.min_group}` : y.n}`).join(" · ")}</td></tr>
                ))}</tbody></table>
            </section>
            <section className="card"><h3>{a.risk}</h3><Bars rows={d.risk} min={d.min_group} lang={lang} names={b.risk} tone={(k) => (k === "alto" ? "err" : k === "medio" ? "warn" : "accent")} />
              <h3>{a.clarify}</h3><Bars rows={d.clarification.decisions} min={d.min_group} lang={lang} names={b.clarify} />
              <h3>{a.rounds}</h3><Bars rows={d.clarification.rounds} min={d.min_group} lang={lang} /></section>
          </div>
          <div className="two-col">
            <section className="card"><h3>{a.outcomes}</h3>
              {d.outcomes.languages.map((l) => <div key={l}><p className="small"><strong>{T[lang].languageNames[l] ?? l.toUpperCase()}</strong></p><Bars rows={d.outcomes.by_language[l]} min={d.min_group} lang={lang} names={b.outcomes} tone={(k) => (k.startsWith("pasó") ? "warn" : "accent")} /></div>)}
            </section>
            <section className="card"><h3>{a.handoffs}</h3><Bars rows={d.handoff_reasons.map((x) => ({ ...x, label: t.agent.reasons[x.key] ?? x.label }))} min={d.min_group} lang={lang} tone={() => "warn"} />
              <h3>{a.sources}</h3><Bars rows={d.understanding.source} min={d.min_group} lang={lang} names={b.sources} tone={(k) => (k.startsWith("respaldo") ? "err" : "accent")} />
              <h3>{a.feedback}</h3><Bars rows={d.feedback.map((x) => ({ ...x, label: x.key === "up" ? "👍" : "👎" }))} min={d.min_group} lang={lang} tone={(k) => (k === "down" ? "warn" : "accent")} /></section>
          </div>
        </>
      )}
    </section>
  );
}
