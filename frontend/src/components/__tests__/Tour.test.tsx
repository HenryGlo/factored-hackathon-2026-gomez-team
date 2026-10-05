import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Tour, { TourButton, useTour, type TourStep } from "../Tour";
import { T } from "../../lib/i18n";
import type { Lang } from "../../api/types";

function Screen({ lang = "es" as Lang, steps }: { lang?: Lang; steps: TourStep[] }) {
  const tour = useTour("prueba", "ana", true);
  return (
    <div>
      <section id="a">A</section>
      <section id="b">B</section>
      <TourButton lang={lang} onClick={tour.start} />
      {tour.open && <Tour steps={steps} lang={lang} onClose={tour.close} />}
    </div>
  );
}

const steps: TourStep[] = [
  { target: "#a", title: "Primero", body: "Sección A" },
  { target: "#falta", title: "No existe", body: "Se salta" },
  { target: "#b", title: "Segundo", body: "Sección B" },
];

beforeEach(() => {
  localStorage.clear();
  // jsdom no calcula el layout: cada elemento mide 100×40
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockReturnValue({ top: 10, left: 10, bottom: 50, right: 110, width: 100, height: 40, x: 10, y: 10, toJSON: () => ({}) } as DOMRect);
});
afterEach(() => vi.restoreAllMocks());

describe("Tour", () => {
  it("se abre la primera vez, avanza, salta pasos sin sección y recuerda que se vio", async () => {
    render(<Screen steps={steps} />);
    expect(await screen.findByRole("dialog", {}, { timeout: 2000 })).toBeTruthy();
    expect(screen.getByText("Primero")).toBeTruthy();
    expect(screen.getByText(T.es.tour.step(1, 3))).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: T.es.tour.next }));
    expect(await screen.findByText("Segundo", {}, { timeout: 4000 })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: T.es.tour.done }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(localStorage.getItem("tour:prueba:ana:v1")).toBe("1");
  }, 10_000);

  it("no se abre si ya se vio, pero el botón lo repite; Esc lo cierra", async () => {
    localStorage.setItem("tour:prueba:ana:v1", "1");
    render(<Screen steps={steps} lang="en" />);
    await act(() => new Promise((r) => setTimeout(r, 900)));
    expect(screen.queryByRole("dialog")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: T.en.tour.start }));
    expect(await screen.findByText(T.en.tour.step(1, 3))).toBeTruthy();
    expect(screen.getByRole("button", { name: T.en.tour.skip })).toBeTruthy();
    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("tour:off lo desactiva (pruebas automáticas)", async () => {
    localStorage.setItem("tour:off", "1");
    render(<Screen steps={steps} />);
    await act(() => new Promise((r) => setTimeout(r, 900)));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("los tres idiomas tienen el mismo número de pasos", () => {
    for (const k of ["admin", "inbox", "ticket"] as const) {
      expect(T.pt.tour[k].length).toBe(T.es.tour[k].length);
      expect(T.en.tour[k].length).toBe(T.es.tour[k].length);
    }
    expect(T.es.tour.admin).toHaveLength(11);
    expect(T.es.tour.inbox).toHaveLength(5);
    expect(T.es.tour.ticket).toHaveLength(7);
  });
});
