// Modo voz manos libres (opción A del líder): pantalla completa con una bola que muestra el estado real
// (escuchando, pensando con la fase del turno, hablando), la última transcripción y la última respuesta en grande.
// - VAD en el navegador (Silero en WASM, archivos servidos por la app en /vad/): al terminar cada frase se transcribe
//   (POST /api/voice/stt) y se envía como turno normal con via: "voice", sin pasos manuales.
// - Después de cada turno el asistente habla solo (POST /api/voice/tts); si el cliente habla encima, se corta (barge-in).
// - Sin selección manual: el backend entiende "la segunda", "el de Netflix", "ver mis movimientos"… La única excepción
//   es confirmar una acción: botón Confirmar grande (R4, la voz no confirma).
// - Cualquier fallo de micrófono, STT o TTS cierra el modo y el chat sigue por escrito con un aviso.
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type { Action, Block, ConversationState, Lang, TurnPhase } from "../api/types";
import { T } from "../lib/i18n";
import Banky, { stateForPhase, type BankyState } from "./Banky";

type Stage = "starting" | "listening" | "hearing" | "transcribing" | "thinking" | "speaking";

export interface VoiceTurn { id: string; conversationId: string; blocks: Block[] }

/** Texto de un turno del asistente para mostrarlo en grande (lo mismo que se lee en voz alta, sin las opciones). */
export function turnText(blocks: Block[]): string {
  const parts: string[] = [];
  for (const b of blocks) {
    if (b.type === "text" || b.type === "notice") parts.push(b.text);
    else if (b.type === "candidate_list") parts.push(b.prompt);
    else if (b.type === "handoff_notice") parts.push(b.message);
    else if (b.type === "action_confirmation") parts.push(b.summary);
    else if (b.type === "error") parts.push(b.message);
  }
  return parts.filter(Boolean).join(" ");
}

/** Opciones que el cliente puede decir (no se tocan): candidatas, movimientos de una lista o respuestas rápidas. */
function sayable(blocks: Block[]): string[] {
  for (const b of blocks) {
    if (b.type === "candidate_list") return b.candidates.map((c) => `${c.label} · ${c.amount_label} · ${c.date_label}`);
    if (b.type === "transaction_list") return b.transactions.slice(0, 5).map((tx) => `${tx.label} · ${tx.amount_label} · ${tx.date_label}`);
  }
  for (const b of blocks) if (b.type === "quick_replies") return b.options.map((o) => o.label);
  return [];
}

