// Un componente por tipo de bloque (docs/api-contract.md, "Catálogo de bloques de UI").
// Reglas: el texto es texto plano (React escapa; nada de HTML inyectado); solo los bloques del ÚLTIMO turno aceptan clics;
// cada botón se deshabilita al primer clic; "listo" solo con un result verified: true.
import { useState } from "react";
import type { Action, Block, CandidateListBlock, ConversationState, Lang, ResultBlock, TxView } from "../../api/types";
import { T } from "../../lib/i18n";

export interface BlockProps {
  block: Block;
  lang: Lang;
  state: ConversationState;
  /** true solo en el último turno del asistente y sin un turno en curso */
  active: boolean;
  onAction: (action: Action, label: string) => void;
}

function TxLine({ tx }: { tx: TxView }) {
  return (
    <span className="tx-line">
      <span className="tx-label">{tx.label}</span>
      <span className="tx-amount">{tx.amount_label}</span>
      <span className="tx-meta">{tx.date_label} · <span className={`status s-${tx.status.toLowerCase()}`}>{tx.status_label}</span></span>
    </span>
  );
}

/** Botón que se deshabilita al primer clic (evita doble envío; la Idempotency-Key cubre los reintentos). */
function OnceButton({ label, action, active, onAction, kind = "secondary", ariaLabel }: {
  label: string; action: Action; active: boolean; onAction: BlockProps["onAction"]; kind?: "primary" | "secondary" | "ghost"; ariaLabel?: string;
}) {
  const [used, setUsed] = useState(false);
  return (
    <button className={`btn ${kind}`} disabled={!active || used} aria-label={ariaLabel}
      onClick={() => { setUsed(true); onAction(action, label); }}>
      {label}
    </button>
  );
}

function CandidateList({ block, active, onAction, lang }: { block: CandidateListBlock } & Omit<BlockProps, "block" | "state">) {
  const t = T[lang];
  const [chosen, setChosen] = useState<string[]>(block.suggested ?? []);
  const [used, setUsed] = useState(false);
  const send = (action: Action, label: string) => { setUsed(true); onAction(action, label); };
  if (!block.multi_select) {
    return (
      <div className="card list" role="group" aria-label={block.prompt}>
        <ul className="choices">
          {block.candidates.map((c, i) => (
            <li key={c.transaction_id}>
              <button className="choice" disabled={!active || used} onClick={() => send({ type: "select_candidate", transaction_id: c.transaction_id }, `${i + 1}. ${c.label}`)}>
                <span className="num" aria-hidden="true">{i + 1}</span><TxLine tx={c} />
              </button>
            </li>
          ))}
        </ul>
        {block.allow_none && (
          <div className="actions"><button className="btn ghost" disabled={!active || used} onClick={() => send({ type: "reject" }, t.none)}>{t.none}</button></div>
        )}
        <p className="muted small">{block.round}/{block.max_rounds}</p>
      </div>
    );
  }
  const all = block.candidates.map((c) => c.transaction_id);
  const toggle = (id: string) => setChosen((xs) => (xs.includes(id) ? xs.filter((x) => x !== id) : [...xs, id]));
  return (
    <fieldset className="card list" disabled={!active || used}>
      <legend className="sr-only">{block.prompt}</legend>
      <ul className="choices">
        {block.candidates.map((c) => (
          <li key={c.transaction_id}>
            <label className="choice check">
              <input type="checkbox" checked={chosen.includes(c.transaction_id)} onChange={() => toggle(c.transaction_id)} />
              <TxLine tx={c} />
              {block.suggested?.includes(c.transaction_id) && <span className="tag">{t.suggested}</span>}
            </label>
          </li>
        ))}
      </ul>
      <div className="actions">
        <button className="btn primary" disabled={chosen.length === 0}
          onClick={() => send(chosen.length === 1 ? { type: "select_candidate", transaction_id: chosen[0] } : { type: "select_candidates", transaction_ids: chosen },
            t.selectChosen(chosen.length))}>
          {t.selectChosen(chosen.length)}
        </button>
        <button className="btn secondary" onClick={() => send({ type: "select_candidates", transaction_ids: all }, block.select_all_label ?? t.selectAll)}>
          {block.select_all_label ?? t.selectAll}
        </button>
        {block.allow_none && <button className="btn ghost" onClick={() => send({ type: "reject" }, t.none)}>{t.none}</button>}
      </div>
    </fieldset>
  );
}

