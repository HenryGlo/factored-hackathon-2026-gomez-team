// Sesión del usuario (rol, nombre, idioma) y manejo de la sesión vencida.
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, ApiError, readCookie } from "../api/client";
import type { Lang, SessionInfo } from "../api/types";

interface SessionCtx {
  session: SessionInfo | null;
  loading: boolean;
  lang: Lang;
  setLang: (l: Lang) => void;
  expired: boolean;
  login: (username: string, password: string, lang: Lang) => Promise<SessionInfo>;
  logout: () => Promise<void>;
  /** Llamar cuando una petición devuelve 401: limpia la sesión y muestra el aviso en el login. */
  onUnauthorized: () => void;
}

const Ctx = createContext<SessionCtx | null>(null);

function storedLang(): Lang {
  try {
    const v = localStorage.getItem("lang");
    return v === "pt" ? "pt" : "es";
  } catch {
    return "es";
  }
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [expired, setExpired] = useState(false);
  const [lang, setLangState] = useState<Lang>(storedLang);

  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    try {
      localStorage.setItem("lang", l);
    } catch {
      /* sin almacenamiento: solo esta pestaña */
    }
    document.documentElement.lang = l === "pt" ? "pt-BR" : "es";
  }, []);

  useEffect(() => {
    // sin cookie csrf_token nunca hubo login en este navegador: no hace falta preguntar (evita un 401 en consola)
    if (!readCookie("csrf_token")) {
      setLoading(false);
      return;
    }
    api.me().then(setSession).catch(() => setSession(null)).finally(() => setLoading(false));
  }, []);

  const value = useMemo<SessionCtx>(() => ({
    session, loading, lang, setLang, expired,
    login: async (username, password, l) => {
      const s = await api.login(username, password, l);
      setExpired(false);
      setSession(s);
      return s;
    },
    logout: async () => {
      await api.logout().catch(() => undefined);
      setSession(null);
    },
    onUnauthorized: () => {
      setSession(null);
      setExpired(true);
    },
  }), [session, loading, lang, setLang, expired]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSession(): SessionCtx {
  const c = useContext(Ctx);
  if (!c) throw new Error("useSession fuera de SessionProvider");
  return c;
}

/** Mensaje y código de referencia de un error de la API, para mostrar al usuario. */
export function describeError(e: unknown, t: { genericError: string; networkError: string }): { message: string; requestId: string | null } {
  if (e instanceof ApiError) {
    if (e.status === 0) return { message: t.networkError, requestId: null };
    return { message: e.message || t.genericError, requestId: e.requestId };
  }
  return { message: t.genericError, requestId: null };
}
