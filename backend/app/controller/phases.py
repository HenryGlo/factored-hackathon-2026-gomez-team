"""Fase real del turno en curso, para el indicador de espera del frontend (GET /api/conversations/{id}/phase).

understanding → searching_transactions (solo si se llama a search_transactions) → checking_policy → writing.
En memoria del proceso: con varias instancias, la consulta puede caer en otra y devolver null; el frontend se queda con
el texto neutro. Nunca bloquea ni rompe el turno.
"""
from __future__ import annotations

import time

PHASES = ("understanding", "searching_transactions", "checking_policy", "writing")
TTL_SECONDS = 120          # un turno colgado no deja una fase vieja para siempre

_current: dict[str, tuple[str, str, float]] = {}     # conversation_id -> (customer_id, fase, instante)


def set_phase(conversation_id: str, customer_id: str, phase: str) -> None:
    _current[conversation_id] = (customer_id, phase, time.monotonic())


def clear(conversation_id: str) -> None:
    _current.pop(conversation_id, None)


def safe(fn, *args) -> None:
    """El indicador de espera es accesorio: un fallo aquí nunca rompe el turno."""
    try:
        fn(*args)
    except Exception:  # noqa: BLE001
        pass


def get(conversation_id: str, customer_id: str) -> str | None:
    """Solo el dueño de la conversación ve su fase; para cualquier otro, None (igual que si no hubiera turno)."""
    entry = _current.get(conversation_id)
    if not entry or entry[0] != customer_id or time.monotonic() - entry[2] > TTL_SECONDS:
        return None
    return entry[1]
