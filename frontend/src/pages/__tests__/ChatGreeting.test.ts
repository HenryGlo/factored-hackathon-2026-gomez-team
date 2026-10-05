import { describe, expect, it } from "vitest";
import { withoutGreetingWord } from "../ChatPage";

describe("single welcome: the backend greeting word is not repeated", () => {
  it.each([
    ["Hola, ¿en qué te ayudo? Puedo ayudarte con…", "¿En qué te ayudo? Puedo ayudarte con…"],
    ["Olá! Como posso ajudar? Posso ajudar com…", "Como posso ajudar? Posso ajudar com…"],
    ["Oi, como posso ajudar?", "Como posso ajudar?"],
    ["Puedo ayudarte con un cargo.", "Puedo ayudarte con un cargo."],
    ["Holanda no es un saludo.", "Holanda no es un saludo."],
  ])("%s", (text, expected) => {
    const [b] = withoutGreetingWord([{ type: "text", text }]);
    expect(b.type === "text" && b.text).toBe(expected);
  });
});
