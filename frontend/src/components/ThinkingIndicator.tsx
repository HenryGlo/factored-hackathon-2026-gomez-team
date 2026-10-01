// Indicador mientras se espera un turno. Expone la fase en data-phase ("thinking" → "searching" → "still") para que la
// futura mascota animada de la landing pueda reaccionar sin tocar el chat.
import { useEffect, useState } from "react";

export type Phase = "thinking" | "searching" | "still";

/** Fase según el tiempo de espera: pensando (0–1,5 s), buscando (hasta 8 s), sigue trabajando (después). */
export function usePhase(waiting: boolean): Phase {
  const [phase, setPhase] = useState<Phase>("thinking");
  useEffect(() => {
    if (!waiting) return;
    setPhase("thinking");
    const a = setTimeout(() => setPhase("searching"), 1500);
    const b = setTimeout(() => setPhase("still"), 8000);
    return () => { clearTimeout(a); clearTimeout(b); };
  }, [waiting]);
  return phase;
}

export default function ThinkingIndicator({ phase, label }: { phase: Phase; label: string }) {
  return (
    <div className="msg assistant">
      <div className="bubble assistant thinking" data-phase={phase} role="status">
        <span className="dots" aria-hidden="true"><i /><i /><i /></span>
        <span>{label}</span>
      </div>
    </div>
  );
}
