// Landing pública de BankyFicticious (banco ficticio). No consume la API: explica qué es, qué hace el asistente y qué no,
// y lleva al chat ("Tengo un reclamo") o al acceso de agentes. Si no hay sesión, /chat pasa primero por el login.
// Banky es el protagonista: saluda desde una forma orgánica; el resto acompaña en crema y verde profundo.
import { useEffect } from "react";
import { Link } from "react-router-dom";
import type { Lang } from "../api/types";
import Banky from "../components/Banky";
import ThemeToggle from "../components/ThemeToggle";
import { T } from "../lib/i18n";
import { useSession } from "../lib/session";
import { useReveal } from "../lib/useReveal";

const LANGS: { code: Lang; label: string; name: string }[] = [
  { code: "es", label: "ES", name: "Español" },
  { code: "pt", label: "PT", name: "Português" },
  { code: "en", label: "EN", name: "English" },
];

export default function LandingPage() {
  const { lang, setLang } = useSession();
  const t = T[lang].landing;
  const steps = useReveal<HTMLOListElement>();
  const scope = useReveal<HTMLDivElement>();
  const notice = useReveal<HTMLDivElement>();

  useEffect(() => {
    document.title = t.title;
  }, [t.title]);

  return (
    <div className="pv">
      <a className="skip" href="#main">{t.skip}</a>
      <header className="pv-top">
        <div className="brand"><span className="logo" aria-hidden="true">B</span><span>{T[lang].appName}</span></div>
        <div className="pv-top-right">
          <ThemeToggle />
          <div className="lang-switch" role="group" aria-label={T[lang].language}>
            {LANGS.map((l) => (
              <button key={l.code} type="button" lang={l.code} aria-pressed={lang === l.code} onClick={() => setLang(l.code)}>{l.label}<span className="sr-only"> {l.name}</span></button>
            ))}
          </div>
          <Link className="pv-agents" to="/login?perfil=agente">{t.agentsShort}</Link>
        </div>
      </header>

      <main id="main" className="pv-hero">
        <div className="pv-hero-copy">
          <h1>{t.h1}</h1>
          <p className="pv-tagline">{t.tagline}</p>
          <p className="pv-lead">{t.lead}</p>
          <div className="pv-actions">
            <Link className="btn primary large" to="/chat" aria-describedby="primary-hint">{t.primary}</Link>
            <Link className="btn secondary large" to="/login?perfil=agente">{t.secondary}</Link>
          </div>
          <p id="primary-hint" className="pv-hint">{t.primaryHint}</p>
        </div>
        <div className="pv-stage">
          <svg className="pv-blob" viewBox="0 0 400 380" aria-hidden="true"><path d="M209 18c62-9 133 23 160 82 26 57 15 131-22 183-39 55-108 86-175 80C105 357 43 316 20 254-4 190 9 110 58 62 98 23 153 26 209 18z" /></svg>
          <svg className="pv-sparks" viewBox="0 0 400 380" aria-hidden="true">
            <path d="M40 60l5 12 12 5-12 5-5 12-5-12-12-5 12-5z" /><path d="M356 300l4 10 10 4-10 4-4 10-4-10-10-4 10-4z" /><circle cx="372" cy="70" r="7" /><circle cx="28" cy="318" r="5" />
          </svg>
          <p className="pv-say">{T[lang].chat.hello}</p>
          <Banky state="greeting" size={250} label={T[lang].chat.bankyStates.greeting} />
        </div>
      </main>

      <svg className="pv-wave" viewBox="0 0 2880 90" preserveAspectRatio="none" aria-hidden="true">
        <path d="M0 45Q360 0 720 45T1440 45T2160 45T2880 45V90H0Z" />
      </svg>
      <section className="pv-section pv-band" aria-labelledby="steps-title">
        <h2 id="steps-title">{t.stepsTitle}</h2>
        <ol className="pv-steps reveal" ref={steps}>
          {t.steps.map((s, i) => (
            <li key={s.title}><span className="pv-num" aria-hidden="true">{i + 1}</span><h3>{s.title}</h3><p>{s.text}</p></li>
          ))}
        </ol>
      </section>

      <section className="pv-section" aria-labelledby="scope-title">
        <h2 id="scope-title">{t.scopeTitle}</h2>
        <div className="pv-scope reveal" ref={scope}>
          <div className="pv-can"><h3>{t.canTitle}</h3><ul>{t.can.map((x) => <li key={x}>{x}</li>)}</ul></div>
          <div className="pv-cannot"><h3>{t.cannotTitle}</h3><ul>{t.cannot.map((x) => <li key={x}>{x}</li>)}</ul></div>
        </div>
      </section>

      <section className="pv-section">
        <div className="pv-notice reveal" role="note" ref={notice}><h2>{t.noticeTitle}</h2><p>{t.notice}</p></div>
      </section>

      <footer className="pv-footer">{t.footer}</footer>
    </div>
  );
}
