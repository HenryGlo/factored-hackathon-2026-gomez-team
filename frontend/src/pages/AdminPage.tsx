// Panel de administración (rol admin): SLO con su presupuesto de error, resultados con n/N, costo frente al presupuesto,
// latencia por endpoint y por nodo, conversaciones recientes, visor de logs y el ciclo de mejora. Cada bloque responde la
// pregunta de su título; no hay gráficos decorativos.
import { useState, type FormEvent } from "react";
import { api } from "../api/client";
import type { AdminLogs, AdminOverview, AdminRoi, AdminSlo, Lang, Slo } from "../api/types";
import ErrorNote from "../components/ErrorNote";
import { formatDate, formatDateTime } from "../lib/format";
import { Empty, Loading } from "../components/States";
import { T } from "../lib/i18n";
import { useSession } from "../lib/session";
import { useApi } from "../lib/useApi";

const REPO = (import.meta.env.VITE_REPO_URL as string | undefined) ?? "https://github.com/HenryGlo/factored-hackathon-2026-gomez-team";

const pct = (x: number, lang: Lang) => `${(x * 100).toLocaleString(lang === "pt" ? "pt-BR" : "es", { maximumFractionDigits: 1 })} %`;
const usd = (x: number, digits = 4) => `$${x.toFixed(digits)}`;
const ms = (x: number | null | undefined) => (x === null || x === undefined ? "—" : `${Math.round(x)} ms`);

/** Valor de un SLO según su unidad: *_ms en milisegundos, *_share como porcentaje, hours en horas. */
function sloValue(obj: Record<string, number | null>, lang: Lang): string {
  return Object.entries(obj).map(([k, v]) => (v === null ? "—" : k.endsWith("_ms") ? `p95 ${Math.round(v)} ms` : k.includes("share") ? pct(v, lang) : k === "hours" ? `${v} h` : String(v))).join(" · ");
}

function Meter({ value, label, tone = "accent" }: { value: number; label: string; tone?: "accent" | "warn" | "err" }) {
  const v = Math.max(0, Math.min(1, value));
  return (
    <div className={`meter ${tone}`} role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(v * 100)} aria-label={label}>
      <i style={{ width: `${v * 100}%` }} />
    </div>
  );
}

function SloCard({ slo, lang }: { slo: Slo; lang: Lang }) {
  const a = T[lang].admin;
  const eb = slo.error_budget;
  const [open, setOpen] = useState(false);
  return (
    <li className={`card slo ${slo.met ? "met" : "unmet"}`}>
      <div className="slo-head">
        <h3>{a.sloNames[slo.id] ?? slo.id}</h3>
        <span className={`pill ${slo.met ? "sla-a_tiempo" : "sla-vencido"}`}>{slo.met ? a.met : a.notMet}</span>
      </div>
      <p className="muted small">{slo.description} · {pct(slo.objective, lang)} · {slo.window_days ? a.period(slo.window_days) : slo.window}</p>
      <dl className="kv">
        <div><dt>{a.current}</dt><dd className="big">{sloValue(slo.current, lang)}</dd></div>
        <div><dt>{a.target}</dt><dd>{sloValue(slo.target, lang)}</dd></div>
      </dl>
      <p className="small meter-label"><span>{a.budget}</span><strong>{pct(eb.consumed, lang)}</strong></p>
      <Meter value={eb.consumed} label={a.budget} tone={eb.consumed >= 1 ? "err" : eb.consumed >= 0.75 ? "warn" : "accent"} />
      <p className="muted small">{a.budgetDetail(eb.bad_events, eb.allowed_bad_events, eb.events)}</p>
      {slo.violations.length === 0 ? <p className="small">{a.violations(0)}</p> : (
        <>
          <button type="button" className="btn ghost small" aria-expanded={open} onClick={() => setOpen(!open)}>{a.violations(slo.violations.length)}</button>
          {open && (
            <ul className="plain small violations">
              {slo.violations.slice(0, 20).map((v, i) => (
                <li key={i}>{formatDateTime(v.at, lang)} · <code>{Object.entries(v).filter(([k]) => k !== "at").map(([k, x]) => `${k}=${String(x)}`).join(" ")}</code></li>
              ))}
            </ul>
          )}
        </>
      )}
    </li>
  );
}

