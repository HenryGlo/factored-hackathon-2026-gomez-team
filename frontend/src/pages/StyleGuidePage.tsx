// Guía viva del sistema de diseño (/sistema): los tokens de styles/tokens.css y los botones con sus estados.
// Es una página de referencia para el equipo; no consume la API.
import Banky, { type BankyState } from "../components/Banky";
const COLORS: { group: string; dark?: boolean; items: [name: string, on: string][] }[] = [
  { group: "Superficies claras", items: [["--paper", "--text"], ["--surface", "--text"], ["--surface-2", "--text"], ["--line", "--text"], ["--line-strong", "--surface"]] },
  { group: "Superficies oscuras", dark: true, items: [["--ink-900", "--on-dark"], ["--ink-800", "--on-dark"], ["--ink-700", "--on-dark"], ["--ink-600", "--on-dark"]] },
  { group: "Acento", items: [["--accent", "--surface"], ["--accent-hover", "--surface"], ["--accent-soft", "--accent"], ["--accent-bright", "--ink-900"]] },
  { group: "Semánticos", items: [["--ok-bg", "--ok"], ["--warn-bg", "--warn"], ["--err-bg", "--err"], ["--info-bg", "--info"]] },
];
const BANKY_STATES: [BankyState, string][] = [
  ["greeting", "Saludo"], ["listening", "Escuchando (voz)"], ["thinking", "Pensando · understanding"], ["searching", "Buscando · searching_transactions"],
  ["checking", "Revisando política · checking_policy"], ["talking", "Escribiendo · writing"], ["happy", "Feliz · reclamo creado"],
  ["worried", "Empático · cargo no reconocido"], ["handoff", "Pasando a una persona"],
];
const SPACING = ["--s-1", "--s-2", "--s-3", "--s-4", "--s-5", "--s-6", "--s-7", "--s-8"];
const RADII = ["--r-sm", "--r-md", "--r-lg", "--r-xl", "--r-full"];
const SHADOWS = ["--shadow-1", "--shadow-2", "--shadow-3", "--glow"];

function Buttons() {
  return (
    <div className="sg-buttons">
      {(["primary", "secondary", "ghost"] as const).map((kind) => (
        <div key={kind} className="sg-row">
          <span className="sg-label mono">.btn.{kind}</span>
          <button type="button" className={`btn ${kind}`}>Tengo un reclamo</button>
          <button type="button" className={`btn ${kind} small`}>Pequeño</button>
          <button type="button" className={`btn ${kind}`} disabled>Deshabilitado</button>
        </div>
      ))}
    </div>
  );
}

export default function StyleGuidePage() {
  return (
    <main className="page sg" id="main">
      <h1>Sistema de diseño · BankyFicticious</h1>
      <p className="muted">Cálido y cercano: crema y verde profundo, un acento de sol para Banky, formas orgánicas y sombras de tinta.</p>

      <section aria-labelledby="sg-color">
        <h2 id="sg-color">Color</h2>
        {COLORS.map((g) => (
          <div key={g.group} className="sg-group">
            <h3>{g.group}</h3>
            <ul className="sg-swatches">
              {g.items.map(([name, on]) => (
                <li key={name} className="sg-swatch" style={{ background: `var(${name})`, color: `var(${on})` }}>
                  <span className="mono">{name}</span>
                  <span>Aa</span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </section>

      <section aria-labelledby="sg-type">
        <h2 id="sg-type">Tipografía</h2>
        <p className="sg-display">Bricolage Grotesque para títulos</p>
        <p className="sg-body">Inter para el texto: legible en tamaños pequeños, con cifras tabulares para montos como <span className="tx-amount">1.833,09 MXN</span>.</p>
        <p className="muted small">Texto secundario (--muted) · <code>código y referencias RCL-1A2B3C</code></p>
      </section>

      <section aria-labelledby="sg-buttons">
        <h2 id="sg-buttons">Botones</h2>
        <p className="muted small">Primario: la acción de la pantalla (uno por vista). Secundario: la alternativa. Fantasma: acciones menores. Prueba hover y Tab.</p>
        <div className="sg-panel"><Buttons /></div>
        <div className="sg-panel on-dark"><Buttons /></div>
      </section>

      <section aria-labelledby="sg-banky">
        <h2 id="sg-banky">Banky</h2>
        <p className="muted small">La mascota del asistente, de diseño propio. Sus estados siguen la fase real del turno y el resultado; con «reducir movimiento» quedan estáticos.</p>
        <ul className="sg-banky">
          {BANKY_STATES.map(([state, name]) => <li key={state}><Banky state={state} size={72} label={name} /><span>{name}</span></li>)}
        </ul>
      </section>

      <section aria-labelledby="sg-space">
        <h2 id="sg-space">Espaciado, radios y sombras</h2>
        <ul className="sg-scale">
          {SPACING.map((s) => <li key={s}><span className="sg-bar" style={{ width: `var(${s})` }} /><span className="mono">{s}</span></li>)}
        </ul>
        <ul className="sg-tiles">
          {RADII.map((r) => <li key={r} style={{ borderRadius: `var(${r})` }}><span className="mono">{r}</span></li>)}
        </ul>
        <ul className="sg-tiles on-dark sg-dark-tiles">
          {SHADOWS.map((s) => <li key={s} style={{ boxShadow: `var(${s})` }}><span className="mono">{s}</span></li>)}
        </ul>
      </section>

      <section aria-labelledby="sg-motion">
        <h2 id="sg-motion">Movimiento</h2>
        <p className="muted small">120 ms (hover y foco), 200 ms (cambios de estado), 360 ms (entradas). Curva de salida suave. Con «reducir movimiento» las duraciones son 0.</p>
        <ul className="sg-motion">
          {["--dur-fast", "--dur-base", "--dur-slow"].map((d) => <li key={d} tabIndex={0} style={{ transitionDuration: `var(${d})` }}><span className="mono">{d}</span></li>)}
        </ul>
      </section>
    </main>
  );
}
