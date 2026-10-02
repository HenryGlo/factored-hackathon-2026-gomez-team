// Landing en tres direcciones visuales para elegir (/preview/a, /b, /c). Mismo contenido y mismas acciones que la landing
// actual; cambia la composición: A hero oscuro con vidrio, B bloques tipo bento, C Banky protagonista sobre formas orgánicas.
import { useEffect } from "react";
import { Link } from "react-router-dom";
import type { Lang } from "../../api/types";
import Banky from "../../components/Banky";
import { T } from "../../lib/i18n";
import { useSession } from "../../lib/session";
import { ChatPreview } from "../LandingPage";
import ThemeScope, { THEMES, useTheme, type Theme } from "./ThemeScope";

type Copy = (typeof T)["es"]["landing"];

function Top({ theme, lang, setLang }: { theme: Theme; lang: Lang; setLang: (l: Lang) => void }) {
  const t = T[lang].landing;
  return (
    <header className="pv-top">
      <Link className="brand" to={`/preview/${theme}`}><span className="logo" aria-hidden="true">B</span><span>{T[lang].appName}</span></Link>
      <nav className="pv-switch" aria-label="Direcciones visuales">
        {THEMES.map((x) => <Link key={x.id} to={`/preview/${x.id}`} aria-current={x.id === theme ? "page" : undefined}>{x.id.toUpperCase()}<span className="sr-only"> {x.name}</span></Link>)}
      </nav>
      <div className="pv-top-right">
        <div className="lang-switch" role="group" aria-label={T[lang].language}>
          {(["es", "pt"] as const).map((l) => <button key={l} type="button" lang={l} aria-pressed={lang === l} onClick={() => setLang(l)}>{l.toUpperCase()}</button>)}
        </div>
        <Link className="pv-agents" to="/login?perfil=agente">{t.agentsShort}</Link>
      </div>
    </header>
  );
}

function Actions({ theme, t }: { theme: Theme; t: Copy }) {
  return (
    <>
      <div className="pv-actions">
        <Link className="btn primary large" to={`/preview/${theme}/chat`} aria-describedby="pv-hint">{t.primary}</Link>
        <Link className="btn secondary large" to="/login?perfil=agente">{t.secondary}</Link>
      </div>
      <p id="pv-hint" className="pv-hint">{t.primaryHint}</p>
    </>
  );
}

function Steps({ t }: { t: Copy }) {
  return (
    <ol className="pv-steps">
      {t.steps.map((s, i) => (
        <li key={s.title}><span className="pv-num" aria-hidden="true">{i + 1}</span><h3>{s.title}</h3><p>{s.text}</p></li>
      ))}
    </ol>
  );
}

function Scope({ t }: { t: Copy }) {
  return (
    <>
      <div className="pv-can"><h3>{t.canTitle}</h3><ul>{t.can.map((x) => <li key={x}>{x}</li>)}</ul></div>
      <div className="pv-cannot"><h3>{t.cannotTitle}</h3><ul>{t.cannot.map((x) => <li key={x}>{x}</li>)}</ul></div>
    </>
  );
}

function Notice({ t }: { t: Copy }) {
  return <div className="pv-notice" role="note"><h2>{t.noticeTitle}</h2><p>{t.notice}</p></div>;
}

/** A · Fintech oscuro: titular grande a la izquierda y la conversación de ejemplo en vidrio esmerilado. */
function LayoutA({ theme, t }: { theme: Theme; t: Copy }) {
  return (
    <>
      <main id="main" className="pv-hero">
        <div className="pv-hero-copy">
          <h1>{t.h1}</h1>
          <p className="pv-tagline">{t.tagline}</p>
          <p className="pv-lead">{t.lead}</p>
          <Actions theme={theme} t={t} />
        </div>
        <ChatPreview t={t} />
      </main>
      <section className="pv-section" aria-labelledby="pv-steps"><h2 id="pv-steps">{t.stepsTitle}</h2><Steps t={t} /></section>
      <section className="pv-section" aria-labelledby="pv-scope"><h2 id="pv-scope">{t.scopeTitle}</h2><div className="pv-scope"><Scope t={t} /></div></section>
      <section className="pv-section"><Notice t={t} /></section>
    </>
  );
}

