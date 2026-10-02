import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import Banky, { stateForPhase } from "../Banky";
import ThinkingIndicator from "../ThinkingIndicator";

afterEach(cleanup);

describe("Banky", () => {
  it("maps each real turn phase to a state and never guesses without a phase", () => {
    expect(stateForPhase("understanding")).toBe("thinking");
    expect(stateForPhase("searching_transactions")).toBe("searching");
    expect(stateForPhase("checking_policy")).toBe("checking");
    expect(stateForPhase("writing")).toBe("talking");
    expect(stateForPhase(null)).toBe("thinking");
  });

  it("is an image with an accessible name when labelled and hidden when decorative", () => {
    const { container, rerender } = render(<Banky state="happy" label="Banky está contento: listo" />);
    expect(screen.getByRole("img", { name: "Banky está contento: listo" }).getAttribute("data-state")).toBe("happy");
    rerender(<Banky state="idle" />);
    expect(container.querySelector("svg")?.getAttribute("aria-hidden")).toBe("true");
  });

  it("follows the phase reported by the backend in the waiting indicator", () => {
    const { container, rerender } = render(<ThinkingIndicator phase="searching_transactions" label="Buscando…" />);
    expect(container.querySelector(".banky")?.getAttribute("data-state")).toBe("searching");
    rerender(<ThinkingIndicator phase="checking_policy" label="Revisando…" />);
    expect(container.querySelector(".banky")?.getAttribute("data-state")).toBe("checking");
  });
});
