import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "../../api/client";
import type { VoiceConfig } from "../../api/types";
import VoiceComposer from "../VoiceComposer";

const config: VoiceConfig = { enabled: true, reason: null, max_audio_bytes: 2_000_000, max_tts_chars: 700, audio_types: ["audio/webm"] };

class FakeRecorder {
  static isTypeSupported = () => true;
  state = "inactive";
  mimeType = "audio/webm";
  ondataavailable: ((e: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  start() { this.state = "recording"; }
  stop() { this.state = "inactive"; this.ondataavailable?.({ data: new Blob(["audio"], { type: "audio/webm" }) }); this.onstop?.(); }
}

function setup(getUserMedia: () => Promise<unknown>) {
  Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia } });
  vi.stubGlobal("MediaRecorder", FakeRecorder);
  const onSend = vi.fn();
  const onFallback = vi.fn();
  render(<VoiceComposer lang="es" config={config} disabled={false} onSend={onSend} onFallback={onFallback} />);
  return { onSend, onFallback };
}

beforeEach(() => sessionStorage.clear());
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe("VoiceComposer", () => {
  it("explains before asking for the microphone and falls back to text when permission is denied", async () => {
    const { onFallback } = setup(() => Promise.reject(new DOMException("denied", "NotAllowedError")));
    expect(screen.getByText(/necesito usar tu micrófono/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Permitir el micrófono" }));
    await waitFor(() => expect(onFallback).toHaveBeenCalledWith(expect.stringMatching(/No tengo permiso/)));
  });

  it("shows the transcript, lets the customer edit it and only then sends it", async () => {
    const stt = vi.spyOn(api, "voiceStt").mockResolvedValue({ text: "No reconozco un cobro de 120", language_code: "es", seconds: 2, truncated: false });
    const { onSend } = setup(() => Promise.resolve({ getTracks: () => [] }));
    fireEvent.click(screen.getByRole("button", { name: "Permitir el micrófono" }));
    const mic = await screen.findByRole("button", { name: "Terminar de hablar" });
    expect(screen.getByText("Escuchando…")).toBeTruthy();
    await act(async () => { fireEvent.pointerDown(mic); });
    const box = await screen.findByLabelText("Transcripción") as HTMLTextAreaElement;
    expect(box.value).toBe("No reconozco un cobro de 120");
    expect(stt).toHaveBeenCalledTimes(1);
    expect(onSend).not.toHaveBeenCalled();                              // nada se envía sin revisar
    fireEvent.change(box, { target: { value: "No reconozco un cobro de 130" } });
    fireEvent.click(screen.getByRole("button", { name: "Enviar" }));
    expect(onSend).toHaveBeenCalledWith("No reconozco un cobro de 130");
  });

  it("falls back to text when the voice provider fails", async () => {
    vi.spyOn(api, "voiceStt").mockRejectedValue(new ApiError(502, "voice_unavailable", "La voz falló", "req", true, { fallback: "text" }));
    const { onFallback } = setup(() => Promise.resolve({ getTracks: () => [] }));
    fireEvent.click(screen.getByRole("button", { name: "Permitir el micrófono" }));
    const mic = await screen.findByRole("button", { name: "Terminar de hablar" });
    await act(async () => { fireEvent.pointerDown(mic); });
    await waitFor(() => expect(onFallback).toHaveBeenCalledWith(expect.stringMatching(/no está disponible/)));
  });
});
