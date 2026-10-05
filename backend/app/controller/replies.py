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
# "No reconozco…", "no lo hice", "no fui yo": empiezan con "no" pero AFIRMAN algo sobre el cargo; no son la respuesta "no"
# a una pregunta de sí/no (ni a "¿es este el movimiento?" ni a "¿algo más?").
ASSERTION = re.compile(r"^(no|nao) (lo |la |le |me |a |o )?(reconozc|reconhec|hice|fiz|fui|compre|comprei|autoric|autoriz|pague|paguei|realic|realiz)")
NEGATION = re.compile(r"\b(no|nao|nunca|ningun\w*|nenhum\w*)\b")


def classify_reply(text: str) -> str | None:
    """'yes', 'no' o None (no se reconoce como una respuesta de sí o no)."""
    first = re.split(r"[,.;:!?¡¿\n]| pero | mas ", normalize(text).strip(), maxsplit=1)[0].strip()
    first = collapse(re.sub(r"[^a-z ]", " ", first))
    first = re.sub(r"\s+", " ", first).strip()
    if not first:
        return None
    if ASSERTION.search(first):
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


def declines_more(text: str) -> bool:
    """¿Responde "no" a "¿algo más?"? Solo si el mensaje es una negativa corta ("no", "no, gracias", "nada más"); si después
    del "no" viene contenido ("no, pero quiero ver mis movimientos") es una consulta nueva y no cierra la conversación."""
    if classify_reply(text) != "no":
        return False
    words = re.sub(r"[^a-z ]", " ", normalize(text)).split()
    return len(words) <= 5 and "pero" not in words


def asserts_about_shown_charge(text: str) -> bool:
    """En "¿es este el movimiento?": "no reconozco ese cargo", "yo no lo hice", "não fiz essa compra". El cliente habla del
    cargo que tiene en pantalla (no trae monto ni fecha de otro) y afirma que no es suyo: equivale a "sí, es ese".
    Confirmar el movimiento no ejecuta nada: la acción sigue pidiendo su confirmación con botón."""
    norm = normalize(text).strip()
    if re.search(r"\d", norm) or len(norm.split()) > 12:
        return False
    first = collapse(re.sub(r"[^a-z ]", " ", re.split(r"[,.;:!?¡¿\n]", norm, maxsplit=1)[0]))
    first = re.sub(r"^(yo|eu|pero|mas) ", "", re.sub(r"\s+", " ", first).strip())
    return bool(ASSERTION.search(first))


# "no, ese cargo no lo reconozco, yo no fui": empieza con "no" pero lo que sigue habla del cargo en pantalla y dice que no es
# del cliente. No es "no es ese" (no señala otro cargo): es "sí, ese, y no lo reconozco".
ABOUT_THIS = re.compile(r"\b(?:no|nao) (?:lo |la |o |a )?(?:reconozc|reconhec)|\b(?:yo )?no fui(?: yo)?\b|\bnao fui eu\b|\bno lo hice\b|"
                        r"\bnao (?:o |a )?fiz\b|\bno (?:lo |la )?autorice|\bnao autorizei")
NOT_THIS = re.compile(r"\b(otro|otra|outro|outra|ninguno|ninguna|nenhum|nenhuma|no es (?:ese|esa|este|esta)|nao e (?:esse|essa|este|esta)|"
                      r"es el de|e o de|era el de|era o de)\b")


def no_but_not_mine(text: str) -> bool:
    """¿La respuesta a "¿es este el movimiento?" empieza con "no" pero en realidad dice que ESE cargo no es del cliente?
    Sin números (un monto o una fecha apuntan a otro cargo) y sin señalar otro ("es otro", "no es ese")."""
    norm = normalize(text)
    if classify_reply(text) != "no" or re.search(r"\d", norm) or NOT_THIS.search(norm):
        return False
    rest = re.sub(r"^\W*(?:no|nao)\b[\s,.;:!-]*", "", norm)
    return rest != norm and bool(ABOUT_THIS.search(rest))
