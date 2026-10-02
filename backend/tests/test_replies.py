"""Sí / no con tipeos y variantes es/pt en los pasos de confirmación."""
from __future__ import annotations

import pytest

from backend.app.controller.replies import asserts_about_shown_charge, classify_reply, declines_more


@pytest.mark.parametrize("text", ["sí", "si", "sii", "siii", "sim", "simm", "sip", "Sí, es ese", "sii, ese mero", "isso aí, sim",
                                  "é sim, é essa mesmo, oxente", "sim, isso mesmo", "dale", "ok", "esse mesmo", "claro que sí",
                                  "sí señor, así es"])
def test_affirmations(text):
    assert classify_reply(text) == "yes"


@pytest.mark.parametrize("text", ["no", "nooo", "nop", "nao", "não", "no es ese", "não, deixa pra lá", "ninguno", "es otro",
                                  "era outra"])
def test_negations(text):
    assert classify_reply(text) == "no"


@pytest.mark.parametrize("text", ["mmm no sé", "no sé", "não sei", "qué?", "sí pero no era ese", "es el del martes", "hmm",
                                  "obrigado", "na farmácia do centro", ""])
def test_unrecognized_is_never_a_confirmation(text):
    assert classify_reply(text) is None


@pytest.mark.parametrize("text", ["No reconozco el cargo de 1.248,65 USD del 10 jun 2026, yo no lo hice", "no lo hice", "No fui yo",
                                  "não reconheço essa cobrança", "nao fiz essa compra", "no hice esa compra", "No autoricé ese pago"])
def test_an_assertion_about_the_charge_is_not_a_no(text):
    """Empieza con "no" pero afirma algo: no rechaza el movimiento mostrado ni cierra la conversación."""
    assert classify_reply(text) is None and not declines_more(text)


@pytest.mark.parametrize("text", ["no", "No, gracias", "nop", "não, obrigado", "no gracias eso es todo", "no, nada más"])
def test_short_negative_declines_more(text):
    assert declines_more(text)


@pytest.mark.parametrize("text", ["no, pero quiero ver mis movimientos", "No, ahora quiero bloquear mi tarjeta porque la perdí ayer", "sí", "gracias"])
def test_a_no_followed_by_a_request_does_not_close(text):
    assert not declines_more(text)


@pytest.mark.parametrize("text", ["no reconozco ese cargo", "No reconozco ese cargo, yo no lo hice", "yo no lo hice", "no fui yo",
                                  "não reconheço essa cobrança", "eu não fiz essa compra"])
def test_assertion_about_the_charge_on_screen(text):
    assert asserts_about_shown_charge(text)


@pytest.mark.parametrize("text", ["no", "no es ese", "sí", "no reconozco el cargo de 500 del martes", "es otro, uno de Netflix", "¿cuánto tarda?"])
def test_not_an_assertion_about_the_charge_on_screen(text):
    assert not asserts_about_shown_charge(text)