function Result({ block, lang }: { block: ResultBlock; lang: Lang }) {
  const t = T[lang];
  const ok = block.status === "success" && block.verified;          // "listo" solo con verified: true
  return (
    <div className={`card result ${ok ? "ok" : block.status === "partial" ? "partial" : "fail"}`} role="status">
      <div className="result-head">
        <span aria-hidden="true">{ok ? "✓" : "!"}</span>
        <strong>{ok ? t.verified : block.status === "partial" ? t.partial : t.notVerified}</strong>
        {block.reference_id && <code>{block.reference_id}</code>}
      </div>
      {block.items && (
        <ul className="items">
          {block.items.map((it) => (
            <li key={it.transaction_id}>
              <span aria-hidden="true">{it.verified ? "✓" : "!"}</span> <code>{it.reference_id ?? "—"}</code> <span>{it.label}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function BlockView({ block, lang, state, active, onAction }: BlockProps) {
  const t = T[lang];
  switch (block.type) {
    case "text":
      return <p className="bubble-text">{block.text}</p>;
    case "notice":
      return <p className={`notice ${block.level === "warning" ? "warning" : "info"}`}>{block.text}</p>;
    case "error":
      return <p className="notice error" role="alert">{block.message}</p>;
    case "candidate_list":
      return <CandidateList block={block} lang={lang} active={active} onAction={onAction} />;
    case "transaction_card":
      return (
        <div className="card tx-card">
          <TxLine tx={block.transaction} />
          {state === "confirmando_movimiento" && active && (
            <div className="actions">
              <OnceButton kind="primary" label={t.yesThis} active={active} onAction={onAction}
                action={{ type: "select_candidate", transaction_id: block.transaction.transaction_id }} />
              <OnceButton label={t.notThis} active={active} onAction={onAction} action={{ type: "reject" }} />
            </div>
          )}
        </div>
      );
    case "action_confirmation":
      return (
        <div className="card confirm">
          <p className="bubble-text">{block.summary}</p>
          {block.disclaimer && <p className="muted small">{block.disclaimer}</p>}
          <div className="actions">
            <OnceButton kind="primary" label={t.confirm} active={active && state === "confirmando_accion"} onAction={onAction}
              action={{ type: "confirm", confirmation_token: block.confirmation_token }} />
            <OnceButton label={t.cancel} active={active && state === "confirmando_accion"} onAction={onAction} action={{ type: "reject" }} />
          </div>
        </div>
      );
    case "result":
      return <Result block={block} lang={lang} />;
    case "handoff_notice":
      return (
        <div className="card handoff" role="status">
          <strong>{t.handoff}</strong>
          <p className="bubble-text">{block.message}</p>
          {!block.message.includes(block.handoff_id) && <code className="small">{block.handoff_id}</code>}
        </div>
      );
    case "transaction_list":
      return (
        <div className="card list">
          <p className="muted small">{block.period.from} → {block.period.to} · {t.movements(block.count)}
            {block.totals.map((x) => <span key={x.currency}> · {t.total}: {x.total_label ?? `${x.total} ${x.currency}`}</span>)}</p>
          <ul className="rows">
            {block.transactions.map((tx) => (
              <li key={tx.transaction_id}>
                <TxLine tx={tx} />
                {block.can_dispute && (
                  <OnceButton kind="ghost" label={t.disputeThis} active={active} onAction={onAction}
                    ariaLabel={`${t.disputeThis}: ${tx.label} ${tx.amount_label}`}
                    action={{ type: "dispute_transaction", transaction_id: tx.transaction_id }} />
                )}
              </li>
            ))}
          </ul>
        </div>
      );
    case "card_list":
      return (
        <div className="card list">
          <div className="actions wrap">
            {block.cards.map((c) => (
              <OnceButton key={c.product_id} label={c.label} active={active} onAction={onAction} action={{ type: "select_card", product_id: c.product_id }} />
            ))}
          </div>
        </div>
      );
    case "case_list":
      return (
        <div className="card list">
          <ul className="rows">
            {block.cases.map((c) => (
              <li key={c.case_id}>
                <span className="tx-line">
                  <span className="tx-label">{c.transaction.label}</span>
                  <span className="tx-amount">{c.transaction.amount_label ?? c.transaction.amount}</span>
                  <span className="tx-meta"><code>{c.case_id}</code> · {t.caseStatus[c.status] ?? c.status} · {t.reason[c.reason_code] ?? c.reason_code}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      );
    case "quick_replies":
      return (
        <div className="quick" role="group">
          {block.options.map((o) => <OnceButton key={o.label} label={o.label} active={active} onAction={onAction} action={o.action} />)}
        </div>
      );
    default:
      return null;
  }
}
