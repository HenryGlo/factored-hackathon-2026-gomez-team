import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { MyTransactions, TxView } from "../api/types";
import ErrorNote from "../components/ErrorNote";
import { formatDate } from "../lib/format";
import { T } from "../lib/i18n";
import { describeError, useSession } from "../lib/session";

/** Línea de tiempo: los movimientos llegan ordenados; se agrupan por el día ya formateado por el backend. */
function groupByDay(txs: TxView[]): [string, TxView[]][] {
  const days: [string, TxView[]][] = [];
  for (const tx of txs) {
    const last = days[days.length - 1];
    if (last && last[0] === tx.date_label) last[1].push(tx);
    else days.push([tx.date_label, [tx]]);
  }
  return days;
}

export default function MovementsPage() {
  const { lang, onUnauthorized } = useSession();
  const t = T[lang];
  const navigate = useNavigate();
  const [filters, setFilters] = useState({ from: "", to: "", merchant: "", status: "" });
  const [data, setData] = useState<MyTransactions | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<{ message: string; requestId: string | null } | null>(null);

  const load = useCallback(async (f = filters) => {
    setLoading(true);
    setError(null);
    try {
      setData(await api.myTransactions({ ...f, lang }));
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) { onUnauthorized(); navigate("/login"); return; }
      setError(describeError(e, t));
    } finally {
      setLoading(false);
    }
  }, [filters, lang, navigate, onUnauthorized, t]);

  useEffect(() => { void load(); }, [lang]); // eslint-disable-line react-hooks/exhaustive-deps

  function submit(e: FormEvent) {
    e.preventDefault();
    void load(filters);
  }

  function dispute(id: string) {
    sessionStorage.removeItem("conversation_id");
    navigate("/chat", { state: { disputeTransactionId: id } });
  }

  return (
    <section className="page" aria-labelledby="h-mov">
      <h1 id="h-mov">{t.navMovements}</h1>
      <form className="filters" onSubmit={submit}>
        <label>{t.from}<input type="date" value={filters.from} onChange={(e) => setFilters({ ...filters, from: e.target.value })} /></label>
        <label>{t.to}<input type="date" value={filters.to} onChange={(e) => setFilters({ ...filters, to: e.target.value })} /></label>
        <label>{t.merchant}<input value={filters.merchant} maxLength={60} onChange={(e) => setFilters({ ...filters, merchant: e.target.value })} /></label>
        <label>{t.status}
          <select value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })}>
            <option value="">{t.all}</option>
            {Object.entries(t.statuses).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
        <button className="btn primary" type="submit" disabled={loading}>{t.filter}</button>
      </form>
      {error && <ErrorNote message={error.message} requestId={error.requestId} label={t.reference} onRetry={() => void load()} retryLabel={t.retry} />}
      {loading && <p className="muted" role="status">{t.loading}</p>}
      {data && !loading && (
        <>
          <p className="muted small" role="status">
            {formatDate(data.period.from, lang)} {t.chat.periodTo} {formatDate(data.period.to, lang)} · {t.movements(data.count)}
            {data.totals.map((x) => <span key={x.currency}> · {t.total}: {x.total_label}</span>)}
          </p>
          {data.transactions.length === 0 ? <p className="empty">{t.noMovements}</p> : (
            <ol className="timeline">
              {groupByDay(data.transactions).map(([day, txs]) => (
                <li key={day}>
                  <h2 className="timeline-day">{day}</h2>
                  <ul className="rows table-like">
                    {txs.map((tx) => (
                      <li key={tx.transaction_id}>
                        <span className="tx-line">
                          <span className="tx-label">{tx.label}</span>
                          <span className="tx-amount">{tx.amount_label}</span>
                          <span className="tx-meta"><span className={`status s-${tx.status.toLowerCase()}`}>{tx.status_label}</span>{tx.channel && <> · {tx.channel}</>}</span>
                        </span>
                        <button className="btn ghost small" onClick={() => dispute(tx.transaction_id)}
                          aria-label={`${t.disputeThis}: ${tx.label} ${tx.amount_label} ${tx.date_label}`}>{t.disputeThis}</button>
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
            </ol>
          )}
        </>
      )}
    </section>
  );
}
