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
        return f"{TYPE_LABEL[lang].get(tx.get('transaction_type'), 'Pago')} · {CATEGORY_LABEL[lang].get(tx['transaction_category'], tx['transaction_category'])}"
    return TYPE_LABEL[lang].get(tx.get("transaction_type"), tx.get("transaction_type") or "")


PICK = {"es": ("Encontré estos cargos parecidos:", "¿Cuál de ellos es?"),
        "pt": ("Encontrei estas cobranças parecidas:", "Qual delas é?")}


def pick_text(txs: list[dict], lang: str) -> str:
    """Plantilla de aclaración para elegir entre candidatas: comercio · monto · fecha de cada una + "¿cuál de ellos?"."""
    head, ask = PICK.get(lang, PICK["es"])
    lines = [f"• {tx_label(t, lang)} · {fmt_money(t['amount'], t['currency'], lang)} · {fmt_date(t['transaction_date'], lang)}"
             for t in txs]
    return "\n".join([head, *lines, ask])


CARD_LABEL = {"es": {"Tarjeta Crédito": "crédito", "Tarjeta Débito": "débito"},
              "pt": {"Tarjeta Crédito": "crédito", "Tarjeta Débito": "débito"}}


def t(lang: str, key: str, **kw) -> str:
    return MSG.get(lang, MSG["es"])[key].format(**kw)


def money(amount) -> str:
    return str(Decimal(str(amount)).quantize(Decimal("0.01")))


def fmt_money(amount, currency: str, lang: str) -> str:
    """'1.250,50 COP' en es y pt (formato latino)."""
    s = f"{Decimal(str(amount)).quantize(Decimal('0.01')):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s} {currency}"


def fmt_date(d, lang: str) -> str:
    d = d.date() if isinstance(d, datetime) else d
    return d.strftime("%d/%m/%Y")


def tx_view(tx: dict[str, Any], rank: int | None = None, lang: str = "es") -> dict:
    """Movimiento del propio cliente para la UI (sin fraud_score, coordenadas ni is_fraud).
    merchant_name es el comercio real o null; label es lo que se muestra (traducido)."""
    v = {"transaction_id": tx["transaction_id"], "date": tx["transaction_date"].isoformat(), "amount": money(tx["amount"]),
         "currency": tx["currency"], "merchant_name": tx.get("merchant_name"), "label": tx_label(tx, lang),
         "channel": tx.get("channel"), "type": tx.get("transaction_type"), "status": tx["transaction_status"]}
    if rank is not None:
        v["rank"] = rank
    return v


def text_block(text: str) -> dict:
    return {"type": "text", "text": text}


def notice(code: str, text: str, level: str = "info") -> dict:
    return {"type": "notice", "level": level, "code": code, "text": text}


def error(code: str, message: str, retryable: bool = False) -> dict:
    return {"type": "error", "code": code, "message": message, "retryable": retryable}
