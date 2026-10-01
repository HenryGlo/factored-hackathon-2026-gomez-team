// Indicador mientras se espera un turno. No adivina por tiempo: muestra la fase REAL que publica el backend
// (GET /api/conversations/{id}/phase, docs/api-contract.md). Texto neutro por defecto; "Buscando en tus movimientos…"
// solo cuando llega searching_transactions. Si el sondeo falla, se queda el texto neutro. La fase queda en data-phase
// para que la futura mascota animada de la landing pueda reaccionar sin tocar el chat.
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { TurnPhase } from "../api/types";
import Banky, { type BankyState } from "./Banky";

const POLL_MS = 700;

/** Sondea la fase del turno mientras se espera; null = sin dato (se muestra el texto neutro). */
export function useTurnPhase(conversationId: string | null, waiting: boolean): TurnPhase | null {
  const [phase, setPhase] = useState<TurnPhase | null>(null);
  useEffect(() => {
    setPhase(null);
    if (!waiting || !conversationId) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try {
        const r = await api.phase(conversationId);
        if (alive && r.phase) setPhase(r.phase);
      } catch {
        /* el indicador es accesorio: ante cualquier error se queda el texto neutro */
      }
      if (alive) timer = setTimeout(tick, POLL_MS);
    };
    timer = setTimeout(tick, 300);
    return () => { alive = false; clearTimeout(timer); };
  }, [conversationId, waiting]);
  return phase;
}

const BANKY: Record<TurnPhase, BankyState> = { understanding: "thinking", searching_transactions: "searching", checking_policy: "checking", writing: "talking" };

export default function ThinkingIndicator({ phase, label }: { phase: TurnPhase | null; label: string }) {
  return (
    <div className="msg assistant">
      <Banky state={phase ? BANKY[phase] : "thinking"} size={44} />
      <div className="bubble assistant thinking" data-phase={phase ?? "waiting"} role="status">
        <span className="dots" aria-hidden="true"><i /><i /><i /></span>
        <span>{label}</span>
      </div>
    </div>
  );
}
