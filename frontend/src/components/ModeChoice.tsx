// Elección del modo (texto o voz). La voz solo se ofrece si GET /api/voice/config dice enabled; con la voz apagada
// no aparece ningún botón ni aviso. La elección se guarda en la sesión del navegador.
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Lang, VoiceConfig } from "../api/types";
import { T } from "../lib/i18n";

export type ChatMode = "text" | "voice";
const MODE_KEY = "chat_mode";

export function storedMode(): ChatMode | null {
  try {
    const v = sessionStorage.getItem(MODE_KEY);
    return v === "text" || v === "voice" ? v : null;
  } catch {
    return null;
  }
}

export function storeMode(mode: ChatMode) {
  try {
    sessionStorage.setItem(MODE_KEY, mode);
  } catch {
    /* sin almacenamiento: solo esta pestaña */
  }
}

/** Disponibilidad de la voz: null mientras carga; ante un error se trata como no disponible. */
export function useVoiceConfig(): { config: VoiceConfig | null; reason: string | null; loading: boolean } {
  const [state, setState] = useState<{ config: VoiceConfig | null; reason: string | null; loading: boolean }>({ config: null, reason: null, loading: true });
  useEffect(() => {
    let alive = true;
    api.voiceConfig()
      .then((config) => { if (alive) setState({ config, reason: config.enabled ? null : (config.reason ?? "voice_disabled"), loading: false }); })
      .catch(() => { if (alive) setState({ config: null, reason: "error", loading: false }); });
    return () => { alive = false; };
  }, []);
  return state;
}

/** Pregunta texto/voz dentro del mensaje de bienvenida. Con la voz apagada no se muestra nada: ni botón ni aviso. */
export default function ModeChoice({ lang, mode, voiceEnabled, onChoose }: {
  lang: Lang; mode: ChatMode | null; voiceEnabled: boolean; onChoose: (m: ChatMode) => void;
}) {
  const c = T[lang].chat;
  if (!voiceEnabled) return null;
  return (
    <div className="mode-choice">
      <p className="bubble-text" id="mode-question">{c.modeQuestion}</p>
      <div className="quick" role="group" aria-labelledby="mode-question">
        <button type="button" className="chip" aria-pressed={mode === "text"} onClick={() => onChoose("text")}><span aria-hidden="true">⌨️</span> {c.modeText}</button>
        <button type="button" className="chip" aria-pressed={mode === "voice"} onClick={() => onChoose("voice")}><span aria-hidden="true">🎙️</span> {c.modeVoice}</button>
      </div>
      {mode && <p className="muted small" role="status">{mode === "voice" ? c.modeChosenVoice : c.modeChosenText}</p>}
    </div>
  );
}
