import { useRef, useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { useDemoInfo } from "../lib/demo";
import { T } from "../lib/i18n";
import { describeError, homeFor, useSession } from "../lib/session";
import Banky from "../components/Banky";
import ErrorNote from "../components/ErrorNote";

export default function LoginPage() {
  const { session, lang, setLang, login, expired } = useSession();
  const t = T[lang];
  const navigate = useNavigate();
  const agent = useSearchParams()[0].get("perfil") === "agente";
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const passwordRef = useRef<HTMLInputElement>(null);
  const demo = useDemoInfo();
  const demoUsers = demo?.demo_mode ? demo.users.filter((u) => (u.role !== "customer") === agent) : [];
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ message: string; requestId: string | null } | null>(null);

  if (session) return <Navigate to={homeFor(session.role)} replace />;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const s = await login(username.trim(), password, lang);
      navigate(homeFor(s.role));
    } catch (err) {
      if (err instanceof ApiError && err.status === 429 && err.retryAfter) setError({ message: t.rateLimited(err.retryAfter), requestId: err.requestId });
      else setError(describeError(err, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <aside className="login-aside on-dark">
        <Link className="brand big" to="/">
          <span className="logo" aria-hidden="true">B</span>
          <span>{t.appName}</span>
        </Link>
        <Banky state="greeting" size={120} />
        <p className="login-aside-text">{agent ? t.loginAsideAgent : t.loginAside}</p>
        {demo?.demo_mode && <p className="demo-note" role="note">{demo.notice[lang]}</p>}
      </aside>
      <main className="login-card" id="main">
        <Link className="back" to="/">← {t.backHome}</Link>
        <h1>{agent ? t.agentLogin : t.customerLogin}</h1>
        {expired && <p className="notice warning" role="alert">{t.sessionExpired}</p>}
        <form onSubmit={submit} className="form" aria-label={t.login}>
          <label>
            {t.username}
            <input autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required maxLength={60} />
          </label>
          <label>
            {t.password}
            <input ref={passwordRef} type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required maxLength={200} />
          </label>
          <div className="row">
            <label className="inline">
              {t.language}
              <select value={lang} onChange={(e) => setLang(e.target.value as "es" | "pt")}>
                <option value="es">Español</option>
                <option value="pt">Português</option>
              </select>
            </label>
            <button className="btn primary" type="submit" disabled={busy}>{busy ? t.signingIn : t.signIn}</button>
          </div>
          {error && <ErrorNote message={error.message} requestId={error.requestId} label={t.reference} />}
        </form>
        {demo?.demo_mode && demoUsers.length > 0 && (
          <section aria-labelledby="demo-users" className="demo-users">
            <h2 id="demo-users">{t.demoUsers}</h2>
            <p className="muted small">{t.demoPick} {demo.password_hint[lang]}</p>
            <ul>
              {demoUsers.map((u) => (
                <li key={u.username}>
                  <button type="button" className="demo-user" onClick={() => { setUsername(u.username); passwordRef.current?.focus(); }} aria-pressed={username === u.username}>
                    <span className="demo-scenario">{u.description[lang]}</span>
                    <span className="muted small"><span className="mono">{u.username}</span>{u.display_name && <> · {u.display_name}</>}</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}
      </main>
    </div>
  );
}
