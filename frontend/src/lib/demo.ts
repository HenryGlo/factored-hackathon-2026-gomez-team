// Modo demostración: GET /api/demo/info (público). Con DEMO_MODE apagado, o si la consulta falla, no hay aviso ni tarjetas.
// La contraseña nunca llega al frontend: `password_hint` solo dice dónde está documentada.
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { DemoInfo } from "../api/types";

let cached: Promise<DemoInfo> | null = null;

export function loadDemoInfo(): Promise<DemoInfo> {
  cached ??= api.demoInfo().catch((): DemoInfo => ({ demo_mode: false }));
  return cached;
}

/** Solo para tests: olvida la respuesta guardada. */
export function resetDemoInfo() {
  cached = null;
}

export function useDemoInfo(): DemoInfo | null {
  const [info, setInfo] = useState<DemoInfo | null>(null);
  useEffect(() => {
    let alive = true;
    void loadDemoInfo().then((d) => { if (alive) setInfo(d); });
    return () => { alive = false; };
  }, []);
  return info;
}