/** B · Claro premium: todo el contenido en una rejilla de bloques (bento); el titular y la conversación son los bloques grandes. */
function LayoutB({ theme, t, lang }: { theme: Theme; t: Copy; lang: Lang }) {
  return (
    <main id="main" className="pv-bento">
      <section className="pv-tile pv-tile-hero">
        <Banky state="greeting" size={64} label={T[lang].chat.bankyStates.greeting} />
        <h1>{t.h1}</h1>
        <p className="pv-lead">{t.lead}</p>
        <Actions theme={theme} t={t} />
      </section>
      <section className="pv-tile pv-tile-chat" aria-label={t.previewTag}><ChatPreview t={t} /></section>
      <section className="pv-tile pv-tile-steps" aria-labelledby="pv-steps"><h2 id="pv-steps">{t.stepsTitle}</h2><Steps t={t} /></section>
      <section className="pv-tile pv-tile-can" aria-labelledby="pv-scope"><h2 id="pv-scope" className="sr-only">{t.scopeTitle}</h2><Scope t={t} /></section>
      <section className="pv-tile pv-tile-notice"><Notice t={t} /></section>
    </main>
  );
}

/** C · Cálido y cercano: Banky grande sobre una forma orgánica, saludando; el resto acompaña en tonos crema y verde. */
function LayoutC({ theme, t, lang }: { theme: Theme; t: Copy; lang: Lang }) {
  return (
    <>
      <main id="main" className="pv-hero">
        <div className="pv-hero-copy">
          <h1>{t.h1}</h1>
          <p className="pv-tagline">{t.tagline}</p>
          <p className="pv-lead">{t.lead}</p>
          <Actions theme={theme} t={t} />
        </div>
        <div className="pv-stage">
          <svg className="pv-blob" viewBox="0 0 400 380" aria-hidden="true"><path d="M209 18c62-9 133 23 160 82 26 57 15 131-22 183-39 55-108 86-175 80C105 357 43 316 20 254-4 190 9 110 58 62 98 23 153 26 209 18z" /></svg>
          <p className="pv-say">{T[lang].chat.hello}</p>
          <Banky state="greeting" size={250} label={T[lang].chat.bankyStates.greeting} />
        </div>
      </main>
      <svg className="pv-wave" viewBox="0 0 1440 90" preserveAspectRatio="none" aria-hidden="true"><path d="M0 40c180 50 360 50 540 18s360-52 540-22 240 44 360 34v20H0z" /></svg>
      <section className="pv-section pv-band" aria-labelledby="pv-steps"><h2 id="pv-steps">{t.stepsTitle}</h2><Steps t={t} /></section>
      <section className="pv-section" aria-labelledby="pv-scope"><h2 id="pv-scope">{t.scopeTitle}</h2><div className="pv-scope"><Scope t={t} /></div></section>
      <section className="pv-section"><Notice t={t} /></section>
    </>
  );
}

function Page() {
  const theme = useTheme();
  const { lang, setLang } = useSession();
  const t = T[lang].landing;
  useEffect(() => { document.title = `${t.title} · ${theme.toUpperCase()}`; }, [t.title, theme]);
  return (
    <div className={`pv pv-${theme}`}>
      <a className="skip" href="#main">{t.skip}</a>
      <Top theme={theme} lang={lang} setLang={setLang} />
      {theme === "a" ? <LayoutA theme={theme} t={t} /> : theme === "b" ? <LayoutB theme={theme} t={t} lang={lang} /> : <LayoutC theme={theme} t={t} lang={lang} />}
      <footer className="pv-footer">{t.footer}</footer>
    </div>
  );
}

export default function PreviewLanding() {
  return <ThemeScope><Page /></ThemeScope>;
}
