import { Navigate, NavLink, Route, Routes, useNavigate } from "react-router-dom";
import Icon, { type IconName } from "./components/Icon";
import { Loading } from "./components/States";
import { useDemoInfo } from "./lib/demo";
import { T } from "./lib/i18n";
import { homeFor, useSession } from "./lib/session";
import type { Role } from "./api/types";
import LandingPage from "./pages/LandingPage";
import LoginPage from "./pages/LoginPage";
import ChatPage from "./pages/ChatPage";
import MovementsPage from "./pages/MovementsPage";
import CasesPage from "./pages/CasesPage";
import ConversationsPage from "./pages/ConversationsPage";
import ConversationPage from "./pages/ConversationPage";
import AdminPage from "./pages/AdminPage";
import TicketsPage from "./pages/TicketsPage";
import TicketPage from "./pages/TicketPage";
import TracePage from "./pages/TracePage";
import StyleGuidePage from "./pages/StyleGuidePage";

function Shell({ children }: { children: React.ReactNode }) {
  const { session, lang, setLang, logout } = useSession();
  const t = T[lang];
  const navigate = useNavigate();
  const demo = useDemoInfo();
  const links: { to: string; label: string; icon: IconName }[] = session && session.role !== "customer"
    ? [...(session.role === "admin" ? [{ to: "/admin", label: t.admin.nav, icon: "gauge" as const }] : []), { to: "/agentes", label: t.agent.nav, icon: "ticket" as const }]
    : [{ to: "/chat", label: t.navChat, icon: "chat" }, { to: "/conversaciones", label: t.history.navShort, icon: "history" },
       { to: "/movimientos", label: t.navMovementsShort, icon: "list" }, { to: "/reclamos", label: t.navCasesShort, icon: "flag" }];
  return (
    <div className="shell">
      <a className="skip" href="#main">{t.landing.skip}</a>
      <header className="topbar">
        <div className="brand" aria-label={t.appName}>
          <span className="logo" aria-hidden="true">B</span>
          <span>{t.appName}</span>
        </div>
        <nav className="main-nav" aria-label={t.navMain}>
          {links.map((l) => (
            <NavLink key={l.to} to={l.to} className={({ isActive }) => (isActive ? "nav active" : "nav")}><Icon name={l.icon} /><span>{l.label}</span></NavLink>
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
      {demo?.demo_mode && <div className="demo-strip" role="note">{demo.notice[lang]}</div>}
      <main id="main" tabIndex={-1}>{children}</main>
    </div>
  );
}

const STAFF: Role[] = ["analyst", "admin"];

function RequireRole({ roles, children }: { roles: Role[]; children: React.ReactNode }) {
  const { session, loading, lang } = useSession();
  if (loading) return <div className="page"><Loading label={T[lang].loading} /></div>;
  if (!session) return <Navigate to={roles.includes("customer") ? "/login" : "/login?perfil=agente"} replace />;
  if (!roles.includes(session.role)) return <Navigate to={homeFor(session.role)} replace />;
  return <Shell>{children}</Shell>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/chat" element={<RequireRole roles={["customer"]}><ChatPage /></RequireRole>} />
      <Route path="/conversaciones" element={<RequireRole roles={["customer"]}><ConversationsPage /></RequireRole>} />
      <Route path="/conversaciones/:id" element={<RequireRole roles={["customer"]}><ConversationPage /></RequireRole>} />
      <Route path="/movimientos" element={<RequireRole roles={["customer"]}><MovementsPage /></RequireRole>} />
      <Route path="/reclamos" element={<RequireRole roles={["customer"]}><CasesPage /></RequireRole>} />
      <Route path="/admin" element={<RequireRole roles={["admin"]}><AdminPage /></RequireRole>} />
      <Route path="/agentes" element={<RequireRole roles={STAFF}><TicketsPage /></RequireRole>} />
      <Route path="/agentes/tickets/:id" element={<RequireRole roles={STAFF}><TicketPage /></RequireRole>} />
      <Route path="/agentes/trazas/:turnId" element={<RequireRole roles={STAFF}><TracePage /></RequireRole>} />
      <Route path="/consola/*" element={<Navigate to="/agentes" replace />} />
      <Route path="/sistema" element={<StyleGuidePage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
