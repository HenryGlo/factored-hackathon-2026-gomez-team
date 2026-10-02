import { Navigate, NavLink, Route, Routes, useNavigate } from "react-router-dom";
import { T } from "./lib/i18n";
import { useSession } from "./lib/session";
import LandingPage from "./pages/LandingPage";
import LoginPage from "./pages/LoginPage";
import ChatPage from "./pages/ChatPage";
import MovementsPage from "./pages/MovementsPage";
import CasesPage from "./pages/CasesPage";
import ConversationsPage from "./pages/ConversationsPage";
import ConversationPage from "./pages/ConversationPage";
import InboxPage from "./pages/InboxPage";
import HandoffPage from "./pages/HandoffPage";
import TracePage from "./pages/TracePage";
import StyleGuidePage from "./pages/StyleGuidePage";

function Shell({ children }: { children: React.ReactNode }) {
  const { session, lang, setLang, logout } = useSession();
  const t = T[lang];
  const navigate = useNavigate();
  const links = session?.role === "analyst"
    ? [{ to: "/consola", label: t.navInbox }]
    : [{ to: "/chat", label: t.navChat }, { to: "/conversaciones", label: t.history.nav }, { to: "/movimientos", label: t.navMovements }, { to: "/reclamos", label: t.navCases }];
  return (
    <div className="shell">
      <a className="skip" href="#main">{t.landing.skip}</a>
      <header className="topbar">
        <div className="brand" aria-label={t.appName}>
          <span className="logo" aria-hidden="true">B</span>
          <span>{t.appName}</span>
        </div>
        <nav aria-label="Principal">
          {links.map((l) => (
            <NavLink key={l.to} to={l.to} className={({ isActive }) => (isActive ? "nav active" : "nav")}>{l.label}</NavLink>
          ))}
        </nav>
        <div className="topbar-right">
          <select aria-label={t.language} value={lang} onChange={(e) => setLang(e.target.value as "es" | "pt")}>
            <option value="es">ES</option>
            <option value="pt">PT</option>
          </select>
          <span className="who" title={session?.display_name}>{session?.display_name}</span>
          <button className="btn ghost" onClick={async () => { await logout(); navigate("/login"); }}>{t.logout}</button>
        </div>
      </header>
      <div className="demo-strip" role="note">{t.demoBanner}</div>
      <main id="main" tabIndex={-1}>{children}</main>
    </div>
  );
}

function RequireRole({ role, children }: { role: "customer" | "analyst"; children: React.ReactNode }) {
  const { session, loading, lang } = useSession();
  if (loading) return <p className="center muted" role="status">{T[lang].loading}</p>;
  if (!session) return <Navigate to="/login" replace />;
  if (session.role !== role) return <Navigate to={session.role === "analyst" ? "/consola" : "/chat"} replace />;
  return <Shell>{children}</Shell>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/chat" element={<RequireRole role="customer"><ChatPage /></RequireRole>} />
      <Route path="/conversaciones" element={<RequireRole role="customer"><ConversationsPage /></RequireRole>} />
      <Route path="/conversaciones/:id" element={<RequireRole role="customer"><ConversationPage /></RequireRole>} />
      <Route path="/movimientos" element={<RequireRole role="customer"><MovementsPage /></RequireRole>} />
      <Route path="/reclamos" element={<RequireRole role="customer"><CasesPage /></RequireRole>} />
      <Route path="/consola" element={<RequireRole role="analyst"><InboxPage /></RequireRole>} />
      <Route path="/consola/handoffs/:id" element={<RequireRole role="analyst"><HandoffPage /></RequireRole>} />
      <Route path="/consola/trazas/:turnId" element={<RequireRole role="analyst"><TracePage /></RequireRole>} />
      <Route path="/sistema" element={<StyleGuidePage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
