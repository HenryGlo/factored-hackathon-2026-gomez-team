"""Base de respuestas aprobadas (backend/knowledge/faq.yaml) y su recuperación.

Con ~12 entradas no hay base vectorial. Primero por `tema` (el LLM de intención elige de una lista cerrada, TOPICS);
si no hay tema o no existe, por palabras clave sobre el mensaje normalizado. Devuelve la entrada y el método usado,
que queda en la traza para auditoría.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml  # type: ignore[import-untyped]

from backend.app.dates import normalize

FAQ_FILE = Path(__file__).resolve().parents[1] / "knowledge" / "faq.yaml"
OUT_OF_SCOPE_ID = "fuera_de_alcance"     # redirección: la usa el controlador, no se recupera por tema ni por palabras
TOPICS = ("devolucion", "plazos", "que_sigue", "cancelar_reclamo", "cargo_pendiente", "tarjeta_bloqueada", "reposicion_tarjeta",
          "consultar_estado", "hablar_persona", "atencion_persona", "seguridad", "cargo_revertido")


@dataclass(frozen=True)
class Entry:
    id: str
    tema: str
    palabras: dict[str, list[str]]
    texto: dict[str, str]


@lru_cache
def load_faq(path: Path = FAQ_FILE) -> tuple[str, dict[str, Entry]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    entries = {e["id"]: Entry(e["id"], e["tema"], e["palabras"], e["texto"]) for e in data["entries"]}
    return data["version"], entries


def retrieve(topic: str | None, message: str, lang: str) -> tuple[Entry | None, str | None]:
    """(entrada, método): método 'tema' o 'palabras_clave'; (None, None) si no hay una entrada para la pregunta."""
    _, all_entries = load_faq()
    entries = {k: e for k, e in all_entries.items() if e.tema in TOPICS}
    by_topic = {e.tema: e for e in entries.values()}
    if topic and topic in by_topic:
        return by_topic[topic], "tema"
    text = normalize(message)
    best, score = None, 0
    for e in entries.values():
        words = e.palabras.get(lang, []) + e.palabras.get("es" if lang == "pt" else "pt", [])
        s = sum(len(w) for w in words if re.search(rf"\b{re.escape(normalize(w))}", text))   # prefijo: devolver → devolverá
        if s > score:
            best, score = e, s
    return (best, "palabras_clave") if best else (None, None)
