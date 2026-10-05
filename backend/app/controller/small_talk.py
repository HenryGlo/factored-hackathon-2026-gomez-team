"""Atajo para mensajes que son SOLO saludo, agradecimiento o despedida (es/pt): se responden con plantilla, sin LLM ni
herramientas. Basta una palabra fuera del vocabulario ("hola, tengo un cobro de 120") para que el mensaje siga el flujo
normal: el atajo nunca decide sobre un pedido."""
from __future__ import annotations

import re

from backend.app.dates import normalize

# palabras núcleo: al menos una tiene que aparecer
CORE = {
    "greeting": {"hola", "holi", "holis", "buenas", "buen", "buenos", "hey", "saludos", "oi", "ola", "bom", "boa", "hello", "hi", "hiya", "morning", "afternoon", "evening"},
    # "¿cómo estás?" / "tudo bem?" sin saludo delante también es un saludo
    "how": {"estas", "andas", "tal", "bem", "bien", "vai", "doing", "going"},
    "thanks": {"gracias", "agradezco", "obrigado", "obrigada", "valeu", "brigado", "brigada", "thanks", "thank", "thx", "cheers"},
    "farewell": {"chao", "chau", "adios", "luego", "pronto", "tchau", "logo", "bye", "goodbye"},
}
# acompañantes: pueden aparecer, pero solos no bastan ("que tal", "muito")
FILLER = {"dia", "dias", "tardes", "noches", "tarde", "noite", "que", "tal", "como", "estas", "esta", "usted", "tudo", "bem", "e", "ai",
          "y", "muchas", "muchisimas", "mil", "te", "lo", "muito", "hasta", "manana", "nos", "vemos", "ate", "mais", "todo", "voce", "tu", "vc",
          "good", "you", "very", "much", "a", "lot", "how", "are", "is", "it", "there", "see", "later", "so", "have", "nice", "day", "great"}
PT = {"oi", "ola", "bom", "boa", "noite", "tudo", "bem", "obrigado", "obrigada", "valeu", "brigado", "brigada", "tchau", "logo",
      "muito", "ate", "mais", "voce", "vai", "vc"}
EN = {"hello", "hi", "hiya", "morning", "afternoon", "evening", "thanks", "thank", "thx", "cheers", "bye", "goodbye", "doing",
      "going", "good", "you", "how", "are", "see", "later", "nice", "day", "great"}
ES = {"hola", "holi", "holis", "buenas", "buen", "buenos", "tardes", "noches", "gracias", "agradezco", "muchas", "muchisimas", "chao",
      "chau", "adios", "luego", "hasta", "estas", "saludos", "manana", "andas", "bien", "todo"}


def small_talk(text: str) -> tuple[str, str | None] | None:
    """('greeting' | 'thanks' | 'farewell', idioma o None) si el mensaje es SOLO eso; None en cualquier otro caso."""
    words = re.findall(r"[a-z]+", normalize(text))
    if not words or len(words) > 8 or re.search(r"\d", text):
        return None
    core = set().union(*CORE.values())
    if any(w not in core and w not in FILLER for w in words) or not any(w in core for w in words):
        return None
    kind = next(k for k in ("farewell", "thanks", "greeting", "how") if any(w in CORE[k] for w in words))
    if kind == "how":
        kind = "greeting"
    pt = sum(w in PT for w in words) + (2 if "olá" in text.lower() else 0)
    es = sum(w in ES for w in words)
    en = sum(w in EN for w in words)
    if en > max(pt, es):
        return kind, "en"
    return kind, ("pt" if pt > es else "es" if es > pt else None)


HOW_ARE_YOU = re.compile(r"\b(como (estas|esta|andas|vai|te va)|que tal|tudo bem|tudo bom|todo bien|como voce esta|how are you|how'?s it going|how are you doing)\b")


def asks_how_are_you(text: str) -> bool:
    """El saludo pregunta por el asistente ("¿cómo estás?", "tudo bem?"): la respuesta lo contesta antes de reencauzar."""
    return bool(HOW_ARE_YOU.search(normalize(text)))
