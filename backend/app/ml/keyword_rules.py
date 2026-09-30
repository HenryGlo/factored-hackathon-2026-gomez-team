"""Reglas de palabras clave (es/pt) para intención, idioma y extracción básica.

Son el baseline sin LLM: las usa `FakeLLMClient` (tests y demos sin conexión) y, en la fase 3,
`KeywordIntentClassifier`. No pretenden ser buenas; sirven de referencia medible.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from backend.app.dates import normalize

PT_MARKERS = r"\b(nao|voce|cobranca|cartao|reconheco|compra|ola|obrigad[oa]|meu|minha|gastei|quanto|foi|uma|pra|pelo|ontem|semana passada|atendente|estorno|bloquear meu)\b"
ES_MARKERS = r"\b(no|usted|cobro|tarjeta|reconozco|hola|gracias|mi|gaste|cuanto|fue|una|para|ayer|asesor|devolucion)\b"

# (intención, patrón) en orden de prioridad; el primero que coincide es la intención principal
RULES: list[tuple[str, str]] = [
    ("bloquear_tarjeta", r"\b(bloque\w*|congel\w*|cancelar (mi|la|minha|o) (tarjeta|cartao)|me robaron|perdi (mi|la) tarjeta|roubad\w*|perdi (meu|o) cartao)\b"),
    ("pedir_humano", r"\b(humano|persona|asesor|agente humano|hablar con alguien|atendente|pessoa|falar com alguem|ejecutivo)\b"),
    ("estado_reclamo", r"\b(estado de mi reclamo|mi reclamo|el reclamo que|numero de reclamo|status da (minha )?reclamacao|minha reclamacao|meu protocolo|como va mi)\b"),
    ("cobro_indebido", r"\b(dos veces|duplicad\w*|doble cobro|cobraron de mas|cobro de mas|monto (equivocado|incorrecto|distinto)|duas vezes|cobraram a mais|cobranca duplicada|valor errado|me cobraron mas)\b"),
    ("cargo_no_reconocido", r"\b(no reconozco|desconozco|no fui yo|no hice (esa|este|ese)|no lo hice|nao reconheco|desconheco|nao fui eu|nao fiz|cargo que no|cobro que no|cobranca que nao|no autorice|nao autorizei|fraude)\b"),
    ("consulta_movimientos", r"\b(movimientos|ultimos cargos|cuanto gaste|mis compras|mis gastos|extrato|movimentacoes|quanto gastei|minhas compras|meus gastos|ultimas transacoes|historial)\b"),
]
NEGATIVE = r"\b(reconocer a|reconocimiento|reconhecer o|app nueva|aplicacion nueva|app nova)\b"
MANIPULATION = r"\b(ignora|ignore|olvida (tus|las) (instrucciones|reglas)|esquece|system prompt|otro cliente|outro cliente|cliente cli-|cli-[a-z0-9]{6,}|actua como|finge que|aprueba (el|la) (reembolso|devolucion)|modo desarrollador)\b"
OUT_OF_SCOPE_TOPICS = [("credito", r"\b(credito|prestamo|emprestimo)\b"), ("cambio de pin", r"\b(pin|clave|senha)\b"),
                       ("cupo", r"\b(cupo|limite)\b"), ("cuenta", r"\b(abrir (una )?cuenta|abrir (uma )?conta)\b")]
GREETINGS = r"^(hola|ola|buen[oa]s (dias|tardes|noches)|bom dia|boa tarde|boa noite|gracias|obrigad[oa]|ok|hey|oi)[\s!.?]*$"


def detect_language(text: str) -> str:
    t = normalize(text)
    pt, es = len(re.findall(PT_MARKERS, t)), len(re.findall(ES_MARKERS, t))
    if re.search(r"[ãõç]", text.lower()):
        pt += 2
    return "pt" if pt > es else "es"


def classify(text: str) -> dict:
    """Salida con la forma de IntentOutput."""
    t = normalize(text)
    lang = detect_language(text)
    manip = bool(re.search(MANIPULATION, t))
    if not t or re.fullmatch(GREETINGS, t):
        return dict(intent="sin_contenido", otras_intenciones=[], tema=None, idioma=lang, certeza="alta",
                    sospecha_manipulacion=manip, multiples_intenciones=False)
    hits = [] if re.search(NEGATIVE, t) else [name for name, pat in RULES if re.search(pat, t)]
    if not hits:
        topic = next((name for name, pat in OUT_OF_SCOPE_TOPICS if re.search(pat, t)), None)
        return dict(intent="fuera_de_alcance", otras_intenciones=[], tema=topic, idioma=lang,
                    certeza="baja" if topic is None else "alta", sospecha_manipulacion=manip, multiples_intenciones=False)
    main, others = hits[0], [h for h in hits[1:] if h != hits[0]][:3]
    # "no reconozco … dos veces" → cobro_indebido tiene prioridad sobre cargo_no_reconocido solo si no hay negación clara
    return dict(intent=main, otras_intenciones=others, tema=None, idioma=lang, certeza="alta" if len(hits) == 1 else "baja",
                sospecha_manipulacion=manip, multiples_intenciones=len(set(hits)) > 1)


AMOUNT = re.compile(r"(?:\$|us\$|r\$|usd|cop|ars|brl)?\s?(\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)\s*(mil)?", re.I)
APPROX = r"\b(como|unos|unas|cerca de|mas o menos|aproximadamente|uns|umas|mais ou menos|por ahi|alrededor de)\b"
CURRENCY = [("USD", r"\b(dolares|dolar|usd|us\$)\b"), ("BRL", r"\b(reais|real|r\$|brl)\b"), ("COP", r"\bcop\b"),
            ("ARS", r"\bars\b"), ("EUR", r"\b(euros?|eur)\b")]
DATE_HINTS = r"(hoy|hoje|anteayer|anteontem|ayer|ontem|(hace|ha|faz) \w+ (dias?|semanas?|mes(es)?)|(la )?semana pasada|semana passada|esta semana|nesta semana|(el )?mes pasado|mes passado|este mes|neste mes|\d{1,2}/\d{1,2}(/\d{2,4})?|\d{1,2} de \w+( de \d{4})?|(el |la |na |no )?(lunes|martes|miercoles|jueves|viernes|sabado|domingo|segunda|terca|quarta|quinta|sexta)(-feira)?( pasado| passada)?)"
MERCHANT = re.compile(r"\b(?:en|em|no|na|de|del)\s+((?:[A-Z][\w'&*.-]*)(?:\s+[A-Z][\w'&*.-]*){0,3})")


def _amount(raw: str, mil: str | None) -> str | None:
    s = raw
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", s):              # 1.250 o 1,250 → miles
        s = re.sub(r"[.,]", "", s)
    elif re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+[.,]\d{1,2}", s):  # 1.250,50 o 1,250.50
        s = re.sub(r"[.,](?=\d{3})", "", s).replace(",", ".")
    else:
        s = s.replace(",", ".")
    try:
        v = Decimal(s) * (1000 if mil else 1)
    except InvalidOperation:
        return None
    return str(v.quantize(Decimal("0.01"))).removesuffix(".00") if v == v.to_integral() else str(v.quantize(Decimal("0.01")))


def extract(text: str) -> dict:
    """Salida con la forma de ExtractOutput (heurística; el nodo real la hace el LLM)."""
    t = normalize(text)
    date_hint = m.group(0) if (m := re.search(DATE_HINTS, t)) else None
    amount = None
    for m in AMOUNT.finditer(text):
        start = m.start(1)
        if start > 0 and (text[start - 1].isalnum() or text[start - 1] in "-_"):   # parte de un ID o palabra
            continue
        if re.search(r"\d{1,2}/\d{1,2}", text[max(0, start - 3): m.end(1) + 3]):   # parte de una fecha
            continue
        if re.match(r"\s*(de (enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre|janeiro|fevereiro|marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)|dias?|semanas?|veces|vezes|meses)",
                    normalize(text[m.end(1):m.end(1) + 20])):
            continue
        value = _amount(m.group(1), m.group(2))
        if value:
            currency = next((c for c, pat in CURRENCY if re.search(pat, t)), None)
            amount = {"value": value, "currency": currency, "approx": bool(re.search(APPROX, t))}
            break
    merchant = (m.group(1) if (m := MERCHANT.search(text)) else None)
    problema = ("duplicado" if re.search(r"\b(dos veces|duplicad\w*|duas vezes|doble)\b", t)
                else "monto_incorrecto" if re.search(r"\b(de mas|a mais|monto (equivocado|incorrecto)|valor errado)\b", t)
                else "no_reconoce" if re.search(r"\b(no reconozco|nao reconheco|no fui yo|nao fui eu|desconozco)\b", t) else None)
    n = 2 if problema == "duplicado" else None
    card = m.group(0) if (m := re.search(r"\b(credito|debito|terminada en \d{4}|final \d{4})\b", t)) else None
    return {"merchant_hint": merchant, "amount_hint": amount, "date_hint": date_hint, "card_hint": card,
            "n_charges": n, "problema": problema}
