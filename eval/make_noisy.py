"""Genera el split dev_noisy: los casos de dev con errores de tipeo en los mensajes del cliente (semilla fija).

    .venv/bin/python -m eval.make_noisy            # reescribe eval/cases/dev_noisy/cases.yaml
    .venv/bin/python -m eval.make_noisy --check    # falla si el archivo versionado no coincide con lo que se generaría

Sirve para medir la tolerancia a errores de tipeo (prompt 11). Qué hace con cada mensaje:
- no toca los marcadores ({monto_es}, {comercio}…), los números ni las palabras de menos de 5 letras;
- mete 1 error cada ~6 palabras (mínimo 1 si el mensaje tiene 3 palabras o más): letras vecinas cambiadas de lugar, una
  letra repetida, una letra perdida o un espacio corrido ("no reconozco" → "n oreconozco");
- a la mitad de los mensajes les quita las tildes.
Lo esperado de cada caso no cambia: el sistema debe llegar al mismo resultado. No se incluyen los casos de saludo
(`fast_path: true`), que miden el atajo de mensajes exactos y no la comprensión.
La semilla es fija y depende del id del caso: el archivo se regenera idéntico.
"""
from __future__ import annotations

import argparse
import hashlib
import random
import re
import sys
import unicodedata
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "cases" / "dev_noisy" / "cases.yaml"
SEED = 20261002
# palabras que cambian el pedido si un error las forma por accidente
PROTECTED = {"pessoa", "persona", "humano", "no", "nao", "si", "sim", "ninguno", "nenhum"}
TOKEN = re.compile(r"(\{[^}]*\}|\s+)")


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn" or c == "̃" and False)


def typo(word: str, nxt: str | None, rng: random.Random) -> tuple[str, str | None]:
    """Un error en `word`. Devuelve (palabra, siguiente palabra modificada o None)."""
    i = rng.randrange(1, len(word) - 1)
    op = rng.choice(("swap", "double", "drop", "space"))
    if op == "swap":
        return word[:i] + word[i + 1] + word[i] + word[i + 2:], None
    if op == "double":
        return word[:i] + word[i] + word[i:], None
    if op == "drop":
        return word[:i] + word[i + 1:], None
    if nxt and nxt.isalpha():                      # espacio corrido: la última letra pasa a la palabra siguiente
        return word[:-1], word[-1] + nxt
    return word[:i] + " " + word[i:], None


def noisy(message: str, rng: random.Random) -> str:
    parts = TOKEN.split(message)
    words = [i for i, p in enumerate(parts) if p and not TOKEN.fullmatch(p)]
    eligible = [i for i in words if len(re.sub(r"\W", "", parts[i])) >= 5 and re.sub(r"\W", "", parts[i]).isalpha()]
    if len(words) < 3 or not eligible:
        return message
    for i in sorted(rng.sample(eligible, min(len(eligible), max(1, len(words) // 6)))):
        core = re.match(r"^(\W*)(.*?)(\W*)$", parts[i], re.S)
        nxt_i = next((j for j in words if j > i), None)
        for _ in range(6):                        # un error no debe formar OTRA palabra con significado propio ("pessoal" → "pessoa")
            new, nxt = typo(core.group(2), parts[nxt_i] if nxt_i else None, rng)
            if not ({strip_accents(w).lower() for w in new.split()} | {strip_accents(nxt or "").lower()}) & PROTECTED:
                break
        else:
            continue
        parts[i] = core.group(1) + new + core.group(3)
        if nxt is not None and nxt_i is not None:
            parts[nxt_i] = nxt
    out = "".join(parts)
    return strip_accents(out) if rng.random() < 0.5 else out


def build() -> str:
    cases = []
    for path in sorted((ROOT / "cases" / "dev").glob("*.yaml")):
        for raw in yaml.safe_load(path.read_text(encoding="utf-8")) or []:
            if (raw.get("expected") or {}).get("fast_path") is True:
                continue
            rng = random.Random(int(hashlib.sha256(f"{SEED}:{raw['case_id']}".encode()).hexdigest()[:12], 16))
            steps = [{**s, "message": noisy(s["message"], rng)} if s.get("message") else s for s in raw["steps"]]
            if steps == raw["steps"]:
                continue                                  # sin mensajes que alterar (solo acciones o respuestas cortas)
            cases.append({**raw, "case_id": raw["case_id"] + "-n", "split": "dev_noisy", "steps": steps})
    header = ("# GENERADO por `python -m eval.make_noisy` desde eval/cases/dev/ (semilla fija). No editar a mano.\n"
              f"# {len(cases)} casos de dev con errores de tipeo en los mensajes del cliente; lo esperado no cambia.\n")
    return header + yaml.safe_dump(cases, allow_unicode=True, sort_keys=False, width=1000)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    text = build()
    if a.check:
        same = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print("dev_noisy al día" if same else "dev_noisy NO coincide: correr `python -m eval.make_noisy`")
        return 0 if same else 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(f"escrito {OUT.relative_to(ROOT.parent)} ({text.count('case_id:')} casos)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
