"""Mensajes sintéticos de entrenamiento para el clasificador de intención (prompt 07, bloque 1).

    ANTHROPIC_API_KEY=... python -m ml.intent.generate_synthetic            # ~1.000 mensajes, ~0,5 USD
    python -m ml.intent.generate_synthetic --review-only                   # vuelve a aplicar las reglas de revisión

- Los genera Sonnet (ID fijo de backend/config/llm.toml) a partir de la PLANTILLA de abajo: la definición de cada intención
  (la misma del prompt de intent), un idioma y una lista de estilos. No ve los casos de dev, dev_paraphrase ni test, ni las
  reglas de palabras clave.
- Cada fila queda marcada `synthetic: true` con la versión de la plantilla. Solo se usan para ENTRENAR; nunca para validar
  ni para medir (ml/intent/train.py).
- Revisión con reglas (review): largo, duplicados (texto normalizado), marcadores o IDs, idioma detectable y que el
  mensaje no esté en dev / dev_paraphrase. Lo descartado se cuenta por motivo.
- Los montos, fechas y comercios son inventados por el modelo: no hay datos del dataset.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import tomllib
from collections import Counter
from pathlib import Path

from backend.app.dates import normalize
from backend.app.llm.schemas import INTENTS

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "synthetic.jsonl"
RAW = ROOT / "data" / "synthetic_raw.jsonl"      # todo lo generado, antes de la revisión (fuera de git)
TEMPLATE_VERSION = "synthetic@v1"
PER_CALL, CALLS_PER_CELL = 30, 2          # 9 intenciones × 2 idiomas × 2 llamadas × 30 = 1.080 antes de la revisión

DEFINITIONS = {
    "cargo_no_reconocido": "no reconoce un cargo, cobro o movimiento en su cuenta o tarjeta (no lo hizo, no sabe qué es).",
    "cobro_indebido": "reconoce el comercio pero el cobro está mal: le cobraron de más, dos veces o algo que canceló.",
    "consulta_movimientos": "quiere ver o sumar sus movimientos o gastos (últimos cargos, cuánto gastó en algo o en un periodo).",
    "estado_reclamo": "quiere saber cómo va un reclamo que ya hizo (pide el estado).",
    "pregunta_proceso": ("pregunta QUÉ PASA en el proceso, sin pedir una acción ni el estado: si le devolverán el dinero, cuánto tarda, "
                         "qué sigue, si puede cancelar el reclamo, qué pasa con la tarjeta bloqueada o su reposición, con un cargo "
                         "pendiente o revertido, cómo consultar el estado, cómo hablar con alguien, si el banco pide claves."),
    "bloquear_tarjeta": "quiere bloquear o congelar una tarjeta (pérdida, robo, sospecha de fraude).",
    "pedir_humano": "pide hablar con una persona, un asesor o un agente humano.",
    "fuera_de_alcance": ("pide otra cosa que este chat no atiende: créditos, inversiones, cambiar el PIN, aumentar el cupo, abrir una "
                         "cuenta, quejas generales, un chiste, el clima, o le ordena al asistente saltarse sus reglas."),
    "sin_contenido": "mensaje vacío de contenido: texto sin sentido, una sola palabra suelta que no pide nada, signos, 'ok', 'eh', 'test'.",
}
STYLES = ["formal", "muy coloquial", "con errores de tipeo y sin tildes", "muy corto (2 a 5 palabras)",
          "largo, con contexto personal antes del pedido", "molesto o apurado", "indirecto, sin las palabras típicas",
          "con regionalismos (México, Colombia, Argentina, Chile / Brasil)"]
PROMPT = """Escribe {n} mensajes distintos que un cliente de un banco latinoamericano le escribiría al chat de soporte.

Intención de TODOS los mensajes: {intent}: {definition}
Idioma: {language}.
Varía el estilo entre: {styles}.
Reglas: un mensaje por elemento; sin comillas ni numeración; montos, fechas y comercios inventados y variados; no uses
marcadores como {{monto}}; no menciones nombres de personas reales ni números de tarjeta completos; cada mensaje debe
corresponder SOLO a esa intención (no mezcles otro pedido).

