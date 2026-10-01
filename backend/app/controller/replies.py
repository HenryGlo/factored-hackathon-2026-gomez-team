"""Respuestas cortas de sí / no en los pasos de confirmación, tolerantes a errores de tipeo (es/pt).

- Se normaliza el texto: sin tildes, en minúsculas, sin signos y con letras repetidas colapsadas ("simm" → "sim",
  "siii" → "si", "nooo" → "no").
- Se mira solo la primera frase, porque el cliente puede agregar algo después ("sí, es ese").
- Es "sí" si empieza con una afirmación y no aparece una negación. Es "no" si empieza con una negación.
- En cualquier otro caso devuelve None. El controlador NO confirma con None: repite la pregunta con los botones.
"""
from __future__ import annotations

import re

from backend.app.ml.keyword_rules import normalize


def collapse(text: str) -> str:
    """Letras repetidas → una: 'simm' → 'sim', 'esse' → 'ese', 'nooo' → 'no'."""
    return re.sub(r"([a-z])\1+", r"\1", text)


def _words(*phrases: str) -> set[str]:
    return {collapse(normalize(p)) for p in phrases}


# afirmaciones (es / pt), ya colapsadas: "esse" y "ese" quedan iguales
YES = _words("si", "sip", "sep", "sim", "simon", "yes", "ok", "okay", "oki", "okey", "vale", "va", "dale", "claro", "correcto",
             "exacto", "exato", "certo", "afirmativo", "confirmo", "aham", "uhum", "ajam", "eso", "ese", "esa", "isso", "esse", "essa",
             "es ese", "es esa", "es eso", "ese mismo", "esa misma", "ese es", "esa es", "asi es", "eso es", "de acuerdo",
             "e esse", "e essa", "e isso", "isso mesmo", "isso ai", "esse mesmo", "essa mesma", "e sim", "pode ser", "com certeza",
             "por supuesto", "si senor", "sim senhor")
NO = _words("no", "nop", "nope", "nel", "nah", "nao", "negativo", "nunca", "ninguno", "ninguna", "nenhum", "nenhuma",
            "no es", "nao e", "no es ese", "no es esa", "nao e esse", "nao e essa", "para nada", "de jeito nenhum", "nada que ver",
            "otro", "otra", "es otro", "es otra", "era otro", "era otra", "outro", "outra", "e outro", "e outra", "era outro", "era outra")
UNSURE = _words("no se", "nao sei", "no estoy seguro", "no estoy segura", "nao tenho certeza", "no me acuerdo", "nao lembro")
NEGATION = re.compile(r"\b(no|nao|nunca|ningun\w*|nenhum\w*)\b")


def classify_reply(text: str) -> str | None:
    """'yes', 'no' o None (no se reconoce como una respuesta de sí o no)."""
    first = re.split(r"[,.;:!?¡¿\n]| pero | mas ", normalize(text).strip(), maxsplit=1)[0].strip()
    first = collapse(re.sub(r"[^a-z ]", " ", first))
    first = re.sub(r"\s+", " ", first).strip()
    if not first:
        return None
    words = first.split()
    prefixes = [" ".join(words[:n]) for n in range(min(len(words), 4), 0, -1)]   # la frase más larga primero
    if any(p in UNSURE for p in prefixes):
        return None
    if any(p in NO for p in prefixes):
        return "no"
    if any(p in YES for p in prefixes):
        rest = collapse(normalize(text))
        return None if NEGATION.search(rest) else "yes"
    return None
