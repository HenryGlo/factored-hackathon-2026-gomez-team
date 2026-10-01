import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CandidateListBlock, ResultBlock, TxView } from "../../api/types";
import BlockView from "../blocks/BlockView";

afterEach(cleanup);

const tx = (id: string, label: string): TxView => ({
  transaction_id: id, date: "2026-06-08T12:00:00", amount: "10.00", currency: "USD", merchant_name: label, label, channel: "POS",
  type: "Purchase", status: "Approved", amount_label: "10,00 USD", date_label: "8 jun 2026", status_label: "Aprobado",
});

describe("BlockView", () => {
  it("multi_select: suggested are preselected, 'Todos estos' sends every shown id", () => {
    const block: CandidateListBlock = { type: "candidate_list", prompt: "Elige", allow_none: true, round: 1, max_rounds: 3, multi_select: true,
      suggested: ["a", "b"], select_all_label: "Todos estos", candidates: [tx("a", "Uno"), tx("b", "Dos"), tx("c", "Tres")] };
    const onAction = vi.fn();
    render(<BlockView block={block} lang="es" state="aclarando" active onAction={onAction} />);
    expect((screen.getAllByRole("checkbox") as HTMLInputElement[]).map((c) => c.checked)).toEqual([true, true, false]);
    fireEvent.click(screen.getByRole("button", { name: "Elegir 2 seleccionados" }));
    expect(onAction).toHaveBeenCalledWith({ type: "select_candidates", transaction_ids: ["a", "b"] }, "Elegir 2 seleccionados");
  });

  it("multi_select: 'Todos estos' sends all shown ids", () => {
    const block: CandidateListBlock = { type: "candidate_list", prompt: "Elige", allow_none: false, round: 1, max_rounds: 3, multi_select: true,
      suggested: [], candidates: [tx("a", "Uno"), tx("b", "Dos")] };
    const onAction = vi.fn();
    render(<BlockView block={block} lang="es" state="aclarando" active onAction={onAction} />);
    fireEvent.click(screen.getByRole("button", { name: "Todos estos" }));
    expect(onAction.mock.calls[0][0]).toEqual({ type: "select_candidates", transaction_ids: ["a", "b"] });
  });

  it("buttons of a previous turn are inactive", () => {
    const block: CandidateListBlock = { type: "candidate_list", prompt: "Elige", allow_none: true, round: 1, max_rounds: 3, candidates: [tx("a", "Uno")] };
    render(<BlockView block={block} lang="es" state="aclarando" active={false} onAction={vi.fn()} />);
    screen.getAllByRole("button").forEach((b) => expect((b as HTMLButtonElement).disabled).toBe(true));
  });

  it("'Verificado' only with verified: true; partial results show each item", () => {
    const fake: ResultBlock = { type: "result", action: "create_dispute_case", status: "success", verified: false, reference_id: "case_1", details: null };
    const { rerender } = render(<BlockView block={fake} lang="es" state="inicio" active onAction={vi.fn()} />);
    expect(screen.queryByText("Verificado")).toBeNull();
    const partial: ResultBlock = { type: "result", action: "create_dispute_case", status: "partial", verified: false, reference_id: null, details: null,
      items: [{ transaction_id: "a", reference_id: "case_a", status: "success", verified: true, label: "Uno" },
              { transaction_id: "b", reference_id: null, status: "failed", verified: false, label: "Dos" }] };
    rerender(<BlockView block={partial} lang="es" state="inicio" active onAction={vi.fn()} />);
    expect(screen.getByText("Parcial")).toBeTruthy();
    expect(screen.getByText("case_a")).toBeTruthy();
  });

  it("shows the short reference to the customer, not the internal ID", () => {
    const ok: ResultBlock = { type: "result", action: "create_dispute_case", status: "success", verified: true,
      reference_id: "case_01J9Z8ABCDEF3F9A1C", reference_label: "RCL-3F9A1C", details: null };
    render(<BlockView block={ok} lang="es" state="inicio" active onAction={vi.fn()} />);
    expect(screen.getByText("RCL-3F9A1C")).toBeTruthy();
    expect(screen.queryByText("case_01J9Z8ABCDEF3F9A1C")).toBeNull();
  });

  it("text blocks are plain text, never HTML", () => {
    const { container } = render(<BlockView block={{ type: "text", text: "<img src=x onerror=alert(1)>hola" }} lang="es" state="inicio" active onAction={vi.fn()} />);
    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toContain("<img");
  });
});
