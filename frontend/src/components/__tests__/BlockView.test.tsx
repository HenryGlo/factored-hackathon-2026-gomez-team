import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CandidateListBlock, NoticeBlock, QuickRepliesBlock, ResultBlock, TxView } from "../../api/types";
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

  it("link blocks open http(s) URLs in a new tab and drop any other scheme", () => {
    const { rerender, container } = render(<BlockView block={{ type: "link", label: "Ir a la página inicial del banco", url: "https://banco-demo.example/" }}
      lang="es" state="inicio" active onAction={vi.fn()} />);
    const a = screen.getByRole("link", { name: "Ir a la página inicial del banco" }) as HTMLAnchorElement;
    expect(a.href).toBe("https://banco-demo.example/");
    expect(a.target).toBe("_blank");
    expect(a.rel).toContain("noopener");
    rerender(<BlockView block={{ type: "link", label: "x", url: "javascript:alert(1)" }} lang="es" state="inicio" active onAction={vi.fn()} />);
    expect(container.querySelector("a")).toBeNull();
  });

  it("text blocks are plain text, never HTML", () => {
    const { container } = render(<BlockView block={{ type: "text", text: "<img src=x onerror=alert(1)>hola" }} lang="es" state="inicio" active onAction={vi.fn()} />);
    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toContain("<img");
  });

  it("quick_replies with topics: sends start_topic with its topic exactly as the backend gave it", () => {
    const block: QuickRepliesBlock = { type: "quick_replies", options: [
      { label: "Un cargo que no reconozco", action: { type: "start_topic", topic: "cargo_no_reconocido" } },
      { label: "Ver mis movimientos", action: { type: "start_topic", topic: "consulta_movimientos" } },
      { label: "Estado de un reclamo", action: { type: "start_topic", topic: "estado_reclamo" } },
      { label: "Bloquear mi tarjeta", action: { type: "start_topic", topic: "bloquear_tarjeta" } },
      { label: "Hablar con una persona", action: { type: "request_human" } },
    ] };
    const onAction = vi.fn();
    render(<BlockView block={block} lang="es" state="inicio" active onAction={onAction} />);
    expect(screen.getAllByRole("button")).toHaveLength(5);
    fireEvent.click(screen.getByRole("button", { name: /Bloquear mi tarjeta/ }));
    expect(onAction).toHaveBeenCalledWith({ type: "start_topic", topic: "bloquear_tarjeta" }, "Bloquear mi tarjeta");
    expect((screen.getByRole("button", { name: /Bloquear mi tarjeta/ }) as HTMLButtonElement).disabled).toBe(true);   // un solo envío
  });

  it("quick_replies from an earlier turn cannot be used", () => {
    const block: QuickRepliesBlock = { type: "quick_replies", options: [{ label: "Ver mis movimientos", action: { type: "start_topic", topic: "consulta_movimientos" } }] };
    const onAction = vi.fn();
    render(<BlockView block={block} lang="es" state="inicio" active={false} onAction={onAction} />);
    fireEvent.click(screen.getByRole("button", { name: /Ver mis movimientos/ }));
    expect(onAction).not.toHaveBeenCalled();
  });

  it("never shows the internal attempt counter of a clarification", () => {
    const block: CandidateListBlock = { type: "candidate_list", prompt: "Elige", allow_none: true, round: 3, max_rounds: 3, candidates: [tx("a", "Uno"), tx("b", "Dos")] };
    const { container } = render(<BlockView block={block} lang="es" state="aclarando" active onAction={vi.fn()} />);
    expect(container.textContent).not.toMatch(/3\s*(de|\/)\s*3|Intento/i);
  });

  it("asking for a detail or finding nothing: the options are one clear list and each sends its action once", () => {
    const block: QuickRepliesBlock = { type: "quick_replies", options: [
      { label: "Darte otro dato", action: { type: "new_request" } },
      { label: "Ver mis últimos movimientos", action: { type: "start_topic", topic: "consulta_movimientos" } },
      { label: "Hablar con una persona", action: { type: "request_human" } },
    ] };
    const onAction = vi.fn();
    const { container } = render(<BlockView block={block} lang="es" state="inicio" active onAction={onAction} />);
    expect(container.querySelectorAll(".options .option")).toHaveLength(3);
    fireEvent.click(screen.getByRole("button", { name: /Ver mis últimos movimientos/ }));
    fireEvent.click(screen.getByRole("button", { name: /Hablar con una persona/ }));
    expect(onAction).toHaveBeenCalledTimes(1);
    expect(onAction).toHaveBeenCalledWith({ type: "start_topic", topic: "consulta_movimientos" }, "Ver mis últimos movimientos");
  });

  it("keeps a plain yes/no pair inline", () => {
    const block: QuickRepliesBlock = { type: "quick_replies", options: [{ label: "Sí, otra consulta", action: { type: "new_request" } }, { label: "No, gracias", action: { type: "end_conversation" } }] };
    const { container } = render(<BlockView block={block} lang="es" state="inicio" active onAction={vi.fn()} />);
    expect(container.querySelector(".options")).toBeNull();
    expect(container.querySelectorAll(".quick .btn")).toHaveLength(2);
  });

  it("need_detail: asks for a detail with its own card and never lists movements", () => {
    const block: NoticeBlock = { type: "notice", level: "info", code: "need_detail", text: "Claro, te ayudo. ¿Me das algún dato del cargo: el monto, el comercio o la fecha aproximada?" };
    const { container } = render(<BlockView block={block} lang="es" state="aclarando" active onAction={vi.fn()} />);
    expect(container.querySelector(".clarify.need-detail")).toBeTruthy();
    expect(screen.getByText(/¿Me das algún dato del cargo/)).toBeTruthy();
    expect(screen.getAllByRole("listitem").map((x) => x.textContent)).toEqual(["El monto", "El comercio", "La fecha aproximada"]);
    expect(container.querySelector(".choice, .tx-line")).toBeNull();
  });

  it("no_match: says nothing matched and shows only the criteria the customer gave, with the data date", () => {
    const block: NoticeBlock = { type: "notice", level: "info", code: "no_match", text: "No encontré cargos de Facebook en tus movimientos hasta el 18 jun 2026.",
      criteria: { merchant: "Facebook", amount: null, date: null }, data_as_of: "2026-06-18" };
    const { container } = render(<BlockView block={block} lang="es" state="aclarando" active onAction={vi.fn()} />);
    expect(container.querySelector(".clarify.no-match")).toBeTruthy();
    expect(screen.getByText("No encontré cargos de Facebook en tus movimientos hasta el 18 jun 2026.")).toBeTruthy();
    expect(screen.getByText("Comercio")).toBeTruthy();
    expect(screen.getByText("Facebook")).toBeTruthy();
    expect(screen.queryByText("Monto")).toBeNull();                       // lo que el cliente no dio no se inventa
    expect(screen.queryByText("Fecha")).toBeNull();
    expect(container.querySelector(".as-of")?.textContent).toMatch(/Movimientos hasta el 18 jun 2026/);
  });

  it("other notices keep the plain notice look", () => {
    const block: NoticeBlock = { type: "notice", level: "warning", code: "pending_transaction", text: "El cargo está pendiente." };
    const { container } = render(<BlockView block={block} lang="es" state="inicio" active onAction={vi.fn()} />);
    expect(container.querySelector(".clarify")).toBeNull();
    expect(container.querySelector(".notice.warning")).toBeTruthy();
  });
});
