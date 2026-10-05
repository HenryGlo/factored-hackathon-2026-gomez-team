"""Convierte la expresión de fecha LITERAL del cliente (date_hint) en un rango de fechas.

El LLM nunca calcula fechas: el nodo extract copia la expresión ("ayer", "el martes", "15 de
junho") y este módulo la resuelve contra la fecha de la sesión. El rango se compara contra la
fecha de `transaction_date`, que es cuando el cliente vio el cargo (H16), no contra process_date.

Reglas (es y pt):
- hoy/hoje · ayer/ontem · anteayer/anteontem
- hace N días / há N dias → N±1 días
- hace una/dos/tres semanas, hace un mes (rangos amplios)
- esta semana · la semana pasada (lunes a domingo) · este mes · el mes pasado
- días de la semana ("el martes", "na terça-feira", "el viernes pasado") → la ocurrencia más
  reciente ANTES de hoy
- fechas explícitas: 15/06, 15/06/2026, 2026-06-15, "15 de junio", "15 de junho de 2026"
  (sin año → la ocurrencia más reciente que no sea futura)
- mes solo: "en mayo", "em maio" → ese mes completo (el más reciente no futuro)
Cualquier otra expresión → None (el controlador la trata como fecha desconocida).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta

WEEKDAYS = {"lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3, "viernes": 4, "sabado": 5, "domingo": 6,
            "segunda": 0, "terca": 1, "quarta": 2, "quinta": 3, "sexta": 4,
            "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
MONTHS = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
          "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
          "janeiro": 1, "fevereiro": 2, "marco": 3, "maio": 5, "junho": 6, "julho": 7, "setembro": 9,
          "outubro": 10, "novembro": 11, "dezembro": 12,
          "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7, "august": 8, "september": 9,
          "october": 10, "november": 11, "december": 12}
NUMBERS = {"un": 1, "uno": 1, "una": 1, "um": 1, "uma": 1, "dos": 2, "dois": 2, "duas": 2, "par": 2, "tres": 3,
           "cuatro": 4, "quatro": 4, "cinco": 5, "seis": 6, "siete": 7, "sete": 7, "ocho": 8, "oito": 8,
           "nueve": 9, "nove": 9, "diez": 10, "dez": 10,
           "a": 1, "one": 1, "two": 2, "couple": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}


@dataclass(frozen=True)
class DateRange:
    start: date
    end: date
    rule: str

    def contains(self, d: date) -> bool:
        return self.start <= d <= self.end

    def distance_days(self, d: date) -> int:
        """0 si d está dentro; si no, días hasta el borde más cercano."""
        return 0 if self.contains(d) else min(abs((d - self.start).days), abs((d - self.end).days))


def normalize(text: str) -> str:
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", t).strip()


def _num(token: str) -> int | None:
    return int(token) if token.isdigit() else NUMBERS.get(token)


def _month_range(y: int, m: int) -> tuple[date, date]:
    start = date(y, m, 1)
    end = (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1))
    return start, end


def _most_recent_month(m: int, today: date) -> tuple[date, date]:
    y = today.year if m <= today.month else today.year - 1
    return _month_range(y, m)


def _explicit(t: str, today: date) -> DateRange | None:
    if m := re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", t):
        d = date(int(m[1]), int(m[2]), int(m[3]))
        return DateRange(d, d, "fecha_iso")
    if m := re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", t):
        day, month, year = int(m[1]), int(m[2]), m[3]
        return _day_month(day, month, year, today, "fecha_dd/mm")
    months = "|".join(MONTHS)
    if m := re.search(rf"\b(\d{{1,2}}) de ({months})(?: de (\d{{4}}))?\b", t):
        return _day_month(int(m[1]), MONTHS[m[2]], m[3], today, "fecha_texto")
    # inglés: "June 10", "June 10th", "10 June", "on the 10th of June" (el mes en letras; "06/10" se lee día/mes, como en es/pt)
    if m := re.search(rf"\b({months}) (\d{{1,2}})(?:st|nd|rd|th)?(?:,? (\d{{4}}))?\b", t):
        return _day_month(int(m[2]), MONTHS[m[1]], m[3], today, "fecha_texto")
    if m := re.search(rf"\b(\d{{1,2}})(?:st|nd|rd|th)? (?:of )?({months})(?:,? (\d{{4}}))?\b", t):
        return _day_month(int(m[1]), MONTHS[m[2]], m[3], today, "fecha_texto")
    if m := re.search(rf"\b(?:en|em|de|durante|no mes de|en el mes de|in|during) ({months})\b|^({months})$", t):
        start, end = _most_recent_month(MONTHS[m[1] or m[2]], today)
        return DateRange(start, min(end, today), "mes")
    return None


def _day_month(day: int, month: int, year: str | None, today: date, rule: str) -> DateRange | None:
    try:
        if year:
            y = int(year) + (2000 if len(year) == 2 else 0)
            d = date(y, month, day)
        else:
            d = date(today.year, month, day)
            if d > today:
                d = date(today.year - 1, month, day)
    except ValueError:
        return None
    return DateRange(d, d, rule)


def resolve_date_hint(hint: str | None, today: date) -> DateRange | None:
    if not hint:
        return None
    t = normalize(hint)
    monday = today - timedelta(days=today.weekday())
    if re.search(r"\b(hoy|hoje|today)\b", t):
        return DateRange(today, today, "hoy")
    if re.search(r"\b(anteayer|antier|antes de ayer|anteontem|day before yesterday)\b", t):
        d = today - timedelta(2)
        return DateRange(d, d, "anteayer")
    if re.search(r"\b(ayer|ontem|yesterday)\b", t):
        d = today - timedelta(1)
        return DateRange(d, d, "ayer")
    if m := re.search(r"\b(\w+)\s+(days?|weeks?|months?)\s+ago\b", t):         # inglés: "3 days ago", "two weeks ago"
        n = _num(m[1])
        if n is not None:
            unit = {"day": "dias", "week": "semanas", "mont": "meses"}[m[2][:4].rstrip("s") if not m[2].startswith("mont") else "mont"]
            t = f"hace {n} {unit}"
    if m := re.search(r"\b(?:hace|ha|faz)\s+(?:unos?\s+|umas?\s+|como\s+)?(\w+)\s+(dias?|semanas?|mes|meses)\b", t):
        n = _num(m[1])
        if n is not None:
            unit = m[2]
            if unit.startswith("dia"):
                return DateRange(today - timedelta(n + 1), today - timedelta(max(n - 1, 0)), "hace_n_dias")
            if unit.startswith("semana"):
                return DateRange(today - timedelta(7 * n + 3), today - timedelta(max(7 * n - 3, 0)), "hace_n_semanas")
            return DateRange(today - timedelta(30 * n + 10), today - timedelta(max(30 * n - 10, 0)), "hace_n_meses")
    if re.search(r"\b(semana pasada|semana passada|ultima semana|last week)\b", t):
        return DateRange(monday - timedelta(7), monday - timedelta(1), "semana_pasada")
    if re.search(r"\b(esta semana|essa semana|nesta semana|nessa semana|this week)\b", t):
        return DateRange(monday, today, "esta_semana")
    if re.search(r"\b(mes pasado|mes passado|ultimo mes|last month)\b", t):
        start, end = _month_range(*(((today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1))))
        return DateRange(start, end, "mes_pasado")
    if re.search(r"\b(este mes|esse mes|neste mes|nesse mes|this month)\b", t):
        return DateRange(today.replace(day=1), today, "este_mes")
    if (explicit := _explicit(t, today)) is not None:
        return explicit
    for name, wd in WEEKDAYS.items():
        if re.search(rf"\b{name}(?:-feira)?\b", t):
            back = (today.weekday() - wd) % 7 or 7   # ocurrencia más reciente ANTES de hoy
            d = today - timedelta(days=back)
            return DateRange(d, d, "dia_semana")
    return None
