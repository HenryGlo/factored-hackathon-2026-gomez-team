"""Generador combinatorio de flujos de conversación (sin LLM, sin base: determinista con una semilla).

Cada flujo parte de un caso SEMILLA ya escrito y validado (splits dev y dev_paraphrase) y cambia solo lo que no debería
cambiar el resultado. Lo esperado se copia de la semilla sin tocarlo, como en dev_noisy. Dimensiones:

- pick: otro cliente y otra transacción del mismo escenario (fila 0–39 del selector; al correr se ajusta a las filas que
  tenga la base, ver eval/generated/store.py:clamp_picks).
- saludo: el primer mensaje empieza con un saludo ("Hola, …", "Oi, …") o no. No se aplica a los casos que miden el
  atajo de saludos (expected.fast_path) ni si el mensaje ya saluda.
- ruido: ninguno, errores de tipeo (los mismos de eval/make_noisy.py), sin tildes o todo en minúsculas. Los marcadores
  ({monto_es}, {comercio}…) nunca se tocan.

Con semillas × 40 picks × 4 saludos × 4 ruidos hay más de 100.000 combinaciones; `generate(n)` toma n repartidas por igual
entre las semillas (ronda por semilla), sin repetir.
"""
from __future__ import annotations

import hashlib
import random
import re
from dataclasses import dataclass

from eval.cases.schema import Case, load_cases
from eval.make_noisy import noisy, strip_accents

GENERATOR_VERSION = "combinatorio@v1"
SEED_SPLITS = ("dev", "dev_paraphrase")
PICKS = 40                                   # los selectores devuelven como máximo 40 filas (LIMIT 40)
OPENERS = {"es": ["", "Hola, ", "Buenas tardes, ", "Buen día. "], "pt": ["", "Olá, ", "Oi, ", "Boa tarde, "]}
NOISES = ("ninguno", "tipeo", "sin_tildes", "minusculas")
GREETING = re.compile(r"^\W*(hola|buen[oa]s?|ol[aá]|oi|boa|bom|e a[ií])\b", re.I)
MARKER = re.compile(r"(\{[^}]*\})")


@dataclass(frozen=True)
class Generated:
    case: Case
    seed_case_id: str
    seed_split: str
    origin: str                              # combinatorio | parafrasis_claude
    pick: int
    opener: str                              # "" = sin saludo
    noise: str


def seeds() -> list[Case]:
    return [c for split in SEED_SPLITS for c in load_cases(split)]


def _outside_markers(text: str, fn) -> str:
    return "".join(p if MARKER.fullmatch(p) else fn(p) for p in MARKER.split(text))


def apply_noise(message: str, noise: str, rng: random.Random) -> str:
    if noise == "tipeo":
        return noisy(message, rng)
    if noise == "sin_tildes":
        return _outside_markers(message, strip_accents)
    if noise == "minusculas":
        return _outside_markers(message, str.lower)
    return message


def with_opener(message: str, opener: str) -> str:
    if not opener:
        return message
    first = message[:1]
    if first.isupper() and message[1:2].islower():          # "No reconozco…" → "Hola, no reconozco…" (no toca siglas)
        message = first.lower() + message[1:]
    return opener + message


def openers_for(seed: Case) -> list[str]:
    first = next((s for s in seed.steps if s.message is not None or s.action is not None), None)
    if seed.expected.fast_path is not None or first is None or first.message is None or GREETING.match(first.message):
        return [""]
    return OPENERS[seed.language]


def noises_for(seed: Case) -> tuple[str, ...]:
    if seed.expected.fast_path is True or not any(s.message for s in seed.steps):
        return ("ninguno",)                  # el atajo de saludos mide mensajes exactos
    return NOISES


def case_id(seed: Case, pick: int, opener: str, noise: str) -> str:
    h = hashlib.sha256(f"{seed.case_id}|{pick}|{opener}|{noise}".encode()).hexdigest()[:8]
    return f"g-{seed.case_id}-{h}"


def build(seed: Case, pick: int, opener: str, noise: str, seed_split: str) -> Generated:
    cid = case_id(seed, pick, opener, noise)
    rng = random.Random(int(hashlib.sha256(cid.encode()).hexdigest()[:12], 16))
    raw = seed.model_dump(exclude_none=True)
    first_msg = True
    for step in raw["steps"]:
        if step.get("message") is not None:
            msg = with_opener(step["message"], opener) if first_msg else step["message"]
            step["message"] = apply_noise(msg, noise, rng)
            first_msg = False
    label = ", ".join(x for x in (f"pick {pick}", f"saludo «{opener.strip()}»" if opener else "", f"ruido {noise}" if noise != "ninguno" else "") if x)
    raw.update({"case_id": cid, "split": "generated", "pick": pick, "title": f"{seed.title} · {label}"})
    return Generated(Case.model_validate(raw), seed.case_id, seed_split, "combinatorio", pick, opener, noise)


def generate(n: int, seed: int = 20261002, only_splits: tuple[str, ...] = SEED_SPLITS) -> list[Generated]:
    """n flujos sin repetir, repartidos por igual entre las semillas (ronda), en orden determinista."""
    rng = random.Random(seed)
    pools: list[list[tuple[Case, str, int, str, str]]] = []
    for split in only_splits:
        for s in load_cases(split):
            combos = [(s, split, p, o, z) for p in range(PICKS) for o in openers_for(s) for z in noises_for(s)]
            rng.shuffle(combos)
            pools.append(combos)
    rng.shuffle(pools)
    out: list[Generated] = []
    idx = 0
    while len(out) < n and any(pools):
        for pool in pools:
            if idx < len(pool) and len(out) < n:
                s, split, p, o, z = pool[idx]
                out.append(build(s, p, o, z, split))
        idx += 1
        if all(idx >= len(p) for p in pools):
            break
    return out


def stratified_sample(items: list, n: int, seed: int, key=lambda g: (g.case.language, g.case.category)) -> list:
    """n elementos con todos los estratos (idioma × categoría) presentes: reparto proporcional al tamaño del estrato,
    con un mínimo de min(5, tamaño) por estrato. Determinista con la semilla."""
    if n >= len(items):
        return list(items)
    groups: dict = {}
    for it in items:
        groups.setdefault(key(it), []).append(it)
    rng = random.Random(seed)
    quota = {k: min(len(v), 5) for k, v in groups.items()}
    rest = n - sum(quota.values())
    if rest < 0:                             # muestra más chica que los mínimos: uno por estrato y el resto al azar
        quota = {k: 1 for k in groups}
        rest = max(0, n - len(groups))
    total = sum(len(v) - quota[k] for k, v in groups.items()) or 1
    shares = {k: (len(v) - quota[k]) * rest / total for k, v in groups.items()}
    for k in groups:
        quota[k] += int(shares[k])
    for k in sorted(groups, key=lambda k: shares[k] - int(shares[k]), reverse=True)[: n - sum(quota.values())]:
        quota[k] += 1
    out = []
    for k in sorted(groups):
        out += rng.sample(groups[k], min(quota[k], len(groups[k])))
    return out[:n]
