// Banky, la mascota del asistente: un robot pequeño de diseño propio (cabeza de bóveda redondeada, visor menta y una
// antena con forma de moneda). El estado cambia la expresión del visor; la animación llega con los estados de fase (B2).
export type BankyState = "greeting" | "listening" | "thinking" | "searching" | "checking" | "talking" | "happy" | "worried" | "handoff" | "idle";

const MOUTH: Record<BankyState, string> = {
  greeting: "M24 41 q8 7 16 0",
  idle: "M25 42 q7 4 14 0",
  listening: "M27 42 h10",
  thinking: "M27 43 q5 -3 10 0",
  searching: "M27 42 h10",
  checking: "M27 42 h10",
  talking: "M26 40 q6 8 12 0 z",
  happy: "M23 40 q9 10 18 0",
  worried: "M25 44 q7 -5 14 0",
  handoff: "M25 42 q7 4 14 0",
};

export default function Banky({ state = "idle", size = 40, label }: { state?: BankyState; size?: number; label?: string }) {
  const worried = state === "worried";
  return (
    <svg className={`banky banky-${state}`} data-state={state} width={size} height={size} viewBox="0 0 64 64"
      role={label ? "img" : undefined} aria-label={label} aria-hidden={label ? undefined : true}>
      <line className="banky-antenna" x1="32" y1="14" x2="32" y2="8" stroke="#26325a" strokeWidth="3" strokeLinecap="round" />
      <circle className="banky-coin" cx="32" cy="6" r="4.5" fill="#3df5c8" />
      <rect x="6" y="28" width="6" height="14" rx="3" fill="#26325a" />
      <rect x="52" y="28" width="6" height="14" rx="3" fill="#26325a" />
      <rect x="10" y="13" width="44" height="42" rx="15" fill="#0d1326" stroke="#26325a" strokeWidth="2" />
      <rect className="banky-visor" x="16" y="21" width="32" height="27" rx="10" fill="#161e38" />
      <g className="banky-eyes" fill="#3df5c8">
        <ellipse cx="25" cy={worried ? 32 : 31} rx="3" ry={state === "happy" ? 1.6 : 3.6} />
        <ellipse cx="39" cy={worried ? 32 : 31} rx="3" ry={state === "happy" ? 1.6 : 3.6} />
      </g>
      {worried && <path d="M20 26 l8 2 M44 26 l-8 2" stroke="#3df5c8" strokeWidth="2" strokeLinecap="round" fill="none" />}
      <path className="banky-mouth" d={MOUTH[state]} stroke="#3df5c8" strokeWidth="2.2" strokeLinecap="round" fill={state === "talking" ? "#3df5c8" : "none"} />
    </svg>
  );
}
