// Landing pública de BankyFicticious (banco ficticio). No consume la API: explica qué es, qué hace el asistente y qué no,
// y lleva al chat ("Tengo un reclamo") o al acceso de agentes. Si no hay sesión, /chat pasa primero por el login.
import { useEffect } from "react";
import { Link } from "react-router-dom";
import type { Lang } from "../api/types";
import { T } from "../lib/i18n";
import { useSession } from "../lib/session";
import Banky from "../components/Banky";

const LANGS: { code: Lang; label: string; name: string }[] = [
  { code: "es", label: "ES", name: "Español" },
  { code: "pt", label: "PT", name: "Português" },
];

/** Conversación de ejemplo, estática: una sola imagen para lectores de pantalla (el texto está en aria-label). */
function ChatPreview({ t }: { t: (typeof T)["es"]["landing"] }) {
  return (
    <div className="preview" role="img" aria-label={t.previewLabel}>
      <p className="preview-tag">{t.previewTag}</p>
      <p className="preview-bubble customer">{t.previewCustomer}</p>
      <div className="preview-bubble assistant">
        <p>{t.previewAsk}</p>
        <div className="preview-tx">
          <span className="tx-label">{t.previewTx}</span>
          <span className="tx-amount">415,45 MXN</span>
          <span className="tx-meta">{t.previewTxMeta}</span>
        </div>
        <span className="preview-chip">{t.previewYes}</span>
      </div>
      <div className="preview-bubble assistant result">
        <span className="preview-check">✓</span>
        <span><strong>{t.previewDone}</strong> · <span className="mono">RCL-3F9A1C</span></span>
        <span className="preview-verified">{t.previewVerified}</span>
      </div>
    </div>
  );
}

export default function LandingPage() {
  const { lang, setLang } = useSession();
  const t = T[lang].landing;

  useEffect(() => {
    document.title = t.title;
  }, [t.title]);

  return (
    <div className="landing">
      <a className="skip" href="#main">{t.skip}</a>
      <div className="landing-dark on-dark">
        <header className="landing-top">
          <div className="brand">
            <span className="logo" aria-hidden="true">B</span>
            <span>{T[lang].appName}</span>
          </div>
          <div className="landing-top-right">
            <div className="lang-switch" role="group" aria-label={T[lang].language}>
              {LANGS.map((l) => (
                <button key={l.code} type="button" lang={l.code} aria-pressed={lang === l.code} onClick={() => setLang(l.code)}>{l.label}<span className="sr-only"> {l.name}</span></button>
              ))}
            </div>
            <Link className="btn ghost small landing-agents" to="/login?perfil=agente">{t.agentsShort}</Link>
          </div>
        </header>

        <main id="main" className="hero">
          <div className="hero-copy">
            <div className="hero-banky">
              <Banky state="greeting" size={84} label={T[lang].chat.bankyStates.greeting} />
              <p className="hero-say">{T[lang].chat.hello}</p>
            </div>
            <p className="eyebrow">{t.eyebrow}</p>
            <h1>{t.h1}</h1>
            <p className="hero-tagline">{t.tagline}</p>
            <p className="hero-lead">{t.lead}</p>
            <div className="hero-actions">
              <Link className="btn primary large" to="/chat" aria-describedby="primary-hint">{t.primary}</Link>
              <Link className="btn secondary large" to="/login?perfil=agente">{t.secondary}</Link>
            </div>
            <p id="primary-hint" className="hero-hint">{t.primaryHint}</p>
          </div>
          <ChatPreview t={t} />
        </main>
      </div>

      <section className="landing-section" aria-labelledby="steps-title">
        <h2 id="steps-title">{t.stepsTitle}</h2>
        <ol className="steps">
          {t.steps.map((s, i) => (
            <li key={s.title}>
              <span className="step-num" aria-hidden="true">{i + 1}</span>
              <h3>{s.title}</h3>
              <p>{s.text}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="landing-section" aria-labelledby="scope-title">
        <h2 id="scope-title">{t.scopeTitle}</h2>
        <div className="scope">
          <div className="scope-card can">
            <h3>{t.canTitle}</h3>
            <ul>{t.can.map((x) => <li key={x}>{x}</li>)}</ul>
          </div>
          <div className="scope-card cannot">
            <h3>{t.cannotTitle}</h3>
            <ul>{t.cannot.map((x) => <li key={x}>{x}</li>)}</ul>
          </div>
        </div>
      </section>

      <section className="landing-section" aria-labelledby="notice-title">
        <div className="fict-notice" role="note">
          <h2 id="notice-title">{t.noticeTitle}</h2>
          <p>{t.notice}</p>
        </div>
      </section>

      <footer className="landing-footer">{t.footer}</footer>
    </div>
  );
}
