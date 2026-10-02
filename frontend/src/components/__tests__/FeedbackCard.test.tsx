import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "../../api/client";
import FeedbackCard from "../FeedbackCard";
import ModeChoice from "../ModeChoice";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("FeedbackCard", () => {
  it("sends a thumbs down with category and comment", async () => {
    const spy = vi.spyOn(api, "feedback").mockResolvedValue({ feedback_id: "fb_1" });
    render(<FeedbackCard conversationId="conv_1" lang="es" />);
    expect(screen.queryByRole("button", { name: "Enviar valoración" })).toBeNull();      // nada que enviar sin elegir
    fireEvent.click(screen.getByRole("button", { name: /No me ayudó/ }));
    fireEvent.click(screen.getByRole("button", { name: "Fue lento" }));
    fireEvent.change(screen.getByLabelText("Comentario (opcional)"), { target: { value: " tardó mucho " } });
    fireEvent.click(screen.getByRole("button", { name: "Enviar valoración" }));
    await waitFor(() => expect(screen.getByRole("status").textContent).toMatch(/quedó registrada/));
    expect(spy).toHaveBeenCalledWith("conv_1", { rating: "down", category: "lento", comment: "tardó mucho" });
  });

  it("never sends a category with a thumbs up and treats 409 feedback_exists as already sent", async () => {
    const spy = vi.spyOn(api, "feedback").mockRejectedValue(new ApiError(409, "feedback_exists", "ya existe", "req_1"));
    render(<FeedbackCard conversationId="conv_1" lang="es" />);
    fireEvent.click(screen.getByRole("button", { name: /Sí, me ayudó/ }));
    expect(screen.queryByText("¿Qué pasó?")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Enviar valoración" }));
    await waitFor(() => expect(screen.getByRole("status").textContent).toMatch(/Ya habías valorado/));
    expect(spy).toHaveBeenCalledWith("conv_1", { rating: "up", category: null, comment: null });
  });
});

describe("ModeChoice", () => {
  it("shows nothing when voice is off: no voice button and no notice", () => {
    const { container } = render(<ModeChoice lang="es" mode={null} voiceEnabled={false} onChoose={vi.fn()} />);
    expect(container.textContent).toBe("");
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("asks text or voice when voice is enabled", () => {
    const onChoose = vi.fn();
    render(<ModeChoice lang="pt" mode={null} voiceEnabled onChoose={onChoose} />);
    fireEvent.click(screen.getByRole("button", { name: /Falar por voz/ }));
    expect(onChoose).toHaveBeenCalledWith("voice");
    fireEvent.click(screen.getByRole("button", { name: /Escrever/ }));
    expect(onChoose).toHaveBeenCalledWith("text");
  });
});
