import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { MyCases } from "../api/types";
import ErrorNote from "../components/ErrorNote";
import CopyRef from "../components/CopyRef";
import { formatDate } from "../lib/format";
import { T } from "../lib/i18n";
import { describeError, useSession } from "../lib/session";

export default function CasesPage() {
  const { lang, onUnauthorized } = useSession();
  const t = T[lang];
  const navigate = useNavigate();
  const [data, setData] = useState<MyCases | null>(null);
  const [error, setError] = useState<{ message: string; requestId: string | null } | null>(null);

  const load = () => {
    setError(null);
    api.myCases(lang).then(setData).catch((e) => {
      if (e instanceof ApiError && e.status === 401) { onUnauthorized(); navigate("/login"); return; }
      setError(describeError(e, t));
    });
  };
  useEffect(load, [lang]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <section className="page" aria-labelledby="h-cases">
      <h1 id="h-cases">{t.navCases}</h1>
      {error && <ErrorNote message={error.message} requestId={error.requestId} label={t.reference} onRetry={load} retryLabel={t.retry} />}
      {!data && !error && <p className="muted" role="status">{t.loading}</p>}
      {data && (data.cases.length === 0 ? <p className="empty">{t.noCases}</p> : (
        <ul className="case-cards">
          {data.cases.map((c) => {
            const steps = t.history.caseSteps;
            const at = steps.indexOf(c.status);
            return (
              <li key={c.case_id} className="card">
                <div className="case-head">
                  <span className="tx-line">
                    <span className="tx-label">{c.transaction.label}</span>
                    <span className="tx-amount">{c.transaction.amount_label}</span>
                    <span className="tx-meta">{c.transaction.date_label} · {t.reason[c.reason_code] ?? c.reason_code}</span>
                  </span>
                  <CopyRef value={c.reference_label ?? c.case_id} lang={lang} />
                </div>
                {at >= 0 ? (
                  <ol className="stepper" aria-label={t.history.caseTimeline}>
                    {steps.map((step, i) => (
                      <li key={step} className={i < at ? "done" : i === at ? "current" : "todo"} aria-current={i === at ? "step" : undefined}>
                        <span className="step-dot" aria-hidden="true">{i < at ? "✓" : i + 1}</span>
                        <span>{t.caseStatus[step] ?? step}{i === 0 && <span className="muted small"> · {formatDate(c.created_at, lang)}</span>}</span>
                      </li>
                    ))}
                  </ol>
                ) : (
                  <p className="case-final"><span className={`pill c-${c.status}`}>{t.caseStatus[c.status] ?? c.status}</span> <span className="muted small">{t.history.caseOpened} {formatDate(c.created_at, lang)}</span></p>
                )}
              </li>
            );
          })}
        </ul>
      ))}
    </section>
  );
}
