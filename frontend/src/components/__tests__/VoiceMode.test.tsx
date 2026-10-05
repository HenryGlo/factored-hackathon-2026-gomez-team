import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "../../api/client";
import type { Block } from "../../api/types";
import VoiceMode, { turnText, type VoiceTurn } from "../VoiceMode";

type VadOptions = { onSpeechStart: () => void; onSpeechEnd: (a: Float32Array) => Promise<void>; onVADMisfire: () => void };
let vadOptions: VadOptions;
const vad = { start: vi.fn(async () => undefined), pause: vi.fn(), destroy: vi.fn(async () => undefined) };
vi.mock("@ricky0123/vad-web", () => ({
  MicVAD: { new: vi.fn(async (opts: VadOptions) => { vadOptions = opts; return vad; }) },
  utils: { encodeWAV: () => new ArrayBuffer(16) },
}));

const source = { buffer: null as unknown, connect: vi.fn(), start: vi.fn(), stop: vi.fn(), onended: null as null | (() => void) };
const audioContext = {
  decodeAudioData: vi.fn(async () => ({ duration: 1 })),
  createBufferSource: vi.fn(() => source),
  destination: {},
} as unknown as AudioContext;

const turn = (id: string, blocks: Block[]): VoiceTurn => ({ id, conversationId: "conv_1", blocks });

function setup(props: Partial<Parameters<typeof VoiceMode>[0]> = {}) {
  const onSend = vi.fn(async () => undefined);
  const onAction = vi.fn();
  const onExit = vi.fn();
  const utils = render(<VoiceMode lang="es" audioContext={audioContext} maxAudioBytes={2_000_000} lastHeard={null}
    lastTurn={turn("greet-1", [{ type: "text", text: "Hola, ¿en qué te ayudo?" }])} state="inicio" sending={false} phase={null}
    onSend={onSend} onAction={onAction} onExit={onExit} {...props} />);
  return { ...utils, onSend, onAction, onExit };
}

beforeEach(() => { vi.clearAllMocks(); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("VoiceMode", () => {
  it("transcribes each phrase when the speaker stops and sends it as a voice turn, with no manual step", async () => {
    const stt = vi.spyOn(api, "voiceStt").mockResolvedValue({ text: "ver mis movimientos", language_code: "es", seconds: 1.2, truncated: false });
    const { onSend } = setup();
    await waitFor(() => expect(vad.start).toHaveBeenCalled());
    expect(screen.getByRole("status").textContent).toMatch(/Te escucho/);
    await act(async () => { vadOptions.onSpeechStart(); });
    expect(screen.getByRole("status").textContent).toMatch(/Escuchando/);
    await act(async () => { await vadOptions.onSpeechEnd(new Float32Array(16000)); });
    expect(stt).toHaveBeenCalledWith(expect.any(Blob), "es");
    expect((stt.mock.calls[0][0] as Blob).type).toBe("audio/wav");
    expect(onSend).toHaveBeenCalledWith("ver mis movimientos");
  });

  it("speaks each new assistant turn by itself and stops talking when the customer speaks over it (barge-in)", async () => {
    const tts = vi.spyOn(api, "voiceTts").mockResolvedValue({ arrayBuffer: async () => new ArrayBuffer(8) } as unknown as Blob);
    const { rerender } = setup();
    await waitFor(() => expect(vad.start).toHaveBeenCalled());
    expect(tts).not.toHaveBeenCalled();                                        // la bienvenida que ya estaba no se lee
    rerender(<VoiceMode lang="es" audioContext={audioContext} maxAudioBytes={2_000_000} lastHeard="ver mis movimientos"
      lastTurn={turn("turn_2", [{ type: "text", text: "Estos son tus últimos movimientos. ¿Cuál no reconoces?" }])} state="inicio" sending={false}
      phase={null} onSend={vi.fn()} onAction={vi.fn()} onExit={vi.fn()} />);
    await waitFor(() => expect(source.start).toHaveBeenCalled());
    expect(tts).toHaveBeenCalledWith("conv_1", "turn_2");
    expect(screen.getByRole("status").textContent).toMatch(/Banky está hablando/);
    expect(screen.getByText("Estos son tus últimos movimientos. ¿Cuál no reconoces?")).toBeTruthy();
    await act(async () => { vadOptions.onSpeechStart(); });
    expect(source.stop).toHaveBeenCalled();
  });

  it("with a pending confirmation shows the summary large and a big Confirmar button: the voice never confirms", async () => {
    const confirmation: Block = { type: "action_confirmation", action: "create_dispute_case", summary: "Voy a registrar un reclamo por Netflix, 15,99 USD.",
      params: {}, confirmation_token: "tok_1", expires_at: "", disclaimer: "No es una devolución." };
    const { onAction } = setup({ lastTurn: turn("greet-x", [confirmation]), state: "confirmando_accion" });
    expect(screen.getByText("Voy a registrar un reclamo por Netflix, 15,99 USD.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Confirmar" }));
    expect(onAction).toHaveBeenCalledWith({ type: "confirm", confirmation_token: "tok_1" }, "Confirmar");
  });

  it("lists what the customer can say instead of buttons to tap", () => {
    setup({ lastTurn: turn("greet-y", [{ type: "notice", level: "info", code: "need_detail", text: "¿Me das algún dato del cargo?" },
      { type: "quick_replies", options: [{ label: "Ver mis últimos movimientos", action: { type: "start_topic", topic: "consulta_movimientos" } }] }]) });
    expect(screen.getByText("Puedes decir, por ejemplo:")).toBeTruthy();
    expect(screen.getByText("Ver mis últimos movimientos").tagName).toBe("LI");
    expect(screen.queryByRole("button", { name: /Ver mis últimos movimientos/ })).toBeNull();
  });

  it("goes back to the written chat with a notice when transcription fails", async () => {
    vi.spyOn(api, "voiceStt").mockRejectedValue(new ApiError(502, "voice_unavailable", "falló", "req", true, { fallback: "text" }));
    const { onExit } = setup();
    await waitFor(() => expect(vad.start).toHaveBeenCalled());
    await act(async () => { await vadOptions.onSpeechEnd(new Float32Array(8000)); });
    expect(onExit).toHaveBeenCalledWith(expect.stringMatching(/No pude entender el audio/));
  });

  it("builds the large answer text from what the assistant said", () => {
    expect(turnText([{ type: "text", text: "Hola." }, { type: "handoff_notice", handoff_id: "h", reason_code: "x", message: "Te paso con una persona." }]))
      .toBe("Hola. Te paso con una persona.");
  });
});
