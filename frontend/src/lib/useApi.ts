// Carga de datos para las pantallas de lectura: estado de carga, error con código de referencia y sesión vencida (401 → login).
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { T } from "./i18n";
import { describeError, useSession } from "./session";

export interface ApiState<D> {
  data: D | null;
  loading: boolean;
  error: { message: string; requestId: string | null; status?: number } | null;
  reload: () => void;
  setData: (d: D) => void;
}

export function useApi<D>(fetcher: () => Promise<D>, deps: unknown[]): ApiState<D> {
  const { lang, onUnauthorized } = useSession();
  const navigate = useNavigate();
  const [data, setData] = useState<D | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiState<D>["error"]>(null);
  const [tick, setTick] = useState(0);
  const latest = useRef(fetcher);
  latest.current = fetcher;

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    latest.current()
      .then((d) => { if (alive) setData(d); })
      .catch((e) => {
        if (!alive) return;
        if (e instanceof ApiError && e.status === 401) { onUnauthorized(); navigate("/login"); return; }
        setError({ ...describeError(e, T[lang]), status: e instanceof ApiError ? e.status : undefined });
      })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [tick, lang, ...deps]); // eslint-disable-line react-hooks/exhaustive-deps

  const reload = useCallback(() => setTick((n) => n + 1), []);
  return { data, loading, error, reload, setData };
}
