// Banky, la mascota del asistente. Diseño propio: cabeza de bóveda redondeada, visor oscuro con ojos menta, una antena con
// forma de moneda y dos brazos cortos. Es un SVG animado con CSS (styles.css, sección "Banky").
// - El estado lo decide quien lo usa a partir de datos REALES: la fase del turno (GET …/phase) o los bloques de la respuesta.
//   Aquí no hay temporizadores.
// - Con prefers-reduced-motion cada estado queda estático (misma pose, sin animación).
// - Con `label` es una imagen con nombre accesible (el estado en palabras); sin `label` es decorativo y se oculta.
import type { TurnPhase } from "../api/types";

export type BankyState = "greeting" | "listening" | "thinking" | "searching" | "checking" | "talking" | "happy" | "worried" | "handoff" | "idle";

/** Fase real del turno → estado de Banky. Sin dato de fase (null) se queda pensando: nunca adivina por tiempo. */
export const PHASE_STATE: Record<TurnPhase, BankyState> = {
  understanding: "thinking",
  searching_transactions: "searching",
  checking_policy: "checking",
  writing: "talking",
};

export function stateForPhase(phase: TurnPhase | null): BankyState {
  return phase ? PHASE_STATE[phase] : "thinking";
}

const MOUTH: Record<BankyState, string> = {
  greeting: "M25 43 q7 7 14 0",
  idle: "M26 44 q6 4 12 0",
  listening: "M28 44 h8",
  thinking: "M28 45 q4 -3 8 0",
  searching: "M28 44 h8",
  checking: "M28 44 q4 2 8 0",
  talking: "M27 42 q5 7 10 0 z",
  happy: "M24 42 q8 9 16 0",
  worried: "M26 46 q6 -5 12 0",
  handoff: "M26 44 q6 4 12 0",
};

// Colores por variable CSS: cada tema puede vestir a Banky sin tocar el dibujo.
const INK = "var(--banky-ink, #0d1326)";
const EDGE = "var(--banky-edge, #26325a)";
const VISOR = "var(--banky-visor, #161e38)";
const MINT = "var(--banky-glow, #3df5c8)";

export default function Banky({ state = "idle", size = 40, label }: { state?: BankyState; size?: number; label?: string }) {
  const squint = state === "happy";
  const eyeY = state === "thinking" ? 31 : state === "worried" ? 34 : 33;
  return (
    <svg className={`banky banky-${state}`} data-state={state} width={size} height={size} viewBox="0 0 64 68"
      role={label ? "img" : undefined} aria-label={label} aria-hidden={label ? undefined : true} focusable="false">
      <g className="banky-all">
        {/* antena con moneda */}
        <line x1="32" y1="16" x2="32" y2="9" stroke={EDGE} strokeWidth="3" strokeLinecap="round" />
        <circle className="banky-coin" cx="32" cy="7" r="4.5" fill={MINT} />
        {/* brazos */}
        <path className="banky-arm-l" d="M11 46 q-6 3 -5 10" stroke={EDGE} strokeWidth="4" strokeLinecap="round" fill="none" />
        <path className="banky-arm-r" d={state === "greeting" ? "M54 47 q8 -3 7 -15" : state === "handoff" ? "M54 46 q6 -1 9 -6" : "M53 46 q6 3 5 10"}
          stroke={EDGE} strokeWidth="4" strokeLinecap="round" fill="none" />
        {/* cabeza y orejas */}
        <rect x="5" y="30" width="6" height="13" rx="3" fill={EDGE} />
        <rect x="53" y="30" width="6" height="13" rx="3" fill={EDGE} />
        <rect x="10" y="15" width="44" height="42" rx="15" fill={INK} stroke={EDGE} strokeWidth="2" />
        <rect x="16" y="23" width="32" height="27" rx="10" fill={VISOR} />
        {/* base */}
        <rect x="22" y="58" width="20" height="6" rx="3" fill={EDGE} />
        {/* cara */}
        <g className="banky-eyes" fill={MINT}>
          <ellipse cx="25" cy={eyeY} rx="3" ry={squint ? 1.5 : 3.6} />
          <ellipse cx="39" cy={eyeY} rx="3" ry={squint ? 1.5 : 3.6} />
        </g>
        {state === "worried" && <path d="M20 30 l8 -2.5 M44 30 l-8 -2.5" stroke={MINT} strokeWidth="2" strokeLinecap="round" fill="none" />}
        <path className="banky-mouth" d={MOUTH[state]} stroke={MINT} strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" fill={state === "talking" ? MINT : "none"} />
        {/* accesorio de cada estado */}
        {state === "listening" && (
          <g className="banky-waves" stroke={MINT} strokeWidth="2" strokeLinecap="round" fill="none">
            <path d="M3 31 q-3 5.5 0 11" /><path d="M61 31 q3 5.5 0 11" />
          </g>
        )}
        {state === "thinking" && (
          <g className="banky-dots" fill={MINT}><circle cx="46" cy="9" r="2" /><circle cx="53" cy="6" r="2.4" /><circle cx="60" cy="4" r="2.8" /></g>
        )}
        {state === "searching" && (
          <g className="banky-lens" stroke={MINT} strokeWidth="2.4" strokeLinecap="round" fill="none"><circle cx="25" cy="33" r="6.5" /><path d="M30 38 l5 5" /></g>
        )}
        {state === "checking" && (
          <g className="banky-doc">
            <rect x="44" y="40" width="17" height="21" rx="3" fill="#eef2ff" stroke={EDGE} strokeWidth="1.5" />
            <path className="banky-doc-lines" d="M48 46 h9 M48 50.5 h9 M48 55 h6" stroke={EDGE} strokeWidth="1.8" strokeLinecap="round" />
          </g>
        )}
        {state === "happy" && (
          <g className="banky-sparks" fill={MINT}><path d="M6 12 l1.6 3.4 3.4 1.6 -3.4 1.6 -1.6 3.4 -1.6 -3.4 -3.4 -1.6 3.4 -1.6z" /><path d="M56 16 l1.2 2.6 2.6 1.2 -2.6 1.2 -1.2 2.6 -1.2 -2.6 -2.6 -1.2 2.6 -1.2z" /></g>
        )}
        {state === "handoff" && (
          <g className="banky-person">
            <circle cx="55" cy="13" r="8.5" fill="#eef2ff" stroke={EDGE} strokeWidth="1.5" />
            <circle cx="55" cy="10.5" r="2.6" fill={EDGE} /><path d="M50 18 q5 -6 10 0" fill={EDGE} />
          </g>
        )}
      </g>
    </svg>
  );
}
