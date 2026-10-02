// Modo voz (detrás de VOICE_ENABLED): micrófono con pulsar o mantener, onda mientras escucha y transcripción visible y
// editable antes de enviar. El audio solo se transcribe (POST /api/voice/stt); el texto revisado entra al chat como un turno
// normal con via: "voice", por el mismo flujo y las mismas guardas. Las confirmaciones siguen siendo tarjetas con botón.
// Ante cualquier error de voz se avisa y se vuelve al texto (details.fallback = "text").
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type { Lang, VoiceConfig } from "../api/types";
import { T } from "../lib/i18n";

const MAX_SECONDS = 45;
const HOLD_MS = 500;
const BARS = 9;
const PERM_KEY = "voice_mic_explained";

type Stage = "explain" | "idle" | "recording" | "transcribing" | "review";

function explained(): boolean {
  try { return sessionStorage.getItem(PERM_KEY) === "1"; } catch { return false; }
}

export default function VoiceComposer({ lang, config, disabled, onSend, onFallback, onListening }: {
  lang: Lang;
  config: VoiceConfig;
  disabled: boolean;
  onSend: (text: string) => void;
  /** La voz no se puede usar: se muestra el motivo y el chat sigue por texto. */
  onFallback: (message: string) => void;
  onListening?: (listening: boolean) => void;
}) {
  const v = T[lang].voice;
  const [stage, setStage] = useState<Stage>(() => (explained() ? "idle" : "explain"));
  const [text, setText] = useState("");
  const [note, setNote] = useState<string | null>(null);
  const [levels, setLevels] = useState<number[]>(() => Array(BARS).fill(0.15));
  const rec = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const audioCtx = useRef<AudioContext | null>(null);
  const raf = useRef(0);
  const chunks = useRef<Blob[]>([]);
  const pressedAt = useRef(0);
  const stopTimer = useRef<ReturnType<typeof setTimeout>>();
  const reviewRef = useRef<HTMLTextAreaElement>(null);

  const release = useCallback(() => {
    cancelAnimationFrame(raf.current);
    clearTimeout(stopTimer.current);
    stream.current?.getTracks().forEach((t) => t.stop());
    stream.current = null;
    void audioCtx.current?.close().catch(() => undefined);
    audioCtx.current = null;
  }, []);

  useEffect(() => release, [release]);
  useEffect(() => { onListening?.(stage === "recording"); }, [stage, onListening]);
  useEffect(() => { if (stage === "review") reviewRef.current?.focus(); }, [stage]);

  const transcribe = useCallback(async (blob: Blob) => {
    if (blob.size === 0) { setNote(v.empty); setStage("idle"); return; }
    if (blob.size > config.max_audio_bytes) { setNote(v.tooLong); setStage("idle"); return; }
    setStage("transcribing");
    try {
      const r = await api.voiceStt(blob, lang);
      if (!r.text.trim()) { setNote(v.empty); setStage("idle"); return; }
      setText(r.text);
      setNote(r.truncated ? v.truncated : null);
      setStage("review");
    } catch (e) {
      if (e instanceof ApiError && e.code === "audio_too_large") { setNote(v.tooLong); setStage("idle"); return; }
      setStage("idle");
      onFallback(e instanceof ApiError && e.code === "voice_budget_exceeded" ? v.budget : v.fallback);
    }
  }, [config.max_audio_bytes, lang, onFallback, v]);

  const start = useCallback(async () => {
    setNote(null);
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") { onFallback(v.unsupported); return; }
    let s: MediaStream;
    try {
      s = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      onFallback(v.denied);            // rechazo del permiso: se explica y se sigue por texto
      return;
    }
    try { sessionStorage.setItem(PERM_KEY, "1"); } catch { /* sin almacenamiento */ }
    stream.current = s;
    const type = ["audio/webm", "audio/mp4", "audio/ogg"].find((m) => MediaRecorder.isTypeSupported(m));
    const r = new MediaRecorder(s, type ? { mimeType: type } : undefined);
    chunks.current = [];
    r.ondataavailable = (ev) => { if (ev.data.size) chunks.current.push(ev.data); };
    r.onstop = () => { release(); void transcribe(new Blob(chunks.current, { type: r.mimeType || type || "audio/webm" })); };
    rec.current = r;
    r.start();
    setStage("recording");
    stopTimer.current = setTimeout(() => { if (r.state === "recording") r.stop(); }, MAX_SECONDS * 1000);
    // onda: niveles reales del micrófono (no es una animación decorativa)
    try {
      const ctx = new AudioContext();
      audioCtx.current = ctx;
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 64;
      ctx.createMediaStreamSource(s).connect(analyser);
      const data = new Uint8Array(analyser.frequencyBinCount);
      const tick = () => {
        analyser.getByteFrequencyData(data);
        setLevels(Array.from({ length: BARS }, (_, i) => Math.max(0.12, data[i * 2] / 255)));
        raf.current = requestAnimationFrame(tick);
      };
      tick();
    } catch {
      /* sin AudioContext: se graba igual, sin onda */
    }
  }, [onFallback, release, transcribe, v]);

  const stop = useCallback(() => { if (rec.current?.state === "recording") rec.current.stop(); }, []);

  // pulsar = empezar/terminar; mantener presionado = habla mientras se sostiene
  const onDown = () => { if (stage === "idle") { pressedAt.current = Date.now(); void start(); } else if (stage === "recording") { pressedAt.current = 0; stop(); } };
  const onUp = () => { if (stage === "recording" && pressedAt.current && Date.now() - pressedAt.current > HOLD_MS) stop(); };

  if (stage === "explain") {
    return (
      <div className="voice-panel explain" role="group" aria-labelledby="voice-perm">
        <h2 id="voice-perm">{v.permTitle}</h2>
        <p>{v.permText}</p>
        <div className="actions">
          <button className="btn primary" type="button" onClick={() => { setStage("idle"); void start(); }}>{v.permAllow}</button>
          <button className="btn ghost" type="button" onClick={() => onFallback("")}>{v.permSkip}</button>
        </div>
      </div>
    );
  }

  if (stage === "review") {
    return (
      <form className="voice-panel review" onSubmit={(e) => { e.preventDefault(); const m = text.trim(); if (m) { setText(""); setStage("idle"); onSend(m); } }}>
        <label htmlFor="voice-text">{v.review}</label>
        <textarea id="voice-text" ref={reviewRef} rows={2} maxLength={2000} value={text} onChange={(e) => setText(e.target.value)} aria-label={v.transcript} />
        {note && <p className="muted small" role="status">{note}</p>}
        <div className="actions">
          <button className="btn primary" type="submit" disabled={disabled || !text.trim()}>{v.send}</button>
          <button className="btn ghost" type="button" onClick={() => { setText(""); setNote(null); setStage("idle"); }}>{v.discard}</button>
        </div>
      </form>
    );
  }

  const recording = stage === "recording";
  return (
    <div className="voice-panel">
      <button type="button" className={`mic ${recording ? "on" : ""}`} aria-pressed={recording} aria-label={recording ? v.stop : v.start}
        disabled={disabled || stage === "transcribing"} onPointerDown={onDown} onPointerUp={onUp} onPointerLeave={onUp}
        onKeyDown={(e) => { if ((e.key === "Enter" || e.key === " ") && !e.repeat) { e.preventDefault(); onDown(); } }}>
        <svg viewBox="0 0 24 24" width="28" height="28" aria-hidden="true"><path fill="currentColor" d="M12 15a3.5 3.5 0 0 0 3.5-3.5v-5a3.5 3.5 0 0 0-7 0v5A3.5 3.5 0 0 0 12 15zm6-3.5a1 1 0 0 1 2 0 8 8 0 0 1-7 7.9V21a1 1 0 0 1-2 0v-1.6a8 8 0 0 1-7-7.9 1 1 0 0 1 2 0 6 6 0 0 0 12 0z" /></svg>
      </button>
      <div className="voice-status">
        {recording ? (
          <>
            <span className="wave" aria-hidden="true">{levels.map((l, i) => <i key={i} style={{ transform: `scaleY(${l})` }} />)}</span>
            <span role="status">{v.listening}</span>
          </>
        ) : stage === "transcribing" ? <span role="status">{v.transcribing}</span> : <span className="muted small">{v.hint}</span>}
        {note && !recording && <span className="small" role="status">{note}</span>}
        <span className="muted small">{v.confirmNote}</span>
      </div>
    </div>
  );
}
