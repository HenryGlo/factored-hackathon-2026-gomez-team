import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { MyCases } from "../api/types";
import ErrorNote from "../components/ErrorNote";
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
        <ul className="rows table-like">
          {data.cases.map((c) => (
            <li key={c.case_id}>
              <span className="tx-line">
                <span className="tx-label">{c.transaction.label}</span>
                <span className="tx-amount">{c.transaction.amount_label}</span>
                <span className="tx-meta">{c.transaction.date_label} · {t.reason[c.reason_code] ?? c.reason_code}</span>
              </span>
              <span className="case-side">
                <span className={`pill c-${c.status}`}>{t.caseStatus[c.status] ?? c.status}</span>
                <code className="small">{c.case_id}</code>
              </span>
            </li>
          ))}
        </ul>
      ))}
    </section>
  );
}
