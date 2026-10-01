"""Sí / no con tipeos y variantes es/pt en los pasos de confirmación."""
from __future__ import annotations

import pytest

from backend.app.controller.replies import classify_reply


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
