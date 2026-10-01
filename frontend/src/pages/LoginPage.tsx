import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { DEMO_USERS, T } from "../lib/i18n";
import { describeError, useSession } from "../lib/session";
import ErrorNote from "../components/ErrorNote";

export default function LoginPage() {
  const { session, lang, setLang, login, expired } = useSession();
  const t = T[lang];
  const navigate = useNavigate();
  const agent = useSearchParams()[0].get("perfil") === "agente";
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ message: string; requestId: string | null } | null>(null);

  if (session) return <Navigate to={session.role === "analyst" ? "/consola" : "/chat"} replace />;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const s = await login(username.trim(), password, lang);
      navigate(s.role === "analyst" ? "/consola" : "/chat");
    } catch (err) {
      if (err instanceof ApiError && err.status === 429 && err.retryAfter) setError({ message: t.rateLimited(err.retryAfter), requestId: err.requestId });
      else setError(describeError(err, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <div className="login-card">
        <Link className="back" to="/">← {t.backHome}</Link>
        <div className="brand big">
          <span className="logo" aria-hidden="true">B</span>
          <span>{t.appName}</span>
        </div>
        <h1>{agent ? t.agentLogin : t.customerLogin}</h1>
        <p className="demo-note" role="note">{t.demoBanner}</p>
        {expired && <p className="notice warning" role="alert">{t.sessionExpired}</p>}
        <form onSubmit={submit} className="form" aria-label={t.login}>
          <label>
            {t.username}
            <input autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required maxLength={60} />
          </label>
          <label>
            {t.password}
            <input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required maxLength={200} />
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
        <section aria-labelledby="demo-users" className="demo-users">
          <h2 id="demo-users">{t.demoUsers}</h2>
          <p className="muted small">{t.demoUsersHint}</p>
          <ul>
            {DEMO_USERS.filter((u) => (u.role === "analyst") === agent).map((u) => (
              <li key={u.username}>
                <button type="button" className="demo-user" onClick={() => setUsername(u.username)} aria-pressed={username === u.username}>
                  <span className="mono">{u.username}</span>
                  <span className="muted small">{u.scenario[lang]}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}