export default function VoiceMode({ lang, audioContext, maxAudioBytes, lastHeard, lastTurn, state, sending, phase, onSend, onAction, onExit }: {
  lang: Lang;
  /** creado y reanudado en el toque que abrió el modo: así el navegador deja reproducir el audio */
  audioContext: AudioContext;
  maxAudioBytes: number;
  lastHeard: string | null;
  lastTurn: VoiceTurn | null;
  state: ConversationState;
  sending: boolean;
  phase: TurnPhase | null;
  onSend: (text: string) => Promise<void>;
  onAction: (action: Action, label: string) => void;
  onExit: (notice?: string) => void;
}) {
  const v = T[lang].voiceMode;
  const [stage, setStage] = useState<Stage>("starting");
  const stageRef = useRef<Stage>("starting");
  const setStageBoth = useCallback((s: Stage) => { stageRef.current = s; setStage(s); }, []);
  const vadRef = useRef<{ start: () => Promise<void>; pause: () => Promise<void>; destroy: () => Promise<void> } | null>(null);
  const sourceRef = useRef<AudioBufferSourceNode | null>(null);
  const spokenRef = useRef<string | null>(lastTurn?.id ?? null);      // el turno que ya estaba en pantalla no se lee
  const exitRef = useRef(onExit);
  exitRef.current = onExit;
  const sendRef = useRef(onSend);
  sendRef.current = onSend;
  const busyRef = useRef(sending);
  busyRef.current = sending;
  const confirmRef = useRef<HTMLButtonElement>(null);

  const stopAudio = useCallback(() => {
    try { sourceRef.current?.stop(); } catch { /* ya terminó */ }
    sourceRef.current = null;
  }, []);

  const fail = useCallback((notice: string) => {
    stopAudio();
    void vadRef.current?.destroy();
    vadRef.current = null;
    exitRef.current(notice);
  }, [stopAudio]);

  // VAD: se carga solo al abrir el modo (no pesa en el resto de la app)
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { MicVAD, utils } = await import("@ricky0123/vad-web");
        const vad = await MicVAD.new({
          model: "v5",
          baseAssetPath: "/vad/",
          onnxWASMBasePath: "/vad/",
          audioContext,
          ortConfig: (ort) => { ort.env.wasm.numThreads = 1; },          // sin SharedArrayBuffer (no hace falta aislamiento)
          redemptionMs: 700,
          minSpeechMs: 300,
          onSpeechStart: () => {
            if (stageRef.current === "speaking") stopAudio();               // barge-in: el cliente habla encima
            if (stageRef.current === "listening" || stageRef.current === "speaking") setStageBoth("hearing");
          },
          onVADMisfire: () => { if (stageRef.current === "hearing") setStageBoth("listening"); },
          onSpeechEnd: async (audio: Float32Array) => {
            if (busyRef.current || stageRef.current === "transcribing" || stageRef.current === "thinking") return;
            const wav = new Blob([utils.encodeWAV(audio)], { type: "audio/wav" });
            if (wav.size > maxAudioBytes) { setStageBoth("listening"); return; }
            setStageBoth("transcribing");
            try {
              const r = await api.voiceStt(wav, lang);
              const text = r.text.trim();
              if (!text) { setStageBoth("listening"); return; }
              setStageBoth("thinking");
              await sendRef.current(text);
            } catch (e) {
              fail(e instanceof ApiError && e.code === "voice_budget_exceeded" ? v.budget : v.sttFailed);
            }
          },
        });
        if (cancelled) { await vad.destroy(); return; }
        vadRef.current = vad;
        await vad.start();
        setStageBoth("listening");
      } catch {
        if (!cancelled) fail(v.micFailed);
      }
    })();
    return () => {
      cancelled = true;
      stopAudio();
      void vadRef.current?.destroy();
      vadRef.current = null;
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // el asistente habla solo después de cada turno nuevo
  useEffect(() => {
    if (!lastTurn || lastTurn.id === spokenRef.current || lastTurn.id.startsWith("greet-") || stageRef.current === "starting") return;
    spokenRef.current = lastTurn.id;
    let alive = true;
    (async () => {
      try {
        const blob = await api.voiceTts(lastTurn.conversationId, lastTurn.id);
        const buffer = await audioContext.decodeAudioData(await blob.arrayBuffer());
        if (!alive) return;
        stopAudio();
        const src = audioContext.createBufferSource();
        src.buffer = buffer;
        src.connect(audioContext.destination);
        src.onended = () => { if (sourceRef.current === src) { sourceRef.current = null; if (stageRef.current === "speaking") setStageBoth("listening"); } };
        sourceRef.current = src;
        setStageBoth("speaking");
        src.start();
      } catch (e) {
        if (alive) fail(e instanceof ApiError && e.code === "voice_budget_exceeded" ? v.budget : v.ttsFailed);
      }
    })();
    return () => { alive = false; };
  }, [lastTurn?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // terminó el turno sin respuesta nueva (p. ej. un error): vuelve a escuchar
  useEffect(() => {
    if (!sending && stageRef.current === "thinking" && lastTurn?.id === spokenRef.current) setStageBoth("listening");
  }, [sending]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") exitRef.current(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const confirmation = state === "confirmando_accion" ? lastTurn?.blocks.find((b) => b.type === "action_confirmation") : undefined;
  useEffect(() => { if (confirmation) confirmRef.current?.focus(); }, [confirmation?.type === "action_confirmation" ? confirmation.confirmation_token : null]); // eslint-disable-line react-hooks/exhaustive-deps

  const busy = sending || stage === "transcribing" || stage === "thinking";
  const orb: "listening" | "hearing" | "thinking" | "speaking" | "starting" =
    stage === "speaking" ? "speaking" : busy ? "thinking" : stage === "hearing" ? "hearing" : stage === "starting" ? "starting" : "listening";
  const label = orb === "speaking" ? v.speaking : orb === "thinking" ? (stage === "transcribing" ? v.transcribing : phase ? T[lang].chat.phases[phase] ?? v.thinking : v.thinking)
    : orb === "hearing" ? v.hearing : orb === "starting" ? v.starting : v.listening;
  const banky: BankyState = orb === "speaking" ? "talking" : orb === "thinking" ? stateForPhase(sending ? phase : null) : orb === "starting" ? "greeting" : "listening";
  const response = lastTurn ? turnText(lastTurn.blocks) : "";
  const options = lastTurn && !confirmation ? sayable(lastTurn.blocks) : [];

  return (
    <div className="voice-mode" role="dialog" aria-modal="true" aria-labelledby="vm-title">
      <header className="vm-top">
        <h2 id="vm-title">{v.title}</h2>
        <button type="button" className="btn secondary" onClick={() => onExit()}>{v.exit}</button>
      </header>

      <div className="vm-stage">
        <div className={`vm-orb ${orb}`} aria-hidden="true">
          <span className="vm-ring" /><span className="vm-ring" />
          <Banky state={banky} size={96} />
        </div>
        <p className="vm-status" role="status" aria-live="polite">{label}</p>
      </div>

      <div className="vm-texts">
        {lastHeard && <p className="vm-heard"><span className="vm-who">{v.you}</span>{lastHeard}</p>}
        {confirmation && confirmation.type === "action_confirmation" ? (
          <div className="vm-confirm">
            <p className="vm-summary">{confirmation.summary}</p>
            {confirmation.disclaimer && <p className="muted">{confirmation.disclaimer}</p>}
            <button ref={confirmRef} type="button" className="btn primary vm-confirm-btn" disabled={sending}
              onClick={() => onAction({ type: "confirm", confirmation_token: confirmation.confirmation_token }, T[lang].confirm)}>{T[lang].confirm}</button>
            <p className="muted small">{v.confirmHint}</p>
          </div>
        ) : response && (
          <p className="vm-answer" aria-live="polite"><span className="vm-who">Banky</span>{response}</p>
        )}
        {options.length > 0 && (
          <div className="vm-options">
            <p className="muted small">{v.youCanSay}</p>
            <ol>{options.map((o) => <li key={o}>{o}</li>)}</ol>
          </div>
        )}
      </div>
    </div>
  );
}