function Logs({ lang }: { lang: Lang }) {
  const t = T[lang];
  const a = t.admin;
  const [form, setForm] = useState({ request_id: "", conversation_id: "", level: "", route: "" });
  const [q, setQ] = useState(form);
  const { data, loading, error, reload } = useApi<AdminLogs>(() => api.adminLogs({ ...q, limit: "100" }), [q]);
  const submit = (e: FormEvent) => { e.preventDefault(); setQ({ ...form }); };
  return (
    <section className="card" aria-labelledby="adm-logs">
      <h2 id="adm-logs">{a.logsTitle}</h2>
      <form className="filters" onSubmit={submit}>
        <label>{a.logFilters.request_id}<input value={form.request_id} maxLength={64} onChange={(e) => setForm({ ...form, request_id: e.target.value.trim() })} /></label>
        <label>{a.logFilters.conversation_id}<input value={form.conversation_id} maxLength={64} onChange={(e) => setForm({ ...form, conversation_id: e.target.value.trim() })} /></label>
        <label>{a.logFilters.level}
          <select value={form.level} onChange={(e) => setForm({ ...form, level: e.target.value })}>
            <option value="">{t.all}</option>{["info", "warning", "error"].map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
        </label>
        <label>{a.logFilters.route}<input value={form.route} maxLength={120} placeholder="/api/conversations" onChange={(e) => setForm({ ...form, route: e.target.value.trim() })} /></label>
        <button className="btn secondary" type="submit" disabled={loading}>{a.search}</button>
      </form>
      {error && <ErrorNote message={error.message} requestId={error.requestId} label={t.reference} onRetry={reload} retryLabel={t.retry} />}
      {data && (data.events.length === 0 ? <Empty title={a.noLogs} banky="searching" /> : (
        <div className="table-scroll" tabIndex={0} role="region" aria-labelledby="adm-logs">
          <table className="grid compact logs">
            <thead><tr><th>ts</th><th>{a.logFilters.level}</th><th>event</th><th>{a.logFilters.route}</th><th>status</th><th>ms</th><th>request_id</th></tr></thead>
            <tbody>
              {data.events.map((ev, i) => (
                <tr key={i} className={ev.level === "error" || (ev.status ?? 0) >= 500 ? "has-error" : undefined}>
                  <td className="mono small">{ev.ts.slice(11, 23)}</td>
                  <td><span className={`pill lv-${ev.level}`}>{ev.level}</span></td>
                  <td className="mono small">{ev.event}</td>
                  <td className="mono small">{ev.method} {ev.route}</td>
                  <td>{ev.status ?? ""}</td>
                  <td>{ev.latency_ms ?? ""}</td>
                  <td className="mono small">{ev.request_id ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
      {data && <p className="muted small">{a.kept(data.kept)} · {data.note}</p>}
    </section>
  );
}

export default function AdminPage() {
  const { lang } = useSession();
  const t = T[lang];
  const a = t.admin;
  const [days, setDays] = useState(7);
  const ov = useApi<AdminOverview>(() => api.adminOverview(days), [days]);
  const slo = useApi<AdminSlo>(() => api.adminSlo(), []);
  const roi = useApi<AdminRoi>(() => api.adminRoi(30), []);
  const o = ov.data;
  const maxP95 = Math.max(1, ...(o?.endpoints.map((e) => e.latency_ms_p95 ?? 0) ?? []));
  const maxNode = Math.max(1, ...(o?.nodes.map((n) => n.p95_ms ?? 0) ?? []));
  const costByDay = new Map<string, { llm: number; voice: number; calls: number; errors: number }>();
  for (const d of o?.llm_cost_daily ?? []) costByDay.set(d.day, { llm: d.cost_usd, voice: 0, calls: d.calls, errors: d.errors });
  for (const d of o?.voice_cost_daily ?? []) costByDay.set(d.day, { ...(costByDay.get(d.day) ?? { llm: 0, calls: 0, errors: 0 }), voice: d.cost_usd });
  const OUTCOMES = ["resolved_automatically", "resolved_after_clarification", "escalated", "no_action"] as const;

  return (
    <section className="page wide admin" aria-labelledby="h-admin">
      <header className="admin-head">
        <h1 id="h-admin">{a.title}</h1>
        <div className="actions">
          <div className="segmented" role="group" aria-label={a.period(days)}>
            {[1, 7, 30].map((d) => <button key={d} type="button" aria-pressed={days === d} onClick={() => setDays(d)}>{d} d</button>)}
          </div>
          <button className="btn ghost small" onClick={() => { ov.reload(); slo.reload(); }}>{a.refresh}</button>
        </div>
      </header>

      <section aria-labelledby="adm-slo">
        <h2 id="adm-slo">{a.sloTitle}</h2>
        {slo.error && <ErrorNote message={slo.error.message} requestId={slo.error.requestId} label={t.reference} onRetry={slo.reload} retryLabel={t.retry} />}
        {slo.loading && !slo.data && <Loading label={t.loading} />}
        {slo.data && <><ul className="slo-grid">{slo.data.slos.map((s) => <SloCard key={s.id} slo={s} lang={lang} />)}</ul><p className="muted small">{slo.data.assumption}</p></>}
      </section>

      {ov.error && <ErrorNote message={ov.error.message} requestId={ov.error.requestId} label={t.reference} onRetry={ov.reload} retryLabel={t.retry} />}
      {ov.loading && !o && <Loading label={t.loading} rows={6} />}
      {o && (
        <>
          <div className="two-col">
            <section className="card" aria-labelledby="adm-out">
              <h2 id="adm-out">{a.outcomesTitle}</h2>
              <p className="muted small">{a.period(o.outcomes.days)} · N = {o.outcomes.conversations}</p>
              <ul className="bars">
                {OUTCOMES.map((k) => (
                  <li key={k}>
                    <span className="bar-label"><span>{a.outcomes[k]}</span><strong>{o.outcomes[k].n}/{o.outcomes[k].of} · {pct(o.outcomes[k].share, lang)}</strong></span>
                    <Meter value={o.outcomes[k].share} label={a.outcomes[k]} tone={k === "escalated" ? "warn" : "accent"} />
                  </li>
                ))}
              </ul>
              {o.outcomes.handoffs.length > 0 && (
                <p className="small"><strong>{a.handoffReasons}:</strong> {o.outcomes.handoffs.map((h) => `${t.agent.reasons[h.reason_code] ?? h.reason_code} (${t.agent.priority[h.priority] ?? h.priority}) ${h.n}`).join(" · ")}</p>
              )}
            </section>
            <section className="card" aria-labelledby="adm-cost">
              <h2 id="adm-cost">{a.costTitle}</h2>
              <ul className="bars">
                <li>
                  <span className="bar-label"><span>{a.costToday}</span><strong>{usd(o.budget.today_cost_usd)} / {usd(o.budget.daily_cost_limit_usd, 2)} · {pct(o.budget.cost_consumed, lang)}</strong></span>
                  <Meter value={o.budget.cost_consumed} label={a.costToday} tone={o.budget.cost_consumed >= 1 ? "err" : o.budget.cost_consumed >= 0.75 ? "warn" : "accent"} />
                </li>
                <li>
                  <span className="bar-label"><span>{a.callsToday}</span><strong>{o.budget.today_calls} / {o.budget.daily_calls_limit} · {pct(o.budget.calls_consumed, lang)}</strong></span>
                  <Meter value={o.budget.calls_consumed} label={a.callsToday} tone={o.budget.calls_consumed >= 1 ? "err" : o.budget.calls_consumed >= 0.75 ? "warn" : "accent"} />
                </li>
              </ul>
              <h3>{a.costDaily}</h3>
              {costByDay.size === 0 ? <p className="muted small">{a.noCost}</p> : (
                <table className="grid compact">
                  <thead><tr><th>{a.day}</th><th>{a.calls}</th><th>{a.errors}</th><th>{a.llm}</th><th>{a.voice}</th></tr></thead>
                  <tbody>{[...costByDay.entries()].map(([day, c]) => <tr key={day}><td>{formatDate(day, lang)}</td><td>{c.calls}</td><td>{c.errors}</td><td>{usd(c.llm)}</td><td>{usd(c.voice)}</td></tr>)}</tbody>
                </table>
              )}
            </section>
          </div>

          <div className="admin-tables">          {/* tablas anchas: una debajo de la otra, cada una con todo el ancho */}
            <section className="card" aria-labelledby="adm-ep">
              <h2 id="adm-ep">{a.endpointsTitle}</h2>
              <p className="muted small">{a.endpointsNote}</p>
              <div className="table-scroll" tabIndex={0} role="region" aria-labelledby="adm-ep">
                <table className="grid compact">
                  <thead><tr><th>Endpoint</th><th>{a.requests}</th><th>4xx / 5xx / 429</th><th>p50</th><th colSpan={2}>p95</th></tr></thead>
                  <tbody>
                    {[...o.endpoints].sort((x, y) => (y.latency_ms_p95 ?? 0) - (x.latency_ms_p95 ?? 0)).map((e) => (
                      <tr key={`${e.method} ${e.route}`} className={e.errors_5xx > 0 ? "has-error" : undefined}>
                        <td className="mono small">{e.method} {e.route}</td><td>{e.requests}</td><td>{e.errors_4xx} / {e.errors_5xx} / {e.rate_limited}</td>
                        <td>{ms(e.latency_ms_p50)}</td><td>{ms(e.latency_ms_p95)}</td>
                        <td className="bar-cell"><span className="trace-bar" aria-hidden="true"><i style={{ width: `${((e.latency_ms_p95 ?? 0) / maxP95) * 100}%` }} /></span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
            <section className="card" aria-labelledby="adm-nodes">
              <h2 id="adm-nodes">{a.nodesTitle}</h2>
              <p className="muted small">{a.period(o.days)}</p>
              <div className="table-scroll" tabIndex={0} role="region" aria-labelledby="adm-nodes">
                <table className="grid compact">
                  <thead><tr><th>{a.node}</th><th>{a.kind}</th><th>{a.calls}</th><th>{a.errors}</th><th>p50</th><th colSpan={2}>p95</th><th>{a.cost}</th></tr></thead>
                  <tbody>
                    {[...o.nodes].sort((x, y) => (y.p95_ms ?? 0) - (x.p95_ms ?? 0)).map((n) => (
                      <tr key={n.node} className={n.errors > 0 ? "has-error" : undefined}>
                        <td className="mono small">{n.node}</td><td><span className={`pill k-${n.kind}`}>{n.kind.toUpperCase()}</span></td><td>{n.calls}</td><td>{n.errors}</td>
                        <td>{ms(n.p50_ms)}</td><td>{ms(n.p95_ms)}</td>
                        <td className="bar-cell"><span className="trace-bar" aria-hidden="true"><i style={{ width: `${((n.p95_ms ?? 0) / maxNode) * 100}%` }} /></span></td>
                        <td>{usd(n.cost_usd)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </div>

          <section className="card" aria-labelledby="adm-recent">
            <h2 id="adm-recent">{a.recentTitle}</h2>
            <div className="table-scroll" tabIndex={0} role="region" aria-labelledby="adm-recent">
              <table className="grid compact">
                <thead><tr><th>{a.conv.when}</th><th>ID</th><th>{a.conv.intent}</th><th>{a.conv.turns}</th><th>{t.status}</th><th>{a.conv.result}</th><th>{a.conv.feedback}</th></tr></thead>
                <tbody>
                  {o.recent_conversations.map((c) => (
                    <tr key={c.conversation_id}>
                      <td>{formatDateTime(c.created_at, lang)}</td><td className="mono small">{c.conversation_id}</td><td>{c.intent ?? "—"}</td><td>{c.customer_turns}</td><td>{c.state}</td>
                      <td>{c.has_case && <span className="pill o-reclamo">{a.conv.case}</span>} {c.has_handoff && <span className="pill o-persona">{a.conv.handoff}</span>}</td>
                      <td>{c.feedback === "up" ? "👍" : c.feedback === "down" ? "👎" : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}

      <Logs lang={lang} />

      <div className="two-col">
        <section className="card" aria-labelledby="adm-improve">
          <h2 id="adm-improve">{a.improveTitle}</h2>
          <p>{a.improveText}</p>
          <ul className="plain links">
            <li><a href={`${REPO}/pulls?q=is%3Apr+head%3Aimprove%2F`} target="_blank" rel="noopener noreferrer">{a.improvePrs}</a></li>
            <li><a href={`${REPO}/tree/main/reports`} target="_blank" rel="noopener noreferrer">{a.improveReports}</a></li>
            <li><a href={`${REPO}/blob/main/docs/improvement-loop.md`} target="_blank" rel="noopener noreferrer">{a.improveDocs}</a></li>
          </ul>
        </section>
        {roi.data && (
          <section className="card" aria-labelledby="adm-roi">
            <h2 id="adm-roi">{a.roiTitle}</h2>
            <p className="notice warning small">{roi.data.label}</p>
            <dl className="kv">
              <div><dt>{a.roi.monthly}</dt><dd className="big">{usd(roi.data.estimate.monthly_saving_usd, 0)}</dd></div>
              <div><dt>{a.roi.perCase}</dt><dd>{usd(roi.data.estimate.saving_per_case_usd, 2)}</dd></div>
              <div><dt>{a.roi.breakEven}</dt><dd>{roi.data.estimate.break_even_cases_per_month}</dd></div>
              <div><dt>{a.roi.notEscalated}</dt><dd>{pct(roi.data.measured.not_escalated_share, lang)} (N = {roi.data.measured.conversations})</dd></div>
            </dl>
          </section>
        )}
      </div>
    </section>
  );
}
