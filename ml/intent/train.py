"""Experimento y entrenamiento del clasificador de intención en cascada (prompt 07, bloque 1).

    python -m ml.intent.train            # validación cruzada, reporte, figuras y modelo final

Un solo comando reproduce todo: lee ml/intent/data/ (etiquetas, predicciones de Haiku, sintéticos) y ml/intent/config.toml,
y escribe docs/experiments/EXP-20261001-intent-cascade.md, sus figuras y models/intent/<version>.{joblib,json}.

Protocolo
- Validación cruzada estratificada POR GRUPOS sobre los mensajes reales (dev + dev_paraphrase): las paráfrasis de un caso y
  los mensajes con la misma plantilla quedan en el mismo fold. Los sintéticos solo entran al entrenamiento de cada fold.
- Nunca se usa el split test.
- Vías comparadas con la misma salida (una intención por mensaje): palabras clave, TF-IDF + regresión logística, lo mismo
  calibrado, Haiku (predicciones registradas de la corrida sistema_api) y la cascada (modelo calibrado si p >= tau y no hay
  marcas de manipulación; si no, Haiku).
"""
from __future__ import annotations

import hashlib
import json
import tomllib
from collections import Counter
from datetime import date
from pathlib import Path

import joblib
import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, f1_score
from sklearn.model_selection import StratifiedGroupKFold, StratifiedKFold
from sklearn.pipeline import FeatureUnion, Pipeline

from backend.app.llm.schemas import INTENTS
from backend.app.ml import keyword_rules
from backend.app.ml.intent_model import MODELS_DIR, needs_llm, preprocess
from ml.intent.dataset import DATA, Row, data_hash, real_rows, synthetic_rows

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
EXP = REPO / "docs" / "experiments"
CFG = tomllib.loads((ROOT / "config.toml").read_text(encoding="utf-8"))


def make_pipeline() -> Pipeline:
    m = CFG["model"]
    feats = FeatureUnion([
        ("word", TfidfVectorizer(preprocessor=preprocess, analyzer="word", ngram_range=tuple(m["word_ngram"]), sublinear_tf=True)),
        ("char", TfidfVectorizer(preprocessor=preprocess, analyzer="char_wb", ngram_range=tuple(m["char_ngram"]), sublinear_tf=True,
                                 max_features=m["max_char_features"])),
    ])
    return Pipeline([("tfidf", feats), ("lr", LogisticRegression(C=m["c"], max_iter=3000, class_weight="balanced"))])


def make_calibrated(n_min_class: int):
    """Sigmoide (Platt): con pocos cientos de ejemplos por clase, la isotónica sobreajusta."""
    # ensemble=False: un solo modelo final + calibradores ajustados con predicciones fuera de fold (artefacto 5 veces menor)
    return CalibratedClassifierCV(make_pipeline(), method="sigmoid", cv=min(5, n_min_class), ensemble=False)


def manipulation(text: str) -> bool:
    """Mensajes que la cascada manda siempre al LLM (misma regla que en ejecución: manipulación, varias intenciones, largos)."""
    return needs_llm(text) is not None


def ece(conf: np.ndarray, correct: np.ndarray, bins: int = 10) -> tuple[float, list[tuple[float, float, int]]]:
    edges, total, rows = np.linspace(0, 1, bins + 1), 0.0, []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (conf > lo) & (conf <= hi)
        if m.any():
            total += m.mean() * abs(correct[m].mean() - conf[m].mean())
            rows.append((float(conf[m].mean()), float(correct[m].mean()), int(m.sum())))
    return float(total), rows


def brier(proba: np.ndarray, y: np.ndarray, classes: list[str]) -> float:
    onehot = np.array([[1.0 if c == t else 0.0 for c in classes] for t in y])
    return float(((proba - onehot) ** 2).sum(axis=1).mean())


def error_cost(true: str) -> float:
    return CFG["cost"]["error_critical_usd"] if true in CFG["cost"]["critical"] else CFG["cost"]["error_other_usd"]


def cascade_stats(tau: float, y, local, conf, haiku, manip) -> dict:
    accept = (conf >= tau) & ~manip
    pred = np.where(accept, local, haiku)
    wrong_local = accept & (local != y)
    wrong_llm = ~accept & (haiku != y)
    cost = (sum(error_cost(t) for t in y[wrong_local]) + sum(error_cost(t) for t in y[wrong_llm])
            + (~accept).sum() * CFG["cost"]["llm_intent_call_usd"]) / len(y)
    return {"tau": tau, "coverage": float(accept.mean()), "n_local": int(accept.sum()), "errors_local": int(wrong_local.sum()),
            "errors_llm": int(wrong_llm.sum()), "error_rate_local": float(wrong_local.sum() / max(accept.sum(), 1)),
            "accuracy": float((pred == y).mean()), "macro_f1": float(f1_score(y, pred, average="macro", labels=sorted(set(y)))),
            "expected_cost": float(cost), "pred": pred}


