"""Reglas de palabras clave (es/pt) para intención, idioma y extracción básica.

Son el baseline sin LLM: las usa `FakeLLMClient` (tests y demos sin conexión) y, en la fase 3,
`KeywordIntentClassifier`. No pretenden ser buenas; sirven de referencia medible.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from backend.app.dates import normalize

PT_MARKERS = (r"\b(nao|voce|cobranca|cartao|reconheco|compra|ola|obrigad[oa]|meu|minha|gastei|quanto|foi|uma|pra|pelo|ontem|semana passada|"
              r"atendente|estorno|bloquear meu|agora|acontece|posso|vai|vou|dinheiro|reclamacao|bloqueado|tempo|demora|seu|sua|"
              r"quero|fazer|preciso|qual|taxa|juros|emprestimo|suas|regras|diga|piada)\b")
ES_MARKERS = (r"\b(no|usted|cobro|tarjeta|reconozco|hola|gracias|mi|gaste|cuanto|fue|una|para|ayer|asesor|devolucion|ahora|pasa|puedo|"
              r"dinero|reclamo|bloqueada|tarda|tiempo|tu|su)\b")

# (intención, patrón) en orden de prioridad; el primero que coincide es la intención principal
RULES: list[tuple[str, str]] = [
    # preguntas sobre el proceso (va primero: "¿qué pasa con mi tarjeta bloqueada?" no es un pedido de bloqueo)
    ("pregunta_proceso", r"\b(devolver\w*|me devuelven|me regresan|cuando me responden|quando (me )?respondem|recuperar (el|mi|o) dinero|vou receber|"
                         r"receber (o dinheiro|de volta)|cuanto (tarda|demora|tiempo)|quanto (tempo|demora)|demora quanto|en cuantos dias|"
                         r"em quantos dias|(y |e )?ahora que (pasa|sigue|hago)|que sigue|proximo paso|o que acontece|e agora|proximos? passos?|"
                         r"que pasa (despues|con mi tarjeta|con (el|un) cargo pendiente)|(cancelar|anular|retirar) (el |mi |a |minha )?(reclamo|reclamacao)|"
                         r"tarjeta bloqueada|cartao bloqueado|desbloque\w*|nueva tarjeta|cartao novo|segunda via|reposicion|"
                         r"como (consulto|veo|reviso|sigo)|onde (vejo|consulto)|como acompanho|me pidieron (mi|la) clave|"
                         r"pediram (minha|a) senha|que significa (revertido|estornado)|how long (does|will) it take|when (will|do) i get (my )?money|will i get (my )?money back|get my money back|what happens (now|next)|what'?s next|next steps?|cancel (the |my )?claim|withdraw (the |my )?claim|blocked card|unblock\w*|new card|replacement card|how (do|can) i (check|track|follow)|where (do|can) i (see|check)|asked for my (password|pin)|what does reversed mean)\b"),
    ("bloquear_tarjeta", r"\b(bloque\w*|congel\w*|cancelar (mi|la|minha|o) (tarjeta|cartao)|me robaron|perdi (mi|la) tarjeta|roubad\w*|perdi (meu|o) cartao|block\w*|freeze\w*|cancel (my|the) card|stolen|lost my card|my card was stolen)\b"),
    ("pedir_humano", r"\b(humano|persona|asesor|agente humano|hablar con alguien|atendente|pessoa|falar com alguem|ejecutivo|human|person|agent|representative|real person|talk to someone|speak to someone)\b"),
    ("estado_reclamo", r"\b(estado de mi reclamo|mi reclamo|el reclamo que|numero de reclamo|status da (minha )?reclamacao|minha reclamacao|meu protocolo|como va mi|status of my claim|my claim|claim status|claim number|how is my claim)\b"),
    ("cobro_indebido", r"\b(dos veces|duplicad\w*|doble cobro|cobraron de mas|cobro de mas|monto (equivocado|incorrecto|distinto)|duas vezes|cobraram a mais|cobranca duplicada|valor errado|me cobraron mas|charged twice|double charge\w*|duplicate\w*|charged (me )?too much|overcharged|wrong amount|charged more)\b"),
    ("cargo_no_reconocido", r"\b(no (lo |la |los |las )?reconozco|desconozco|no fui yo|yo no fui|no hice (esa|este|ese)|no lo hice|que (yo )?no hice|"
                            r"no reconocid\w*|nao reconhecid\w*|nao (o |a )?reconheco|desconheco|nao fui eu|nao fiz|cargo que no|cobro que no|cobranca que nao|no autorice|nao autorizei|"
                            r"fraude|(cobro|cargo|movimiento) (raro|extrano|desconocido)|cobranca (estranha|desconhecida)|"
                            r"(quiero|quero)( sim| si)? reclamar|reclamar (de )?(ese|este|esse|essa|desse|dessa|un|um|uma) (cargo|cobro|cobranca)|(don'?t|do not|didn'?t|did not) recogni[sz]e|unrecogni[sz]ed|wasn'?t me|it was not me|i didn'?t (make|do|buy|authori[sz]e)|i did not (make|do|buy|authori[sz]e)|not mine|unknown charge|strange charge|weird charge|fraud\w*|dispute (this|that|a|the) (charge|transaction))\b"),
    ("consulta_movimientos", r"\b(movimientos|ultimos cargos|cuanto gaste|mis compras|mis gastos|extrato|movimentacoes|quanto gastei|minhas compras|meus gastos|ultimas transacoes|historial|transactions|my purchases|my spending|how much (did i|have i) spen[dt]|recent charges|statement|account activity)\b"),
]
NEGATIVE = r"\b(reconocer a|reconocimiento|reconhecer o|app nueva|aplicacion nueva|app nova)\b"
MANIPULATION = r"\b(ignora|ignore|forget (your|the) (instructions|rules)|you are now|act as|pretend|approve (the|my) refund|developer mode|olvida (tus|las) (instrucciones|reglas)|esquece|system prompt|otro cliente|outro cliente|cliente cli-|cli-[a-z0-9]{6,}|actua como|finge que|aprueba (el|la) (reembolso|devolucion)|modo desarrollador)\b"
OUT_OF_SCOPE_TOPICS = [("credito", r"\b(credito|prestamos?|emprestimos?|loans?|mortgage|credit line)\b"),
                       ("inversiones", r"\b(cdt|cdb|inversion\w*|invertir|investimentos?|investir|invest\w*|stocks?)\b"),
                       ("tasas", r"\b(tasa|taxa) (de interes|de juros|tiene|tem)\b|\bque (tasa|taxa)\b"),
                       ("chiste", r"\b(chistes?|piadas?)\b"), ("cambio de pin", r"\b(pin|clave|senha)\b"),
                       ("cupo", r"\b(cupo|limite)\b"), ("cuenta", r"\b(abrir (una )?cuenta|abrir (uma )?conta)\b")]
# temas que, junto a un pedido de este chat, forman un mensaje mixto ("¿qué tasa tiene un préstamo? y no reconozco un cargo")
MIXED_TOPICS = ("credito", "inversiones", "tasas", "chiste")
GREETINGS = r"^(hello|hi|good (morning|afternoon|evening)|thanks|thank you|hola|ola|buen[oa]s (dias|tardes|noches)|bom dia|boa tarde|boa noite|gracias|obrigad[oa]|ok|hey|oi)[\s!.?]*$"


# --- tolerancia a errores de tipeo (prompt 11): "n oreconocido", "noo reconoscoo", "cargoo"
# Raíces que, pegadas y sin letras repetidas, indican un reclamo por un cargo. Se buscan en el texto SIN espacios.
DISPUTE_STEMS = ("noreconoz", "noreconoc", "noloreconoz", "nolareconoz", "naoreconhec", "desconoz", "desconoc", "desconhec", "nofuiyo",
                 "yonofui", "naofuieu", "nolohice", "nohiceesa", "nohiceese", "naofiz", "noautoric", "naoautoriz",
                 "dontrecogni", "didntrecogni", "donotrecogni", "didnotrecogni", "unrecogni", "wasntme", "itwasnotme", "didntmake",
                 "didnotmake", "didntauthori", "notmine")
# Palabras del dominio de este chat: si el mensaje menciona alguna, NO es "fuera de alcance" por descarte.
BANKING_WORDS = ("cargo", "cargos", "cobro", "cobros", "cobraron", "compra", "compras", "pago", "pagos", "movimiento", "movimientos",
                 "tarjeta", "tarjetas", "reclamo", "reclamos", "transaccion", "debito", "cobranca", "cobrancas", "cobraram", "pagamento",
                 "lancamento", "lancamentos", "cartao", "reclamacao", "transacao", "extrato",
                 "charge", "charges", "charged", "purchase", "purchases", "payment", "payments", "transaction", "transactions",
                 "card", "cards", "claim", "claims", "dispute", "statement", "debit")
DISPUTE_WORDS = ("reconozco", "reconocido", "reconheco", "reconhecido", "desconozco", "desconocido", "desconheco", "desconhecido",
                 "recognize", "recognise", "recognized", "unrecognized")


def squash(text: str) -> str:
    """Texto normalizado, sin letras repetidas y sin espacios: "n oreconocido" y "noo  reconocido" → "noreconocido"."""
    return re.sub(r"([a-z])\1+", r"\1", re.sub(r"[^a-z0-9]", "", normalize(text)))


def _fuzzy_tokens(text: str, vocabulary: tuple[str, ...], cutoff: int = 84) -> bool:
    from rapidfuzz import fuzz, process
    tokens = [w for w in re.findall(r"[a-z]{4,}", normalize(text))]
    return any(process.extractOne(w, vocabulary, scorer=fuzz.ratio, score_cutoff=cutoff) for w in tokens)


def dispute_signal(text: str) -> bool:
    """El mensaje habla de un cargo que el cliente no reconoce, aun con errores de tipeo."""
    t = normalize(text)
    if re.search(NEGATIVE, t):
        return False
    squashed = squash(text)
    folded = re.sub(r"(?<=o)sc(?=o)", "c", squashed.replace("z", "c"))     # "reconosco", "reconozco" → "reconoco"
    if any(stem.replace("z", "c") in folded for stem in DISPUTE_STEMS):
        return True
    return bool(re.search(r"\b(no|nao|n|not|dont|don't|didnt|didn't|never)\b", t)) and _fuzzy_tokens(text, DISPUTE_WORDS)


def mentions_banking(text: str) -> bool:
    """Menciona cargo, cobro, compra, pago, movimiento, tarjeta, reclamo… (con coincidencia aproximada) o un comercio."""
    t = normalize(text)
    return (any(re.search(rf"\b{w}\b", t) for w in BANKING_WORDS) or _fuzzy_tokens(text, BANKING_WORDS, cutoff=86)
            or bool(MERCHANT.search(text)))


def out_of_scope_topic(text: str) -> str | None:
    """Tema que este chat NO atiende, nombrado de forma explícita (préstamo, inversión, PIN, cupo…): alta confianza."""
    t = normalize(text)
    return next((name for name, pat in OUT_OF_SCOPE_TOPICS if re.search(pat, t)), None)


EN_MARKERS = (r"\b(the|i|my|you|your|is|was|it|this|that|charge|charged|card|recognize|recognise|didn'?t|don'?t|wasn'?t|"
              r"not|what|how|please|thanks|thank|hello|hi|want|need|block|claim|transaction|transactions|money|yesterday|"
              r"week|month|ago|from|at|and|of|with|help|someone|person|agent|status|refund|did|have|can|would)\b")


def detect_language(text: str) -> str:
    t = normalize(text)
    pt, es, en = len(re.findall(PT_MARKERS, t)), len(re.findall(ES_MARKERS, t)), len(re.findall(EN_MARKERS, t))
    if re.search(r"[ãõç]", text.lower()):
        pt += 2
    if re.search(r"[ñ¿¡]", text.lower()):
        es += 2
    if en > max(pt, es) and (en >= 2 or pt + es == 0):    # una sola palabra común no basta si hay marcas de es/pt
        return "en"
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
    if not hits and dispute_signal(text):            # "tengo un cargo n oreconocido": error de tipeo, sigue siendo un reclamo
        return dict(intent="cargo_no_reconocido", otras_intenciones=[], tema=None, tema_proceso=None, idioma=lang, certeza="baja",
                    sospecha_manipulacion=manip, multiples_intenciones=False)
    if not hits:
        topic = next((name for name, pat in OUT_OF_SCOPE_TOPICS if re.search(pat, t)), None)
        return dict(intent="fuera_de_alcance", otras_intenciones=[], tema=topic, idioma=lang,
                    certeza="baja" if topic is None else "alta", sospecha_manipulacion=manip, multiples_intenciones=False)
    if "pregunta_proceso" in hits and "?" not in text and any(h in hits for h in ("cargo_no_reconocido", "cobro_indebido")):
        hits = [h for h in hits if h != "pregunta_proceso"]      # "y ahora me aparece un cobro que no hice": no es una pregunta
    if "pregunta_proceso" in hits:      # "¿puedo cancelar mi reclamo?" menciona el reclamo, pero no pide su estado
        hits = [h for h in hits if h != "estado_reclamo"]
        # "tarjeta bloqueada" / "desbloquear" describen un estado: no es un pedido de bloqueo (sí lo es "bloquea", "bloquear")
        if not re.search(r"\b(bloquea|bloquear|bloqueen|bloqueie|congel\w*|me robaron|perdi|roubad\w*)\b", t):
            hits = [h for h in hits if h != "bloquear_tarjeta"]
    main, others = hits[0], [h for h in hits[1:] if h != hits[0]][:3]
    oos = next((name for name, pat in OUT_OF_SCOPE_TOPICS if name in MIXED_TOPICS and re.search(pat, t)), None)
    if oos:
        others = [*others, "fuera_de_alcance"][:3]
        hits = [*hits, "fuera_de_alcance"]
    # "no reconozco … dos veces" → cobro_indebido tiene prioridad sobre cargo_no_reconocido solo si no hay negación clara
    topic = None
    if "pregunta_proceso" in hits:
        from backend.app.knowledge import retrieve
        entry, _ = retrieve(None, text, lang)
        topic = entry.tema if entry else None
    return dict(intent=main, otras_intenciones=others, tema=oos, tema_proceso=topic, idioma=lang,
                certeza="alta" if len(hits) == 1 else "baja", sospecha_manipulacion=manip, multiples_intenciones=len(set(hits)) > 1)


AMOUNT = re.compile(r"(?:\$|us\$|r\$|usd|cop|ars|brl)?\s?(\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)\s*(mil)?", re.I)
APPROX = r"\b(como|unos|unas|cerca de|mas o menos|aproximadamente|uns|umas|mais ou menos|por ahi|alrededor de|about|around|roughly|approximately|approx)\b"
CURRENCY = [("USD", r"\b(dolares|dolar|usd|us\$|dollars?|bucks)\b"), ("BRL", r"\b(reais|real|r\$|brl)\b"), ("COP", r"\bcop\b"),
            ("ARS", r"\bars\b"), ("EUR", r"\b(euros?|eur)\b")]
DATE_HINTS = r"(today|yesterday|day before yesterday|\w+ (days?|weeks?|months?) ago|last (week|month|monday|tuesday|wednesday|thursday|friday|saturday|sunday)|this (week|month)|(on )?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)|(january|february|march|april|may|june|july|august|september|october|november|december) \d{1,2}(st|nd|rd|th)?|\d{1,2}(st|nd|rd|th)? (of )?(january|february|march|april|may|june|july|august|september|october|november|december)|hoy|hoje|anteayer|anteontem|ayer|ontem|(hace|ha|faz) \w+ (dias?|semanas?|mes(es)?)|(la )?semana pasada|semana passada|esta semana|nesta semana|(el )?mes pasado|mes passado|este mes|neste mes|\d{1,2}/\d{1,2}(/\d{2,4})?|\d{1,2} de \w+( de \d{4})?|(el |la |na |no )?(lunes|martes|miercoles|jueves|viernes|sabado|domingo|segunda|terca|quarta|quinta|sexta)(-feira)?( pasado| passada)?)"
# tipos de comercio que el léxico de alias del ranker sabe resolver (ml/ranker/merchant_aliases.json); solo tras una preposición
PLACE = r"\b(?:en (?:el|la|un|una)|no|na|num|numa)\s+(super|farmacia|taxi|mercado|restaurante|gasolinera|cine)\b|\b(?:at|in) (?:a|the) (supermarket|pharmacy|taxi|market|restaurant|gas station|cinema)\b"
MERCHANT = re.compile(r"\b(?:en|em|no|na|de|del|at|from|on|in)\s+((?:[A-Z][\w'&*.-]*)(?:\s+[A-Z][\w'&*.-]*){0,3})")


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


# el cliente AFIRMA que no hizo el cargo (R2b), no solo que no lo reconoce
ASSERTS_NOT_DONE = (r"\b(yo no (lo |la )?hice|no (lo |la )?hice yo|no lo hice|no la hice|no fui yo|yo no fui|nunca (compre|he comprado|estuve|fui)|"
                    r"no (hice|realice|autorice) (esa|ese|esta|este|ninguna|ningun)\w*|ni siquiera tengo|no tengo (carro|auto|coche)|"
                    r"eu nao fiz|nao fiz (essa|esse|isso)|nao fui eu|nunca (comprei|fui)|nem tenho|nao autorizei|"
                    r"i didn'?t (make|do|buy|authori[sz]e)|i did not (make|do|buy|authori[sz]e)|wasn'?t me|it was not me|i never (bought|made|went))\b")
NUMBER_WORDS = {"dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "duas": 2, "dois": 2, "quatro": 4, "2": 2, "3": 3, "4": 4, "5": 5}
GROUP = (r"\b(los|las|os|as|ultimos|ultimas|esos|esas|esses|essas)\s+(?P<n>dos|tres|cuatro|cinco|dois|duas|quatro|[2-5])\b"
         r"|\b(?P<n2>dos|tres|cuatro|cinco|dois|duas|quatro|[2-5])\s+(cargos|cobros|cobrancas|compras|movimientos|ultimos)\b")


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
    if merchant:                                   # "en Tienda X. Ese no lo reconozco": el comercio termina con la oración
        merchant = re.split(r"[.!?;,]\s", merchant)[0].rstrip(".!?;,")
    elif m := re.search(PLACE, normalize(text)):   # referencia indirecta por tipo de comercio: "en un taxi", "na farmácia"
        merchant = m.group(1) or m.group(2)
    problema = ("duplicado" if re.search(r"\b(dos veces|duplicad\w*|duas vezes|doble|twice|duplicate\w*|double)\b", t)
                else "monto_incorrecto" if re.search(r"\b(de mas|a mais|monto (equivocado|incorrecto)|valor errado|too much|overcharged|wrong amount|charged more)\b", t)
                else "no_reconoce" if re.search(r"\b(no reconozco|nao reconheco|no fui yo|nao fui eu|desconozco|(don'?t|do not|didn'?t|did not) recogni[sz]e|wasn'?t me|unrecogni[sz]ed)\b", t) else None)
    n = 2 if problema == "duplicado" else None
    if (m := re.search(GROUP, t)):
        n = n or NUMBER_WORDS.get(m.group("n") or m.group("n2"))
    seleccion = ("mas_recientes" if re.search(r"\b(mas recientes|ultimos|ultimas)\b", t) and n else
                 "mas_antiguos" if re.search(r"\b(mas antiguos|mas viejos|mais antig\w+)\b", t) and n else
                 "todos" if re.search(r"\b(todos|todas|ambos|ambas)\b", t) else None)
    card = m.group(0) if (m := re.search(r"\b(credito|debito|terminada en \d{4}|final \d{4})\b", t)) else None
    return {"merchant_hint": merchant, "amount_hint": amount, "date_hint": date_hint, "card_hint": card,
            "n_charges": n, "problema": problema, "afirma_no_haberlo_hecho": bool(re.search(ASSERTS_NOT_DONE, t)),
            "seleccion": seleccion}
