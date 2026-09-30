"""dates.py: expresiones de fecha del cliente (es/pt) → rango, contra la fecha de la sesión."""
from datetime import date

import pytest

from backend.app.dates import resolve_date_hint

TODAY = date(2026, 6, 17)   # miércoles


@pytest.mark.parametrize("hint, start, end", [
    ("hoy", "2026-06-17", "2026-06-17"), ("hoje", "2026-06-17", "2026-06-17"),
    ("ayer", "2026-06-16", "2026-06-16"), ("ontem", "2026-06-16", "2026-06-16"),
    ("anteayer", "2026-06-15", "2026-06-15"), ("anteontem", "2026-06-15", "2026-06-15"),
    ("hace 3 días", "2026-06-13", "2026-06-15"), ("há 3 dias", "2026-06-13", "2026-06-15"),
    ("hace tres dias", "2026-06-13", "2026-06-15"), ("faz dois dias", "2026-06-14", "2026-06-16"),
    ("hace una semana", "2026-06-07", "2026-06-13"), ("hace dos semanas", "2026-05-31", "2026-06-06"),
    ("la semana pasada", "2026-06-08", "2026-06-14"), ("semana passada", "2026-06-08", "2026-06-14"),
    ("esta semana", "2026-06-15", "2026-06-17"), ("nesta semana", "2026-06-15", "2026-06-17"),
    ("este mes", "2026-06-01", "2026-06-17"), ("neste mês", "2026-06-01", "2026-06-17"),
    ("el mes pasado", "2026-05-01", "2026-05-31"), ("mês passado", "2026-05-01", "2026-05-31"),
    ("el martes", "2026-06-16", "2026-06-16"), ("na terça-feira", "2026-06-16", "2026-06-16"),
    ("el miércoles", "2026-06-10", "2026-06-10"),        # hoy es miércoles → el anterior
    ("el viernes pasado", "2026-06-12", "2026-06-12"), ("sexta-feira", "2026-06-12", "2026-06-12"),
    ("15/06", "2026-06-15", "2026-06-15"), ("20/12", "2025-12-20", "2025-12-20"),   # sin año y futura → año anterior
    ("15/06/2026", "2026-06-15", "2026-06-15"), ("2026-05-03", "2026-05-03", "2026-05-03"),
    ("15 de junio", "2026-06-15", "2026-06-15"), ("3 de março", "2026-03-03", "2026-03-03"),
    ("15 de junho de 2025", "2025-06-15", "2025-06-15"),
    ("en mayo", "2026-05-01", "2026-05-31"), ("em julho", "2025-07-01", "2025-07-31"),
])
def test_resolves(hint, start, end):
    r = resolve_date_hint(hint, TODAY)
    assert r is not None, hint
    assert (r.start.isoformat(), r.end.isoformat()) == (start, end)


@pytest.mark.parametrize("hint", [None, "", "no me acuerdo", "hace mucho", "31/02"])
def test_unknown_is_none(hint):
    assert resolve_date_hint(hint, TODAY) is None


def test_distance():
    r = resolve_date_hint("la semana pasada", TODAY)
    assert r.distance_days(date(2026, 6, 10)) == 0 and r.distance_days(date(2026, 6, 16)) == 2