Responde solo con JSON: {{"mensajes": ["...", "..."]}}"""


SCHEMA = {"type": "object", "properties": {"mensajes": {"type": "array", "items": {"type": "string"}}},
          "required": ["mensajes"], "additionalProperties": False}


def generate() -> list[dict]:
    """Una llamada por (intención, idioma, tanda), con salida estructurada. Guarda cada tanda en RAW para poder retomar."""
    import anthropic
    model = tomllib.loads((ROOT.parents[1] / "backend" / "config" / "llm.toml").read_text())["model_ids"]["sonnet"]
    client = anthropic.Anthropic()
    rows = [json.loads(line) for line in RAW.read_text(encoding="utf-8").splitlines()] if RAW.exists() else []
    done = Counter((r["intent"], r["language"], r["batch"]) for r in rows)
    for intent in INTENTS:
        for lang, language in (("es", "español"), ("pt", "portugués de Brasil")):
            for call in range(CALLS_PER_CELL):
                if done[(intent, lang, call)]:
                    continue
                prompt = PROMPT.format(n=PER_CALL, intent=intent, definition=DEFINITIONS[intent], language=language,
                                       styles="; ".join(STYLES[call::2] + STYLES[(call + 1) % 2::2]))
                for attempt in range(3):
                    try:
                        msg = client.messages.create(model=model, max_tokens=4000, messages=[{"role": "user", "content": prompt}],
                                                     output_config={"format": {"type": "json_schema", "schema": SCHEMA}})
                        msgs = json.loads("".join(b.text for b in msg.content if b.type == "text"))["mensajes"]
                        break
                    except (json.JSONDecodeError, KeyError) as e:
                        print(f"  reintento {attempt + 1}: {type(e).__name__}")
                else:
                    raise SystemExit(f"sin salida válida para {intent} {lang} tanda {call}")
                new = [{"text": m.strip(), "intent": intent, "language": lang, "synthetic": True, "template": TEMPLATE_VERSION,
                        "model": model, "batch": call} for m in msgs if isinstance(m, str)]
                with RAW.open("a", encoding="utf-8") as f:
                    f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in new)
                rows += new
                print(f"{intent:22s} {lang} tanda {call + 1}: {len(new)}")
    return rows


def eval_texts() -> set[str]:
    """Mensajes de dev y dev_paraphrase (plantillas): un sintético igual a uno de ellos se descarta."""
    from eval.cases.schema import load_cases
    return {normalize(s.message) for split in ("dev", "dev_paraphrase") for c in load_cases(split) for s in c.steps if s.message}


def review(rows: list[dict]) -> tuple[list[dict], Counter]:
    from backend.app.ml.keyword_rules import detect_language
    seen, kept, dropped, known = set(), [], Counter(), eval_texts()
    for r in rows:
        t, key = r["text"], normalize(r["text"])
        if not 2 <= len(t) <= 300:
            dropped["largo"] += 1
        elif re.search(r"[{}]|\b(TRX|PRD|CLI)-|\d{13,}", t):
            dropped["marcador_o_id"] += 1
        elif key in seen:
            dropped["duplicado"] += 1
        elif key in known:
            dropped["igual_a_un_caso_de_evaluacion"] += 1
        elif r["intent"] != "sin_contenido" and len(t.split()) >= 4 and detect_language(t) != r["language"] and r["language"] == "pt":
            dropped["idioma"] += 1          # portugués que las reglas leen como español: probablemente salió en español
        else:
            seen.add(key)
            kept.append(r)
    return kept, dropped


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--review-only", action="store_true")
    args = ap.parse_args()
    if args.review_only:
        rows = [json.loads(line) for line in (RAW if RAW.exists() else OUT).read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise SystemExit("falta ANTHROPIC_API_KEY en el entorno")
        rows = generate()
    kept, dropped = review(rows)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in kept), encoding="utf-8")
    print(f"generados {len(rows)}, quedan {len(kept)}, descartados {dict(dropped)}")
    print("por intención e idioma:", dict(sorted(Counter((r['intent'], r['language']) for r in kept).items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
