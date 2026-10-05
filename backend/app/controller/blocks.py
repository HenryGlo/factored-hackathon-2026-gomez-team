"""Bloques de UI (docs/api-contract.md) y textos que escribe el código, en español y portugués.

Montos siempre como string decimal con 2 decimales; nunca float. Los textos que el código
escribe no dicen "aprobado" ni "reembolsado" (R5).
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

MSG = {
    "es": {
        "greeting": "Hola, ¿en qué te ayudo? Puedo ayudarte con un cargo que no reconoces, un cobro mal hecho, tus movimientos, el estado de un reclamo o bloquear tu tarjeta.",
        "sin_contenido": "Cuéntame en qué te ayudo: por ejemplo, un cargo que no reconoces o bloquear tu tarjeta.",
        "out_of_scope": "Por este canal puedo ayudarte con cargos no reconocidos o mal cobrados, tus movimientos, reclamos y bloqueo de tarjeta. Para {tema}, usa los canales del banco.",
        "out_of_scope_generic": "Por este canal puedo ayudarte con cargos no reconocidos o mal cobrados, tus movimientos, reclamos y bloqueo de tarjeta.",
        "no_candidates": "No encontré cargos que coincidan en los últimos {dias} días. ¿Puedes darme el monto, la fecha o el comercio?",
        "ask_more": "Entiendo. ¿Me das algún dato más del cargo (monto, fecha o comercio)?",
        "duplicate_pick": "Encontré dos cargos iguales. ¿Cuál de los dos quieres reclamar?",
        "no_duplicate": "No encontré dos cargos iguales cercanos. Te muestro los más parecidos:",
        "confirm_tx": "¿Es este el cargo al que te refieres?",
        "no_refund": "Puedo registrar un reclamo para que el banco lo revise, pero no puedo aprobar devoluciones.",
        "handoff": "Tu caso pasó a una persona del banco con el número {handoff_id}. Te contactarán por los canales habituales.",
        "handoff_fraud": "Por seguridad, tu caso pasó al equipo de fraude con el número {handoff_id}.",
        "recommend_lock": "Te recomendamos bloquear tu tarjeta mientras revisan el caso.",
        "offer_lock": "Si quieres, también puedo bloquear tu tarjeta por precaución.",
        "no_cards": "No encontré tarjetas activas asociadas a tu cuenta.",
        "pick_card": "Tienes varias tarjetas. ¿Cuál quieres bloquear?",
        "card_already_blocked": "Esa tarjeta ya está bloqueada.",
        "offer_replacement": "¿Quieres que una persona del banco gestione la reposición de tu tarjeta?",
        "continue_other": "Listo con eso. ¿Seguimos con lo otro que mencionaste?",
        "cancelled": "De acuerdo, no hice ningún cambio.",
        "recognized": "Perfecto, entonces no hace falta un reclamo. No hice ningún cambio.",
        "closed": "Esta conversación ya terminó. Inicia una nueva para otra consulta.",
        "closed_idle": "Esta conversación se cerró por inactividad. Inicia una nueva para seguir.",
        "anything_else": "¿Hay algo más en lo que te pueda ayudar?",
        "thanks": "¡Con gusto! ¿Te ayudo con algo más?",
        "oos_follow": "¿Te ayudo con algo de tus movimientos o reclamos?",
        "bank_home": "Ir a la página inicial del banco",
        "ask_details": "Claro, te ayudo. ¿Me das algún dato del cargo: el monto, el comercio o la fecha aproximada?",
        "ask_details_again": "Para buscarlo necesito al menos un dato: el monto, el comercio o la fecha aproximada.",
        "movements_pick": "Estos son tus últimos movimientos. ¿Cuál no reconoces?",
        "no_match": "No encontré cargos {criterio} en tus movimientos hasta el {fecha}. Puede aparecer con otro nombre o no haberse registrado todavía.",
        "no_match_other": "No encontré otros cargos {criterio} en tus movimientos hasta el {fecha}. Puede aparecer con otro nombre o no haberse registrado todavía.",
        "found": "Encontré {n} cargos {criterio}. ¿Cuál de ellos es?",
        "crit_merchant": "de {v}", "crit_amount": "de {v}", "crit_amount_approx": "de cerca de {v}", "crit_date": "del {v}",
        "crit_date_range": "entre el {a} y el {b}", "crit_generic": "que coinciden con lo que me dijiste", "crit_and": " y ",
        "qr_other_detail": "Darte otro dato", "qr_movements": "Ver mis últimos movimientos",
        "topic_cargo_no_reconocido": "No reconozco un cargo", "topic_consulta_movimientos": "Ver mis movimientos",
        "topic_estado_reclamo": "Estado de mi reclamo", "topic_bloquear_tarjeta": "Bloquear mi tarjeta",
        "qr_more": "Sí, otra consulta",
        "qr_done": "No, gracias",
        "new_request": "Claro, cuéntame qué necesitas.",
        "goodbye": "Gracias por escribirnos. Que tengas un buen día.",
        "pending_unrecognized": "Este cargo sigue pendiente, así que todavía no se puede abrir el reclamo formal: se podrá abrir cuando el cargo se confirme. Como nos dices que no lo hiciste, ya pasé el caso al equipo de fraude ({handoff_id}) para que lo revise.",
        "handoff_pending_fraud": "El equipo de fraude ya tiene tu caso ({handoff_id}). Te contactarán por los canales del banco.",
        "multi_pick": "Encontré estos cargos. Elige los que no reconoces (puedes elegir varios) o «Todos estos».",
        "multi_confirm_head": "Voy a registrar un reclamo por cada uno de estos {n} cargos:",
        "multi_confirm_tail": "No es una devolución: el banco revisará cada caso. ¿Confirmas?",
        "multi_done": "Registré {n} reclamos, uno por cargo:",
        "multi_done_tail": "El banco los revisará; registrar un reclamo no es una devolución.",
        "multi_partial": "No pude verificar todos los reclamos. Te paso con una persona para revisarlo.",
        "multi_all": "Todos estos",
        "faq_none": "No tengo una respuesta confirmada para eso. Si quieres, te paso con una persona que puede ayudarte.",
        "qr_human": "Hablar con una persona",
        "confirm_repeat": "No estoy seguro de haberte entendido. ¿Es este el movimiento? Responde sí o no, o usa los botones.",
        "use_buttons": "Para seguir, usa el botón Confirmar o Cancelar.",
        "confirm_again": "Volviendo a tu cargo: ¿es este el movimiento? Responde sí o no, o usa los botones.",
        "lock_declined_escalated": "De acuerdo, no bloqueé la tarjeta. Tu caso sigue con el equipo que lo va a revisar.",
        "cases_none": "No tienes reclamos registrados por este canal.",
        "cases_list": "Estos son tus reclamos:",
        "movements": "Encontré {n} movimientos entre el {desde} y el {hasta}.",
        "movements_none": "No encontré movimientos entre el {desde} y el {hasta} con esos filtros.",
        "tool_failed": "No pude completar la operación por un problema técnico. No se hizo ningún cambio.",
        "not_verified": "No pude confirmar que la operación quedara registrada, así que no la doy por hecha.",
        "invalid_confirmation": "La confirmación ya no es válida (venció, ya se usó o corresponde a otra sesión). Revisa y confirma de nuevo.",
        "manipulation": "Solo puedo consultar datos de tu propia cuenta.",
        "exhausted": "No logré identificar el cargo con la información disponible.",
    },
    "pt": {
        "greeting": "Olá! Como posso ajudar? Posso ajudar com uma cobrança que você não reconhece, uma cobrança errada, seus lançamentos, o status de uma reclamação ou bloquear o seu cartão.",
        "sin_contenido": "Conte como posso ajudar: por exemplo, uma cobrança que você não reconhece ou bloquear o seu cartão.",
        "out_of_scope": "Por este canal posso ajudar com cobranças não reconhecidas ou erradas, lançamentos, reclamações e bloqueio de cartão. Para {tema}, use os canais do banco.",
        "out_of_scope_generic": "Por este canal posso ajudar com cobranças não reconhecidas ou erradas, lançamentos, reclamações e bloqueio de cartão.",
        "no_candidates": "Não encontrei cobranças que coincidam nos últimos {dias} dias. Pode me dizer o valor, a data ou o estabelecimento?",
        "ask_more": "Entendi. Pode me dar mais algum dado da cobrança (valor, data ou estabelecimento)?",
        "duplicate_pick": "Encontrei duas cobranças iguais. Qual das duas você quer contestar?",
        "no_duplicate": "Não encontrei duas cobranças iguais próximas. Estas são as mais parecidas:",
        "confirm_tx": "É esta a cobrança a que você se refere?",
        "no_refund": "Posso registrar uma reclamação para o banco analisar, mas não posso aprovar devoluções.",
        "handoff": "Seu caso foi encaminhado para uma pessoa do banco com o número {handoff_id}. Entrarão em contato pelos canais habituais.",
        "handoff_fraud": "Por segurança, seu caso foi encaminhado para a equipe de fraude com o número {handoff_id}.",
        "recommend_lock": "Recomendamos bloquear o seu cartão enquanto o caso é analisado.",
        "offer_lock": "Se quiser, também posso bloquear o seu cartão por precaução.",
        "no_cards": "Não encontrei cartões ativos associados à sua conta.",
        "pick_card": "Você tem vários cartões. Qual deseja bloquear?",
        "card_already_blocked": "Esse cartão já está bloqueado.",
        "offer_replacement": "Quer que uma pessoa do banco cuide da reposição do seu cartão?",
        "continue_other": "Pronto. Vamos seguir com o outro assunto que você mencionou?",
        "cancelled": "Tudo bem, não fiz nenhuma alteração.",
        "recognized": "Perfeito, então não é preciso reclamar. Não fiz nenhuma alteração.",
        "closed": "Esta conversa já terminou. Inicie uma nova para outra solicitação.",
        "closed_idle": "Esta conversa foi encerrada por inatividade. Inicie uma nova para continuar.",
        "anything_else": "Posso ajudar com mais alguma coisa?",
        "thanks": "De nada! Posso ajudar com mais alguma coisa?",
        "oos_follow": "Posso ajudar com algo dos seus lançamentos ou reclamações?",
        "bank_home": "Ir para a página inicial do banco",
        "ask_details": "Claro, eu ajudo. Você pode me dar algum dado da cobrança: o valor, a loja ou a data aproximada?",
        "ask_details_again": "Para procurar preciso de pelo menos um dado: o valor, a loja ou a data aproximada.",
        "movements_pick": "Estes são seus últimos lançamentos. Qual você não reconhece?",
        "no_match": "Não encontrei cobranças {criterio} nos seus lançamentos até {fecha}. Ela pode aparecer com outro nome ou ainda não ter sido registrada.",
        "no_match_other": "Não encontrei outras cobranças {criterio} nos seus lançamentos até {fecha}. Ela pode aparecer com outro nome ou ainda não ter sido registrada.",
        "found": "Encontrei {n} cobranças {criterio}. Qual delas é?",
        "crit_merchant": "de {v}", "crit_amount": "de {v}", "crit_amount_approx": "de cerca de {v}", "crit_date": "de {v}",
        "crit_date_range": "entre {a} e {b}", "crit_generic": "que coincidem com o que você me disse", "crit_and": " e ",
        "qr_other_detail": "Dar outro dado", "qr_movements": "Ver meus últimos lançamentos",
        "topic_cargo_no_reconocido": "Não reconheço uma cobrança", "topic_consulta_movimientos": "Ver meus lançamentos",
        "topic_estado_reclamo": "Status da minha reclamação", "topic_bloquear_tarjeta": "Bloquear meu cartão",
        "qr_more": "Sim, outra solicitação",
        "qr_done": "Não, obrigado",
        "new_request": "Claro, me conte do que você precisa.",
        "goodbye": "Obrigado por falar com a gente. Tenha um ótimo dia.",
        "pending_unrecognized": "Esta cobrança ainda está pendente, então ainda não dá para abrir a reclamação formal: ela poderá ser aberta quando a cobrança for confirmada. Como você diz que não fez essa compra, já passei o caso para a equipe de fraude ({handoff_id}).",
        "handoff_pending_fraud": "A equipe de fraude já está com o seu caso ({handoff_id}). Eles vão entrar em contato pelos canais do banco.",
        "multi_pick": "Encontrei estas cobranças. Escolha as que você não reconhece (pode escolher várias) ou «Todas estas».",
        "multi_confirm_head": "Vou registrar uma reclamação para cada uma destas {n} cobranças:",
        "multi_confirm_tail": "Não é uma devolução: o banco vai analisar cada caso. Você confirma?",
        "multi_done": "Registrei {n} reclamações, uma por cobrança:",
        "multi_done_tail": "O banco vai analisá-las; registrar uma reclamação não é uma devolução.",
        "multi_partial": "Não consegui verificar todas as reclamações. Vou passar você para uma pessoa revisar.",
        "multi_all": "Todas estas",
        "faq_none": "Não tenho uma resposta confirmada para isso. Se quiser, passo você para uma pessoa que pode ajudar.",
        "qr_human": "Falar com uma pessoa",
        "confirm_repeat": "Não tenho certeza se entendi. É esta a movimentação? Responda sim ou não, ou use os botões.",
        "use_buttons": "Para continuar, use o botão Confirmar ou Cancelar.",
        "confirm_again": "Voltando à sua cobrança: é esta a movimentação? Responda sim ou não, ou use os botões.",
        "lock_declined_escalated": "Tudo bem, não bloqueei o cartão. O seu caso continua com a equipe que vai analisá-lo.",
        "cases_none": "Você não tem reclamações registradas por este canal.",
        "cases_list": "Estas são as suas reclamações:",
        "movements": "Encontrei {n} lançamentos entre {desde} e {hasta}.",
        "movements_none": "Não encontrei lançamentos entre {desde} e {hasta} com esses filtros.",
        "tool_failed": "Não consegui concluir a operação por um problema técnico. Nenhuma alteração foi feita.",
        "not_verified": "Não consegui confirmar que a operação foi registrada, então não a dou como concluída.",
        "invalid_confirmation": "A confirmação não é mais válida (venceu, já foi usada ou é de outra sessão). Revise e confirme de novo.",
        "manipulation": "Só posso consultar dados da sua própria conta.",
        "exhausted": "Não consegui identificar a cobrança com as informações disponíveis.",
    },
}
DISCLAIMER = {"es": "Registrar un reclamo no es una devolución: el banco revisará el caso.",
              "pt": "Registrar uma reclamação não é uma devolução: o banco vai analisar o caso."}
TYPE_LABEL = {"es": {"Withdrawal": "Retiro en efectivo", "Payment": "Pago", "Purchase": "Compra", "Deposit": "Depósito",
                     "Transfer": "Transferencia", "Adjustment": "Ajuste"},
              "pt": {"Withdrawal": "Saque", "Payment": "Pagamento", "Purchase": "Compra", "Deposit": "Depósito",
                     "Transfer": "Transferência", "Adjustment": "Ajuste"}}
CATEGORY_LABEL = {"es": {"Food": "Alimentación", "Transport": "Transporte", "Services": "Servicios", "Entertainment": "Entretenimiento",
                         "Health": "Salud", "Other": "Otros"},
                  "pt": {"Food": "Alimentação", "Transport": "Transporte", "Services": "Serviços", "Entertainment": "Entretenimento",
                         "Health": "Saúde", "Other": "Outros"}}


def tx_label(tx: dict, lang: str) -> str:
    """Comercio si existe; si no, categoría o tipo, traducidos."""
    if tx.get("merchant_name"):
        return tx["merchant_name"]
    if tx.get("transaction_category"):
        ttype = str(tx.get("transaction_type") or "")
        return f"{TYPE_LABEL[lang].get(ttype, 'Pago')} · {CATEGORY_LABEL[lang].get(tx['transaction_category'], tx['transaction_category'])}"
    ttype = str(tx.get("transaction_type") or "")
    return TYPE_LABEL[lang].get(ttype, ttype)


PICK = {"es": "Encontré {n} cargos parecidos. ¿Cuál de ellos es?", "pt": "Encontrei {n} cobranças parecidas. Qual delas é?"}


def short_ref(internal_id: str | None) -> str:
    """Referencia corta y legible para el cliente (RCL-1A2B3C para reclamos, ATN-… para atenciones). El ID interno completo
    sigue en la traza, en la consola y en los campos *_id de los bloques."""
    if not internal_id:
        return ""
    prefix = {"case": "RCL", "hof": "ATN"}.get(internal_id.split("_", 1)[0], "REF")
    return f"{prefix}-{internal_id[-6:].upper()}"


def tx_line(t: dict, lang: str) -> str:
    return f"{tx_label(t, lang)} · {fmt_money(t['amount'], t['currency'], lang)} · {fmt_date(t['transaction_date'], lang)}"


# Textos aprobados con VARIANTES (plantillas, sin LLM): el controlador elige una distinta de la anterior, para no repetir.
VARIANTS: dict[str, dict[str, list[str]]] = {
    "es": {
        "greeting_short": ["¡Hola! ¿En qué te puedo ayudar?", "¡Hola de nuevo! Cuéntame, ¿qué necesitas?", "Aquí estoy. ¿Con qué te ayudo?"],
        "how_are_you": ["¡Muy bien, gracias por preguntar! ¿En qué te ayudo hoy?", "¡Todo bien por aquí, gracias! ¿Qué necesitas?",
                        "¡Bien, gracias! Cuéntame, ¿en qué te puedo ayudar?"],
        "pick_topic": ["Elige una opción o cuéntame con tus palabras qué necesitas.", "¿Con cuál de estas opciones te ayudo?",
                       "Puedo ayudarte con cualquiera de estas opciones."],
        "retry": ["Perdona, no logré entenderte. ", "Disculpa, sigo sin entender. ", "Lo intento de nuevo. "],
    },
    "pt": {
        "greeting_short": ["Olá! Como posso ajudar?", "Olá de novo! Conte, do que você precisa?", "Estou aqui. Com o que posso ajudar?"],
        "how_are_you": ["Tudo bem, obrigado por perguntar! Como posso ajudar hoje?", "Tudo ótimo por aqui, obrigado! Do que você precisa?",
                        "Tudo bem, obrigado! Conte, como posso ajudar?"],
        "pick_topic": ["Escolha uma opção ou conte com suas palavras do que você precisa.", "Com qual destas opções posso ajudar?",
                       "Posso ajudar com qualquer uma destas opções."],
        "retry": ["Desculpe, não consegui entender. ", "Desculpe, continuo sem entender. ", "Vou tentar de novo. "],
    },
}
TOPICS = ("cargo_no_reconocido", "consulta_movimientos", "estado_reclamo", "bloquear_tarjeta")


def detail_replies(lang: str, other_detail: bool = False) -> dict:
    """Respuestas rápidas cuando falta un dato del cargo o la búsqueda no encontró nada: dar otro dato (solo tras una
    búsqueda sin coincidencias), ver los últimos movimientos o hablar con una persona."""
    options = [{"label": t(lang, "qr_movements"), "action": {"type": "start_topic", "topic": "consulta_movimientos"}},
               {"label": t(lang, "qr_human"), "action": {"type": "request_human"}}]
    if other_detail:
        options.insert(0, {"label": t(lang, "qr_other_detail"), "action": {"type": "start_topic", "topic": "cargo_no_reconocido"}})
    return {"type": "quick_replies", "options": options}


def variants(lang: str, key: str) -> list[str]:
    return VARIANTS.get(lang, VARIANTS["es"])[key]


def topic_replies(lang: str) -> dict:
    """Respuestas rápidas con las opciones principales (cuando el cliente escribe dos veces sin contenido)."""
    return {"type": "quick_replies", "options": [
        *({"label": t(lang, f"topic_{topic}"), "action": {"type": "start_topic", "topic": topic}} for topic in TOPICS),
        {"label": t(lang, "qr_human"), "action": {"type": "request_human"}}]}


def quick_replies(lang: str) -> dict:
    """Respuestas rápidas tras cerrar un flujo: seguir con otra consulta o terminar."""
    return {"type": "quick_replies", "options": [
        {"label": t(lang, "qr_more"), "action": {"type": "new_request"}},
        {"label": t(lang, "qr_done"), "action": {"type": "end_conversation"}}]}


def multi_confirm_text(txs: list[dict], lang: str) -> str:
    return "\n".join([t(lang, "multi_confirm_head", n=len(txs)), *[f"• {tx_line(x, lang)}" for x in txs], t(lang, "multi_confirm_tail")])


def pick_text(txs: list[dict], lang: str) -> str:
    """Plantilla de aclaración para elegir entre candidatas: comercio · monto · fecha de cada una + "¿cuál de ellos?"."""
    # la lista (comercio, monto, fecha) va solo en el bloque candidate_list; el texto no la repite
    return PICK.get(lang, PICK["es"]).format(n=len(txs))


CARD_LABEL = {"es": {"Tarjeta Crédito": "crédito", "Tarjeta Débito": "débito"},
              "pt": {"Tarjeta Crédito": "crédito", "Tarjeta Débito": "débito"}}


def t(lang: str, key: str, **kw) -> str:
    return MSG.get(lang, MSG["es"])[key].format(**kw)


def money(amount) -> str:
    return str(Decimal(str(amount)).quantize(Decimal("0.01")))


def fmt_money(amount, currency: str, lang: str) -> str:
    """'1.250,50 COP' en es y pt (formato latino); '1,250.50 COP' en inglés."""
    s = f"{Decimal(str(amount)).quantize(Decimal('0.01')):,.2f}"
    if lang != "en":
        s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s} {currency}"


MONTHS = {"es": ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sept", "oct", "nov", "dic"),
          "pt": ("jan.", "fev.", "mar.", "abr.", "mai.", "jun.", "jul.", "ago.", "set.", "out.", "nov.", "dez.")}
# estado del movimiento, igual en todos los bloques y textos
STATUS_DISPLAY = {"es": {"Approved": "Aprobado", "Pending": "Pendiente", "Reversed": "Revertido", "Declined": "Rechazado"},
                  "pt": {"Approved": "Aprovado", "Pending": "Pendente", "Reversed": "Revertido", "Declined": "Recusado"}}


def fmt_date(d, lang: str) -> str:
    """'8 jun 2026' (es) / '8 jun. 2026' (pt): el mismo formato en bloques y textos."""
    d = d.date() if isinstance(d, datetime) else d
    if lang == "en":
        return f"{MONTHS['en'][d.month - 1]} {d.day}, {d.year}"          # 'Jun 8, 2026'
    return f"{d.day} {MONTHS.get(lang, MONTHS['es'])[d.month - 1]} {d.year}"


def status_label(status: str | None, lang: str) -> str:
    return STATUS_DISPLAY.get(lang, STATUS_DISPLAY["es"]).get(status or "", status or "")


def tx_view(tx: dict[str, Any], rank: int | None = None, lang: str = "es") -> dict:
    """Movimiento del propio cliente para la UI (sin fraud_score, coordenadas ni is_fraud).
    merchant_name es el comercio real o null; label es lo que se muestra (traducido)."""
    v = {"transaction_id": tx["transaction_id"], "date": tx["transaction_date"].isoformat(), "amount": money(tx["amount"]),
         "currency": tx["currency"], "merchant_name": tx.get("merchant_name"), "label": tx_label(tx, lang),
         "channel": tx.get("channel"), "type": tx.get("transaction_type"), "status": tx["transaction_status"],
         # ya formateados para mostrar (mismo formato que los textos)
         "amount_label": fmt_money(tx["amount"], tx["currency"], lang), "date_label": fmt_date(tx["transaction_date"], lang),
         "status_label": status_label(tx["transaction_status"], lang)}
    if rank is not None:
        v["rank"] = rank
    return v


def text_block(text: str) -> dict:
    return {"type": "text", "text": text}


def notice(code: str, text: str, level: str = "info") -> dict:
    return {"type": "notice", "level": level, "code": code, "text": text}


def error(code: str, message: str, retryable: bool = False) -> dict:
    return {"type": "error", "code": code, "message": message, "retryable": retryable}


# ---------------------------------------------------------------- inglés (2026-10-05): tercer idioma, para todo
# Mismas claves y marcadores que es/pt (lo comprueba backend/tests/test_english.py). Los textos del código no prometen
# devoluciones ni dicen "refunded"/"approved" fuera de la etiqueta de estado (R5).
MSG["en"] = {'greeting': "Hi, how can I help? I can help with a charge you don't recognize, a wrong charge, your transactions, the status of a claim or blocking "
             'your card.',
 'sin_contenido': "Tell me how I can help: for example, a charge you don't recognize or blocking your card.",
 'out_of_scope': "Here I can help with unrecognized or wrong charges, your transactions, claims and card blocking. For {tema}, please use the bank's "
                 'other channels.',
 'out_of_scope_generic': 'Here I can help with unrecognized or wrong charges, your transactions, claims and card blocking.',
 'no_candidates': "I didn't find matching charges in the last {dias} days. Can you give me the amount, the date or the merchant?",
 'ask_more': 'Got it. Can you give me another detail of the charge (amount, date or merchant)?',
 'duplicate_pick': 'I found two identical charges. Which one do you want to dispute?',
 'no_duplicate': "I didn't find two identical charges close together. Here are the most similar ones:",
 'confirm_tx': 'Is this the charge you mean?',
 'no_refund': "I can file a claim so the bank reviews it, but I can't decide on giving money back.",
 'handoff': 'Your case was passed to a person at the bank with number {handoff_id}. They will contact you through the usual channels.',
 'handoff_fraud': 'For your security, your case was passed to the fraud team with number {handoff_id}.',
 'recommend_lock': 'We recommend blocking your card while the case is reviewed.',
 'offer_lock': 'If you want, I can also block your card as a precaution.',
 'no_cards': "I didn't find any active cards linked to your account.",
 'pick_card': 'You have several cards. Which one do you want to block?',
 'card_already_blocked': 'That card is already blocked.',
 'offer_replacement': 'Would you like a person at the bank to arrange a replacement card?',
 'continue_other': 'Done with that. Shall we continue with the other thing you mentioned?',
 'cancelled': "All right, I didn't change anything.",
 'recognized': "Great, then there's no need for a claim. I didn't change anything.",
 'closed': 'This conversation has ended. Start a new one for another question.',
 'closed_idle': 'This conversation was closed due to inactivity. Start a new one to continue.',
 'anything_else': 'Is there anything else I can help you with?',
 'thanks': "You're welcome! Can I help with anything else?",
 'oos_follow': 'Can I help with your transactions or claims?',
 'bank_home': "Go to the bank's home page",
 'ask_details': 'Sure, I can help. Can you give me a detail of the charge: the amount, the merchant or the approximate date?',
 'ask_details_again': 'To look for it I need at least one detail: the amount, the merchant or the approximate date.',
 'movements_pick': "These are your latest transactions. Which one don't you recognize?",
 'no_match': "I didn't find charges {criterio} in your transactions up to {fecha}. It may appear under another name or not be posted yet.",
 'no_match_other': "I didn't find other charges {criterio} in your transactions up to {fecha}. It may appear under another name or not be posted "
                   'yet.',
 'found': 'I found {n} charges {criterio}. Which one is it?',
 'crit_merchant': 'from {v}',
 'crit_amount': 'of {v}',
 'crit_amount_approx': 'of about {v}',
 'crit_date': 'on {v}',
 'crit_date_range': 'between {a} and {b}',
 'crit_generic': 'that match what you told me',
 'crit_and': ' and ',
 'qr_other_detail': 'Give another detail',
 'qr_movements': 'See my latest transactions',
 'topic_cargo_no_reconocido': "I don't recognize a charge",
 'topic_consulta_movimientos': 'See my transactions',
 'topic_estado_reclamo': 'Status of my claim',
 'topic_bloquear_tarjeta': 'Block my card',
 'qr_more': 'Yes, something else',
 'qr_done': 'No, thanks',
 'new_request': 'Sure, tell me what you need.',
 'goodbye': 'Thanks for writing to us. Have a good day.',
 'pending_unrecognized': "This charge is still pending, so the formal claim can't be filed yet: it can be filed once the charge is posted. Since you "
                         "tell us you didn't make it, I've already passed the case to the fraud team ({handoff_id}) for review.",
 'handoff_pending_fraud': "The fraud team already has your case ({handoff_id}). They will contact you through the bank's channels.",
 'multi_pick': "I found these charges. Choose the ones you don't recognize (you can choose several) or «All of these».",
 'multi_confirm_head': "I'm going to file a claim for each of these {n} charges:",
 'multi_confirm_tail': 'This is not giving money back: the bank will review each case. Do you confirm?',
 'multi_done': 'I filed {n} claims, one per charge:',
 'multi_done_tail': 'The bank will review them; filing a claim does not mean you get the money back.',
 'multi_partial': "I couldn't verify all the claims. I'm passing you to a person to review it.",
 'multi_all': 'All of these',
 'faq_none': "I don't have a confirmed answer for that. If you want, I can pass you to a person who can help.",
 'qr_human': 'Talk to a person',
 'confirm_repeat': "I'm not sure I understood. Is this the transaction? Answer yes or no, or use the buttons.",
 'use_buttons': 'To continue, use the Confirm or Cancel button.',
 'confirm_again': 'Back to your charge: is this the transaction? Answer yes or no, or use the buttons.',
 'lock_declined_escalated': "All right, I didn't block the card. Your case stays with the team that will review it.",
 'cases_none': 'You have no claims filed through this channel.',
 'cases_list': 'These are your claims:',
 'movements': 'I found {n} transactions between {desde} and {hasta}.',
 'movements_none': "I didn't find transactions between {desde} and {hasta} with those filters.",
 'tool_failed': "I couldn't complete the operation because of a technical problem. Nothing was changed.",
 'not_verified': "I couldn't confirm that the operation was recorded, so I'm not treating it as done.",
 'invalid_confirmation': 'The confirmation is no longer valid (it expired, was already used or belongs to another session). Please review and '
                         'confirm again.',
 'manipulation': 'I can only look up data from your own account.',
 'exhausted': "I couldn't identify the charge with the information available."}
VARIANTS["en"] = {'greeting_short': ['Hi! How can I help you?', 'Hi again! Tell me, what do you need?', "I'm here. What can I help you with?"],
 'how_are_you': ['Very well, thanks for asking! How can I help you today?',
                 'All good here, thanks! What do you need?',
                 'Fine, thanks! Tell me, how can I help?'],
 'pick_topic': ['Choose an option or tell me in your own words what you need.',
                'Which of these options can I help you with?',
                'I can help with any of these options.'],
 'retry': ["Sorry, I didn't understand. ", "Sorry, I still don't understand. ", 'Let me try again. ']}
DISCLAIMER["en"] = "Filing a claim is not giving money back: the bank will review the case."
TYPE_LABEL["en"] = {"Withdrawal": "Cash withdrawal", "Payment": "Payment", "Purchase": "Purchase", "Deposit": "Deposit",
                    "Transfer": "Transfer", "Adjustment": "Adjustment"}
CATEGORY_LABEL["en"] = {"Food": "Food", "Transport": "Transport", "Services": "Services", "Entertainment": "Entertainment",
                        "Health": "Health", "Other": "Other"}
PICK["en"] = "I found {n} similar charges. Which one is it?"
CARD_LABEL["en"] = {"Tarjeta Crédito": "credit", "Tarjeta Débito": "debit"}
MONTHS["en"] = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
STATUS_DISPLAY["en"] = {"Approved": "Approved", "Pending": "Pending", "Reversed": "Reversed", "Declined": "Declined"}
