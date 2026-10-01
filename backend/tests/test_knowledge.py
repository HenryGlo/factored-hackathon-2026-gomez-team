"""Base de respuestas aprobadas (backend/knowledge/faq.yaml) y su recuperación."""
from __future__ import annotations

import re

import pytest

from backend.app.knowledge import TOPICS, load_faq, retrieve
from backend.app.llm.nodes import FORBIDDEN
from backend.app.llm.schemas import IntentOutput
from eval.harness.checkers import PROMISE, SUCCESS_CLAIM


def test_every_entry_is_complete_in_both_languages_and_topics_match_the_schema():
    version, entries = load_faq()
    assert version.startswith("faq@v") and 10 <= len(entries) <= 14
    assert {e.tema for e in entries.values()} == set(TOPICS)
    schema_topics = set(IntentOutput.model_json_schema()["properties"]["tema_proceso"]["anyOf"][0]["enum"])
    assert schema_topics == set(TOPICS)
    for e in entries.values():
        assert set(e.texto) == {"es", "pt"} and all(len(t) > 40 for t in e.texto.values())
        assert e.palabras["es"] and e.palabras["pt"]


@pytest.mark.parametrize("lang", ["es", "pt"])
def test_approved_texts_never_promise_refunds(lang):
    for e in load_faq()[1].values():
        assert not FORBIDDEN.search(e.texto[lang]), e.id          # guarda R5 de los nodos
        assert not re.search(PROMISE, e.texto[lang]), e.id        # checker del harness
        assert not SUCCESS_CLAIM.search(e.texto[lang]), e.id      # no suena a "registré tu reclamo" sin un result verificado


@pytest.mark.parametrize("topic,text,lang,expected,method", [
    ("plazos", "lo que sea", "es", "plazos", "tema"),
    (None, "¿El banco me devolverá el dinero?", "es", "devolucion", "palabras_clave"),
    (None, "posso cancelar a reclamação?", "pt", "cancelar_reclamo", "palabras_clave"),
    (None, "¿qué pasa con mi tarjeta bloqueada?", "es", "tarjeta_bloqueada", "palabras_clave"),
    ("tema_inexistente", "¿cuánto tarda?", "es", "plazos", "palabras_clave"),
])
def test_retrieve_by_topic_then_keywords(topic, text, lang, expected, method):
    entry, how = retrieve(topic, text, lang)
    assert entry is not None and entry.tema == expected and how == method


def test_no_entry_for_unrelated_questions():
    assert retrieve(None, "¿cuál es la capital de Francia?", "es") == (None, None)