def frac(n: int, d: int) -> str:
    return f"{n}/{d} ({100 * n / d:.1f} %)" if d else f"{n}/0"


def main() -> int:
    real, syn = real_rows(), synthetic_rows()
    haiku_all = json.loads((DATA / "haiku_predictions.json").read_text(encoding="utf-8"))
    y = np.array([r.intent for r in real])
    groups = np.array([r.group for r in real])
    texts = [r.text for r in real]
    haiku = np.array([haiku_all[r.key] for r in real])
    manip = np.array([manipulation(t) for t in texts])
    keyword = np.array([keyword_rules.classify(t)["intent"] for t in texts])
    classes = sorted(set(INTENTS))
    n = len(real)

    # ---------------------------------------------------------------- validación cruzada por grupos (reales)
    skf = StratifiedGroupKFold(n_splits=CFG["model"]["folds"], shuffle=True, random_state=CFG["model"]["seed"])
    p_lr, p_cal = np.zeros((n, len(classes))), np.zeros((n, len(classes)))
    syn_x, syn_y = [r.text for r in syn], [r.intent for r in syn]
    for fold, (tr, va) in enumerate(skf.split(texts, y, groups)):
        assert not set(groups[tr]) & set(groups[va])                       # sin fuga entre folds
        x_tr, y_tr = [texts[i] for i in tr] + syn_x, list(y[tr]) + syn_y
        lr = make_pipeline().fit(x_tr, y_tr)
        cal = make_calibrated(min(Counter(y_tr).values())).fit(x_tr, y_tr)
        for model, out in ((lr, p_lr), (cal, p_cal)):
            cols = [classes.index(c) for c in model.classes_]
            out[np.ix_(va, cols)] = model.predict_proba([texts[i] for i in va])
    labels_real = sorted(set(y))
    res = {}
    for name, pred in (("palabras clave", keyword), ("TF-IDF + LR", np.array(classes)[p_lr.argmax(1)]),
                       ("TF-IDF + LR calibrado", np.array(classes)[p_cal.argmax(1)]), ("Haiku (solo LLM)", haiku)):
        res[name] = {"acc": int((pred == y).sum()), "f1": f1_score(y, pred, average="macro", labels=labels_real), "pred": pred}
    conf_lr, conf_cal = p_lr.max(1), p_cal.max(1)
    local = np.array(classes)[p_cal.argmax(1)]
    ece_lr, _ = ece(conf_lr, np.array(classes)[p_lr.argmax(1)] == y)
    ece_cal, rel_cal = ece(conf_cal, local == y)
    curve = [cascade_stats(t, y, local, conf_cal, haiku, manip) for t in CFG["model"]["taus"]]
    floor = min(c["expected_cost"] for c in curve)
    best = max((c for c in curve if c["expected_cost"] <= floor * (1 + CFG["model"]["tau_cost_tolerance"])), key=lambda c: c["tau"])
    always_llm = (sum(error_cost(t) for t in y[haiku != y]) + n * CFG["cost"]["llm_intent_call_usd"]) / n

    # ---------------------------------------------------------------- clases raras: validación solo con sintéticos
    sx, sy = np.array(syn_x), np.array(syn_y)
    syn_pred = np.empty(len(sy), dtype=object)
    for tr, va in StratifiedKFold(5, shuffle=True, random_state=CFG["model"]["seed"]).split(sx, sy):
        syn_pred[va] = make_pipeline().fit(list(sx[tr]), list(sy[tr])).predict(list(sx[va]))
    syn_kw = np.array([keyword_rules.classify(t)["intent"] for t in sx])

    # ---------------------------------------------------------------- modelo final (todo lo real + sintéticos)
    all_rows: list[Row] = real + syn
    final = make_calibrated(min(Counter(r.intent for r in all_rows).values())).fit([r.text for r in all_rows], [r.intent for r in all_rows])
    version = CFG["model"]["version"]
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    artifact = MODELS_DIR / f"{version}.joblib"
    joblib.dump(final, artifact, compress=3)
    import sklearn
    meta = {"version": version, "trained_on": str(date.today()), "tau": best["tau"], "classes": list(final.classes_),
            "training_data_sha256": data_hash(all_rows), "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
            "n_real": len(real), "n_synthetic": len(syn), "sklearn": sklearn.__version__,
            "cv": {"macro_f1_calibrated": round(res["TF-IDF + LR calibrado"]["f1"], 4), "coverage_at_tau": round(best["coverage"], 4),
                   "error_rate_local_at_tau": round(best["error_rate_local"], 4)},
            "config": CFG, "command": "python -m ml.intent.train"}
    (MODELS_DIR / f"{version}.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    # ---------------------------------------------------------------- figuras
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig_dir = EXP / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.2))
    ax[0].plot([0, 1], [0, 1], "--", color="gray", label="calibración perfecta")
    ax[0].plot([r[0] for r in rel_cal], [r[1] for r in rel_cal], "o-", label=f"LR calibrado (ECE {ece_cal:.3f})")
    ax[0].set(xlabel="confianza media del bin", ylabel="aciertos en el bin", title="¿La probabilidad del modelo calibrado es confiable?")
    ax[0].legend()
    ax[1].plot([c["coverage"] * 100 for c in curve], [c["error_rate_local"] * 100 for c in curve], "o-")
    for c in curve:
        ax[1].annotate(f"τ={c['tau']}", (c["coverage"] * 100, c["error_rate_local"] * 100), fontsize=7, xytext=(3, 3), textcoords="offset points")
    ax[1].set(xlabel="% de turnos resueltos sin LLM (cobertura)", ylabel="% de error en esos turnos",
              title="¿Cuántos turnos evita el LLM y con qué error?")
    fig.tight_layout()
    fig.savefig(fig_dir / "intent-cascade-calibracion-cobertura.png", dpi=110)

    # ---------------------------------------------------------------- reporte
    cm = confusion_matrix(y, best["pred"], labels=labels_real)
    L = ["# EXP-20261001-intent-cascade · Clasificador de intención en cascada", "",
         f"Generado por `python -m ml.intent.train` el {date.today()} (reproducible con ese único comando). Issue #17.", "",
         "## Hipótesis", "",
         "Un clasificador pequeño (TF-IDF + regresión logística calibrada) puede atender los turnos rutinarios y dejar el LLM (Haiku) "
         "solo para los difíciles, con menos costo y la misma calidad.", "",
         "## Datos", "",
         f"- **Reales:** {n} mensajes que llegan al clasificador (estado `inicio`): {Counter(r.source for r in real)['dev']} de dev y "
         f"{Counter(r.source for r in real)['dev_paraphrase']} de dev_paraphrase, en {len(set(groups))} grupos. Etiquetas: "
         "`ml/intent/data/labels.yaml` (intención de Haiku en una corrida donde el caso pasó todos los checkers, revisada a mano por "
         "una persona: 2 corregidas); las paráfrasis heredan la etiqueta de su caso. **Nunca el split test.**",
         f"- **Sintéticos (solo entrenamiento):** {len(syn)} mensajes generados por Sonnet con la plantilla documentada en "
         "`ml/intent/generate_synthetic.py`, revisados con reglas y marcados `synthetic`.",
         "- **Sin fuga:** validación cruzada estratificada de 5 folds por grupos; las paráfrasis de un caso y los mensajes con la "
         "misma plantilla van al mismo fold.", "",
         "| Intención | Reales | Grupos | Sintéticos |", "|---|---|---|---|"]
    by_group = {c: len({g for g, t in zip(groups, y) if t == c}) for c in classes}
    syn_count = Counter(sy)
    L += [f"| `{c}` | {int((y == c).sum())} | {by_group[c]} | {syn_count[c]} |" for c in classes]
    rare = [c for c in classes if (y == c).sum() < 5]
    L += ["", f"**Clases raras:** el set real está muy desbalanceado ({frac(int((y == 'cargo_no_reconocido').sum()), n)} es "
          f"`cargo_no_reconocido`) y {', '.join(f'`{c}`' for c in rare)} tienen menos de 5 mensajes reales. Para esas clases el modelo "
          "aprende de los sintéticos (`class_weight=balanced`) y **no hay cómo validarlas con datos reales**: su resultado de abajo "
          "sale solo de sintéticos y es optimista (misma distribución que el generador).", "",
          "## Resultados (validación cruzada sobre los mensajes reales)", "",
          "| Vía | Aciertos | Macro-F1 | Turnos que llegan al LLM |", "|---|---|---|---|"]
    for name, r in res.items():
        llm = "0/%d (0.0 %%)" % n if "Haiku" not in name else frac(n, n)
        L.append(f"| {name} | {frac(r['acc'], n)} | {r['f1']:.3f} | {llm} |")
    L.append(f"| **Cascada (τ = {best['tau']})** | {frac(int(round(best['accuracy'] * n)), n)} | {best['macro_f1']:.3f} | "
             f"{frac(n - best['n_local'], n)} |")
    L += ["", f"Macro-F1 sobre las {len(labels_real)} intenciones con mensajes reales. **Sesgo declarado:** las etiquetas de dev salen "
          "de Haiku (más revisión), así que el acierto de Haiku en dev está inflado; la comparación justa de Haiku son los "
          f"{Counter(r.source for r in real)['dev_paraphrase']} mensajes de dev_paraphrase: "
          f"{frac(int(sum(h == t for h, t, r in zip(haiku, y, real) if r.source == 'dev_paraphrase')), Counter(r.source for r in real)['dev_paraphrase'])}.",
          "", "### Calibración", "", "| Modelo | Brier (multiclase) | ECE (10 bins) |", "|---|---|---|",
          f"| TF-IDF + LR | {brier(p_lr, y, classes):.4f} | {ece_lr:.4f} |",
          f"| TF-IDF + LR calibrado (sigmoide) | {brier(p_cal, y, classes):.4f} | {ece_cal:.4f} |", "",
          "Se usó sigmoide y no isotónica por el tamaño de los datos (cientos de ejemplos por clase). "
          + ("**La calibración no mejoró** ni Brier ni ECE frente a la regresión logística sin calibrar: se dice tal cual. La cascada usa "
             "el modelo calibrado porque el umbral se eligió sobre sus probabilidades." if brier(p_cal, y, classes) >= brier(p_lr, y, classes)
             else "La calibración mejoró el Brier frente a la regresión logística sin calibrar."), "",
          "![Calibración y cobertura](figures/intent-cascade-calibracion-cobertura.png)", "",
          "### Umbral τ por costo esperado", "",
          f"Supuestos del equipo (`ml/intent/config.toml`): una llamada de intención a Haiku cuesta ${CFG['cost']['llm_intent_call_usd']} "
          f"(medido); equivocar una intención crítica ({', '.join(CFG['cost']['critical'])}) cuesta ${CFG['cost']['error_critical_usd']:.2f} y "
          f"cualquier otra ${CFG['cost']['error_other_usd']:.2f}. Además, un mensaje con marcas de manipulación, con varias intenciones según las reglas o muy largo va siempre al LLM (el modelo pequeño da una sola intención).", "",
          "| τ | Cobertura (sin LLM) | Errores del modelo local | Errores de Haiku en el resto | Aciertos de la cascada | Costo esperado por turno |",
          "|---|---|---|---|---|---|"]
    for c in curve:
        mark = " ←" if c is best else ""
        L.append(f"| {c['tau']}{mark} | {frac(c['n_local'], n)} | {frac(c['errors_local'], max(c['n_local'], 1))} | {c['errors_llm']} | "
                 f"{frac(int(round(c['accuracy'] * n)), n)} | ${c['expected_cost']:.5f} |")
    L += ["", f"Solo LLM: ${always_llm:.5f} por turno. τ elegido: **{best['tau']}**: el más alto cuyo costo esperado queda a menos de {CFG['model']['tau_cost_tolerance']:.0%} del mínimo (con {n} mensajes, diferencias menores son ruido; se prefiere mandar más turnos dudosos al LLM).", "",
          f"### Matriz de confusión de la cascada (τ = {best['tau']}, filas = real, columnas = predicho)", "",
          "| | " + " | ".join(f"`{c}`" for c in labels_real) + " |", "|---|" + "---|" * len(labels_real)]
    L += [f"| `{c}` | " + " | ".join(str(v) for v in row) + " |" for c, row in zip(labels_real, cm)]
    L += ["", "### Por idioma (cascada)", "", "| Idioma | Aciertos |", "|---|---|"]
    for lang in ("es", "pt"):
        m = np.array([r.language == lang for r in real])
        L.append(f"| {lang} | {frac(int((best['pred'][m] == y[m]).sum()), int(m.sum()))} |")
    L += ["", "### Clases raras: validación cruzada SOLO con sintéticos (optimista, no comparable con lo de arriba)", "",
          "| Intención | TF-IDF + LR: aciertos | Palabras clave: aciertos |", "|---|---|---|"]
    for c in classes:
        m = sy == c
        L.append(f"| `{c}` | {frac(int((syn_pred[m] == c).sum()), int(m.sum()))} | {frac(int((syn_kw[m] == c).sum()), int(m.sum()))} |")
    L += ["", "## Modelo", "",
          f"`models/intent/{version}.joblib` ({artifact.stat().st_size / 1024:.0f} KB) y `{version}.json` (versión, fecha, hash de los datos de "
          "entrenamiento y del artefacto, τ, configuración). Ficha: [docs/ml/intent-classifier.md](../ml/intent-classifier.md).", ""]
    harness = ROOT / "harness_results.md"       # resultados del harness y conclusión: escritos a mano tras correr la variante
    if harness.exists():
        L += [harness.read_text(encoding="utf-8").rstrip(), ""]
    EXP.mkdir(exist_ok=True)
    (EXP / "EXP-20261001-intent-cascade.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[L.index("## Resultados (validación cruzada sobre los mensajes reales)"):][:60]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
