"""Elegir por voz (o por texto) entre lo que el asistente acaba de mostrar, sin tocar la pantalla (modo voz, opción A).

- `pick_shown`: "el primero", "la segunda", "el último", "el de Netflix", "el de 15 dólares" → la candidata o el movimiento
  de la lista que el cliente nombra. Si la referencia es ambigua (dos candidatas de Netflix) devuelve None y el flujo sigue
  como antes (pregunta de nuevo).
- `pick_option`: el cliente dice el nombre de una respuesta rápida ("ver mis movimientos", "una persona", "otro dato").
- Nada de esto confirma una acción: confirmar un reclamo o un bloqueo sigue exigiendo el botón y su token (R4).
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from backend.app.dates import normalize

ORDINALS = {1: r"primer[oa]?|primeir[oa]|1(?:ro|ra|o|a|º|ª|st)?|uno|una|um|uma|first",
            2: r"segund[oa]|2(?:do|da|o|a|º|ª|nd)?|dos|dois|duas|second|two",
            3: r"tercer[oa]?|terceir[oa]|3(?:ro|ra|o|a|º|ª|rd)?|tres|third|three",
            4: r"cuart[oa]|quart[oa]|4(?:to|ta|o|a|º|ª|th)?|cuatro|quatro|fourth|four",
            5: r"quint[oa]|5(?:to|ta|o|a|º|ª|th)?|cinco|fifth|five",
            -1: r"ultim[oa]|last"}
MONTHS = r"\b(january|february|march|april|june|july|august|september|october|november|december|enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre|janeiro|fevereiro|marco|maio|junho|julho|setembro|outubro|novembro|dezembro)\b"
FILLER = {"the", "one", "that", "this", "from", "at", "it", "is", "option", "number", "please", "yes",
          "el", "la", "los", "las", "de", "del", "en", "ese", "esa", "este", "esta", "o", "a", "do", "da", "no", "na", "que", "es", "e",
          "eh", "pues", "opcion", "opcao", "numero", "si", "sim", "cargo", "cobro", "cobranca", "movimiento", "lancamento", "uno", "um"}
STOP = {"de", "del", "la", "el", "en", "y", "e", "da", "do", "das", "dos", "por", "con", "com", "un", "una", "mis", "meus", "minha",
        "the", "my", "to", "a", "of", "and", "with", "see"}


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", normalize(text))


def _amount(text: str) -> Decimal | None:
    m = re.search(r"(\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)", text)
    if not m:
        return None
    raw = m.group(1)
    raw = re.sub(r"[.,](?=\d{3}\b)", "", raw).replace(",", ".")
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def pick_shown(message: str, views: list[dict]) -> str | None:
    """transaction_id de la opción que el cliente nombra, o None. views: [{transaction_id, label, merchant_name, amount}]."""
    if not views:
        return None
    norm = normalize(message)
    words = _words(message)
    if not words or len(words) > 10 or re.search(MONTHS, norm):        # "el primero de junio" es una fecha, no una opción
        return None
    if re.search(r"\b(los|las|os|as|ambos|ambas|todos|todas|both|all)\b", norm):   # "los dos", "todos", "both": varios, no una opción
        return None
    for pos, pat in ORDINALS.items():
        if re.search(rf"\b(?:el|la|o|a|opcion|opcao|numero|the|option|number)?\s*(?:{pat})\b", norm) and (pos == -1 or pos <= len(views)):
            only_ordinal = all(w in FILLER or re.fullmatch(rf"(?:{pat})", w) for w in words)
            if only_ordinal or len(words) <= 4:
                return views[pos - 1 if pos > 0 else -1]["transaction_id"]
    content = {w for w in words if w not in FILLER and len(w) >= 3}
    by_name = [v for v in views if content and content & {w for w in _words(v.get("merchant_name") or v.get("label") or "")
                                                           if len(w) >= 3 and w not in STOP}]
    if len(by_name) == 1:
        return by_name[0]["transaction_id"]
    value = _amount(message)
    if value:
        pool = by_name or views
        by_amount = [v for v in pool if abs(Decimal(str(v["amount"])) - value) <= max(Decimal("0.01"), value * Decimal("0.01"))]
        if len(by_amount) == 1:
            return by_amount[0]["transaction_id"]
    return None


def pick_option(message: str, options: list[dict]) -> dict | None:
    """La acción de la respuesta rápida que el cliente nombra (sin tocarla), o None si no nombra una sola."""
    words = [w for w in _words(message) if w not in STOP]
    if not words or len(words) > 6 or not options:
        return None
    from rapidfuzz import fuzz
    scored = []
    for o in options:
        label = [w for w in _words(o["label"]) if w not in STOP]
        whole = fuzz.ratio(" ".join(words), " ".join(label))
        covered = all(any(fuzz.ratio(w, lw) >= 85 for lw in label) for w in words if len(w) >= 4) and any(len(w) >= 4 for w in words)
        if whole >= 85 or covered:
            scored.append((whole, o))
    if len(scored) == 1 or (len(scored) > 1 and sorted(s for s, _ in scored)[-1] - sorted(s for s, _ in scored)[-2] >= 15):
        return max(scored, key=lambda x: x[0])[1]["action"]
    return None
