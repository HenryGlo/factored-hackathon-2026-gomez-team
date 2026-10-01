import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client";
import type { TurnPhase } from "../../api/types";
import ThinkingIndicator, { useTurnPhase } from "../ThinkingIndicator";

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.useRealTimers(); });

function Probe({ waiting }: { waiting: boolean }) {
  const phase = useTurnPhase("conv_1", waiting);
  return <ThinkingIndicator phase={phase} label={phase === "searching_transactions" ? "Buscando en tus movimientos…" : "Escribiendo…"} />;
}

async function advance(ms: number) {
  await act(async () => { await vi.advanceTimersByTimeAsync(ms); });
}

describe("ThinkingIndicator", () => {
  it("is neutral by default and says 'searching' only when the backend reports searching_transactions", async () => {
    vi.useFakeTimers();
    const phases: (TurnPhase | null)[] = ["understanding", "searching_transactions"];
    vi.spyOn(api, "phase").mockImplementation(async () => ({ phase: phases.shift() ?? "writing" }));
    render(<Probe waiting />);
    expect(screen.getByText("Escribiendo…")).toBeTruthy();          // antes de cualquier dato, nunca adivina
    await advance(300);
    expect(screen.getByText("Escribiendo…")).toBeTruthy();          // understanding
    await advance(700);
    expect(screen.getByText("Buscando en tus movimientos…")).toBeTruthy();
    await advance(700);
    expect(screen.getByText("Escribiendo…")).toBeTruthy();          // writing
  });

  it("stays neutral when the phase channel fails", async () => {
    vi.useFakeTimers();
    vi.spyOn(api, "phase").mockRejectedValue(new Error("network"));
    render(<Probe waiting />);
    await advance(2000);
    expect(screen.getByText("Escribiendo…")).toBeTruthy();
    expect(screen.getByRole("status").getAttribute("data-phase")).toBe("waiting");
  });
});
