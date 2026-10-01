"""Experimento de riesgo: score crudo vs score calibrado vs modelo simple para movimientos sin score (prompt 07, bloque 2).

    python -m ml.fraud_risk.experiment            # lee data/bank.duckdb (DUCKDB_PATH), no escribe datos del dataset

Escribe docs/experiments/EXP-20261001-risk-calibration.md, su figura y models/risk/<version>.json (el calibrador isotónico
como puntos (score, probabilidad): un JSON pequeño, sin datos del dataset).

Etiqueta: transactions.is_fraud (columna del diccionario de datos; sintética). Partición TEMPORAL: se entrena con lo
antiguo y se prueba con lo reciente. Sin atributos demográficos del cliente.
"""
from __future__ import annotations

import hashlib
import json
import os
import tomllib
from datetime import date
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
CFG = tomllib.loads((ROOT / "config.toml").read_text(encoding="utf-8"))
EXP = REPO / "docs" / "experiments"
MODELS = REPO / "models" / "risk"
C_FN, C_FP = CFG["cost"]["false_negative_usd"], CFG["cost"]["false_positive_usd"]


def frac(n: int, d: int) -> str:
    return f"{n:,}/{d:,} ({100 * n / d:.2f} %)".replace(",", ".") if d else f"{n}/0"


def decision(y: np.ndarray, flag: np.ndarray) -> dict:
    tp, fp, fn = int((flag & (y == 1)).sum()), int((flag & (y == 0)).sum()), int((~flag & (y == 1)).sum())
    return {"flag": int(flag.sum()), "tp": tp, "fp": fp, "fn": fn, "n": len(y), "pos": int(y.sum()),
            "cost_per_1000": 1000 * (fn * C_FN + fp * C_FP) / len(y)}


def best_threshold(y: np.ndarray, p: np.ndarray) -> float:
    """Umbral de costo esperado mínimo. Con probabilidades bien calibradas, el óptimo teórico es C_FP / (C_FP + C_FN)."""
    grid = np.unique(np.quantile(p, np.linspace(0.5, 1, 400)))
    costs = [decision(y, p >= t)["cost_per_1000"] for t in grid]
    return float(grid[int(np.argmin(costs))])


def reliability(y: np.ndarray, p: np.ndarray, bins: int = 10) -> list[tuple[float, float, int]]:
    """Bins por cuantiles de la probabilidad (con prevalencia ~0,1 %, bins de ancho fijo quedan vacíos)."""
    edges = np.unique(np.quantile(p, np.linspace(0, 1, bins + 1)))
    out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (p >= lo) & ((p < hi) if hi < edges[-1] else (p <= hi))
        if m.any():
            out.append((float(p[m].mean()), float(y[m].mean()), int(m.sum())))
    return out


def main() -> int:
    db = os.environ.get("DUCKDB_PATH") or str(REPO / "data" / "bank.duckdb")
    con = duckdb.connect(db, read_only=True)
    feats = CFG["model"]["features"]
    df = con.execute(f"""SELECT transaction_date, is_fraud::INT AS y, fraud_score, dayofweek(transaction_date) AS dow,
                         {', '.join(f for f in feats if f != 'dow')} FROM transactions ORDER BY transaction_date""").df()
    n = len(df)
    cut = int(n * CFG["split"]["train_fraction"])
    val_cut = int(cut * (1 - CFG["split"]["validation_fraction"]))
    cutoff, val_cutoff = df.transaction_date.iloc[cut], df.transaction_date.iloc[val_cut]
    part = np.where(np.arange(n) < val_cut, "train", np.where(np.arange(n) < cut, "val", "test"))
    y = df.y.to_numpy()
    has = df.fraud_score.notna().to_numpy()
    raw = (df.fraud_score.fillna(0) / 100).to_numpy()

    # ------------------------------------------------ (a) score crudo y (b) isotónica, sobre movimientos CON score
    fit = (part != "test") & has                                   # la isotónica no tiene hiperparámetros: usa train + val
    iso = IsotonicRegression(y_min=0, y_max=1, out_of_bounds="clip").fit(raw[fit], y[fit])
    cal = iso.predict(raw)
    val_s, test_s = (part == "val") & has, (part == "test") & has
    iso_tv = IsotonicRegression(y_min=0, y_max=1, out_of_bounds="clip").fit(raw[(part == "train") & has], y[(part == "train") & has])
    thr_cal = best_threshold(y[val_s], iso_tv.predict(raw[val_s]))      # umbral elegido en validación, con la isotónica de train
    # umbral robusto: punto medio entre la menor probabilidad priorizada y la mayor no priorizada (misma decisión, sin depender
    # de una igualdad exacta con 1,0)
    pv = iso_tv.predict(raw[val_s])
    thr_cal = float((pv[pv >= thr_cal].min() + (pv[pv < thr_cal].max() if (pv < thr_cal).any() else 0.0)) / 2)
    score_equiv = float(raw[has & (cal >= thr_cal)].min() * 100)          # a qué fraud_score equivale el umbral calibrado
    thr_raw_cost = best_threshold(y[val_s], raw[val_s])
    yt, rt, ct = y[test_s], raw[test_s], cal[test_s]
    rows_scored = {
        "Score crudo, banda alta actual (≥ 0,70)": decision(yt, rt >= CFG["bands"]["raw_high"]),
        f"Score crudo, umbral por costo (≥ {thr_raw_cost:.2f})": decision(yt, rt >= thr_raw_cost),
        f"Score calibrado (isotónica), umbral por costo (p ≥ {thr_cal:.4f})": decision(yt, ct >= thr_cal),
        "Nadie con prioridad (referencia)": decision(yt, np.zeros(len(yt), bool)),
    }
    metrics_scored = {"crudo": (average_precision_score(yt, rt), roc_auc_score(yt, rt), brier_score_loss(yt, rt)),
                      "calibrado": (average_precision_score(yt, ct), roc_auc_score(yt, ct), brier_score_loss(yt, ct))}

    # ------------------------------------------------ (c) modelo simple para movimientos SIN score
    import lightgbm as lgb
    X = df[feats].copy()
    cats = [c for c in feats if not pd.api.types.is_numeric_dtype(X[c])]
    for c in cats:
        X[c] = X[c].fillna("NA").astype("category")
    tr, va, te = part == "train", part == "val", part == "test"
    model = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=31, min_child_samples=200, subsample=0.8,
                               subsample_freq=1, colsample_bytree=0.8, random_state=CFG["model"]["seed"], verbose=-1)
    model.fit(X[tr], y[tr], eval_X=X[va], eval_y=y[va], eval_metric="average_precision",
              callbacks=[lgb.early_stopping(30, verbose=False)])
    p_model = model.predict_proba(X)[:, 1]
    test_ns, val_ns = te & ~has, va & ~has
    yn, pn = y[test_ns], p_model[test_ns]
    prevalence_ns = float(yn.mean())
    thr_model = best_threshold(y[val_ns], p_model[val_ns])
    rows_ns = {f"Modelo simple (LightGBM), umbral por costo (p ≥ {thr_model:.4f})": decision(yn, pn >= thr_model),
               "Hoy: banda `desconocido`, nadie con prioridad por riesgo": decision(yn, np.zeros(len(yn), bool))}
    ap_model, auc_model, brier_model = average_precision_score(yn, pn), roc_auc_score(yn, pn), brier_score_loss(yn, pn)
    ap_model_scored = average_precision_score(yt, p_model[test_s])        # ¿aporta algo donde SÍ hay score?
    importance = sorted(zip(feats, model.feature_importances_), key=lambda t: -t[1])[:5]
    model_useful = ap_model >= 3 * prevalence_ns and rows_ns[next(iter(rows_ns))]["cost_per_1000"] < rows_ns["Hoy: banda `desconocido`, nadie con prioridad por riesgo"]["cost_per_1000"]

    # ------------------------------------------------ artefacto: calibrador como puntos (score, probabilidad)
    xs = np.round(np.unique(np.concatenate([iso.X_thresholds_, [0.0, 1.0]])), 6)
    points = [[float(x), float(v)] for x, v in zip(xs, iso.predict(xs))]
    version = CFG["model"]["version"]
    MODELS.mkdir(parents=True, exist_ok=True)
    body = {"version": version, "trained_on": str(date.today()), "kind": "isotonic(fraud_score/100) -> P(is_fraud)",
            "points": points, "threshold_high": round(thr_cal, 6),
            "threshold_medium": round(thr_cal * CFG["bands"]["medium_fraction_of_high"], 6),
            "threshold_high_as_fraud_score": round(score_equiv, 2), "train_until": str(cutoff), "n_fit": int(fit.sum()), "n_fit_fraud": int(y[fit].sum()),
            "cost_assumptions": CFG["cost"], "command": "python -m ml.fraud_risk.experiment",
            "test": {"pr_auc": round(metrics_scored["calibrado"][0], 4), "brier": round(metrics_scored["calibrado"][2], 6)}}
    body["points_sha256"] = hashlib.sha256(json.dumps(points).encode()).hexdigest()
    (MODELS / f"{version}.json").write_text(json.dumps(body, indent=1) + "\n", encoding="utf-8")

    # ------------------------------------------------ figura
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.2))
    for name, p in (("score crudo / 100", rt), ("calibrado (isotónica)", ct)):
        rel = reliability(yt, p)
        ax[0].plot([r[0] for r in rel], [r[1] for r in rel], "o-", label=name)
    ax[0].plot([1e-5, 1], [1e-5, 1], "--", color="gray")
    ax[0].set(xscale="log", yscale="log", xlabel="probabilidad predicha (media del bin)", ylabel="fraude observado en el bin",
              title="¿La probabilidad de fraude es confiable? (prueba, con score)")
    ax[0].legend()
    grid = np.linspace(0.05, 0.99, 60)
    ax[1].plot(grid, [decision(yt, rt >= t)["cost_per_1000"] for t in grid])
    ax[1].axvline(CFG["bands"]["raw_high"], color="gray", ls="--", label="banda alta actual (0,70)")
    ax[1].axvline(thr_raw_cost, color="tab:red", ls=":", label=f"mínimo en validación ({thr_raw_cost:.2f})")
    ax[1].set(xlabel="umbral sobre fraud_score / 100", ylabel="costo esperado por 1.000 movimientos (USD)",
              title="¿Qué umbral cuesta menos? (supuestos del equipo)")
    ax[1].legend()
    fig.tight_layout()
    (EXP / "figures").mkdir(parents=True, exist_ok=True)
    fig.savefig(EXP / "figures" / "risk-calibracion-costo.png", dpi=110)

    # ------------------------------------------------ reporte
    def table(rows: dict) -> list[str]:
        out = ["| Opción | Enviados con prioridad | Fraudes detectados (recall) | Precisión | Costo esperado por 1.000 |", "|---|---|---|---|---|"]
        for name, d in rows.items():
            prec = frac(d["tp"], d["flag"]) if d["flag"] else "—"
            out.append(f"| {name} | {frac(d['flag'], d['n'])} | {frac(d['tp'], d['pos'])} | {prec} | ${d['cost_per_1000']:.2f} |")
        return out

    L = ["# EXP-20261001-risk-calibration · Riesgo: calibración y política", "",
         f"Generado por `python -m ml.fraud_risk.experiment` el {date.today()} (reproducible con ese comando sobre `data/bank.duckdb`). Issue #26.", "",
         "## Hipótesis", "",
         "1. Calibrar `fraud_score` (isotónica) da una probabilidad de fraude confiable y un umbral elegido por costo, mejor que las "
         "bandas fijas del score crudo.", "2. Un modelo simple con variables del movimiento puede dar una señal de riesgo al ~20 % de "
         "movimientos que no tienen `fraud_score`.", "",
         "## Datos y partición", "",
         f"- Etiqueta: `transactions.is_fraud` (columna del diccionario de datos; **sintética**). {frac(int(y.sum()), n)} de los movimientos.",
         f"- **Partición temporal** por `transaction_date`: entrenamiento hasta {str(val_cutoff)[:10]}, validación hasta {str(cutoff)[:10]} "
         f"(elegir umbrales), prueba después. Prueba: {f'{int(te.sum()):,}'.replace(',', '.')} movimientos, {int(y[te].sum())} fraudes.",
         f"- Sin `fraud_score`: {frac(int((~has).sum()), n)}. En prueba: {frac(int(test_ns.sum()), int(te.sum()))}, con {int(yn.sum())} fraudes.",
         f"- **¿La falta de score dice algo?** No: tasa de fraude {100 * y[has].mean():.3f} % con score y {100 * y[~has].mean():.3f} % sin "
         "score, en todo el dataset. La ausencia no es una señal; se trata como riesgo desconocido, no como riesgo bajo.",
         "- Sin atributos demográficos del cliente. Variables del modelo simple: " + ", ".join(f"`{f}`" for f in feats) + ".", "",
         "**Límite importante:** se mide sobre TODOS los movimientos, no sobre los que un cliente disputa. La política usa el riesgo "
         "solo en movimientos disputados, donde la proporción de fraude es mayor; los umbrales son un punto de partida.", "",
         "## Movimientos con score (prueba)", "",
         "| Señal | PR-AUC | ROC-AUC | Brier |", "|---|---|---|---|",
         f"| `fraud_score / 100` crudo | {metrics_scored['crudo'][0]:.4f} | {metrics_scored['crudo'][1]:.4f} | {metrics_scored['crudo'][2]:.6f} |",
         f"| Calibrado (isotónica) | {metrics_scored['calibrado'][0]:.4f} | {metrics_scored['calibrado'][1]:.4f} | {metrics_scored['calibrado'][2]:.6f} |", "",
         "La isotónica es monótona: no cambia el orden (PR-AUC y ROC-AUC casi iguales; las diferencias vienen de empates). Lo que "
         "cambia es la **confiabilidad**: el score crudo dividido por 100 no es una probabilidad (Brier mucho peor).", "",
         f"Supuestos de costo del equipo (`ml/fraud_risk/config.toml`): un fraude no priorizado cuesta ${C_FN:.0f}; un movimiento "
         f"legítimo enviado al equipo de fraude cuesta ${C_FP:.0f}. Umbrales elegidos en validación, medidos en prueba:", ""]
    L += table(rows_scored)
    L += ["", "![Confiabilidad y costo](figures/risk-calibracion-costo.png)", "",
          "## Movimientos sin score (prueba)", "",
          f"Prevalencia de fraude: {prevalence_ns * 100:.3f} % (una señal al azar tiene PR-AUC ≈ {prevalence_ns:.4f}).", "",
          "| Señal | PR-AUC | ROC-AUC | Brier |", "|---|---|---|---|",
          f"| Modelo simple (LightGBM, {model.best_iteration_ or model.n_estimators} árboles) | {ap_model:.4f} | {auc_model:.4f} | {brier_model:.6f} |", ""]
    L += table(rows_ns)
    L += ["", "Variables más usadas por el modelo: " + ", ".join(f"`{f}` ({int(v)})" for f, v in importance) + ". "
          f"Sobre los movimientos que SÍ tienen score, el modelo simple logra PR-AUC {ap_model_scored:.4f} frente a "
          f"{metrics_scored['crudo'][0]:.4f} del score: el score sigue siendo la señal.", "",
          "## Conclusión", "",
          f"1. **Calibración: sí.** El score calibrado es una probabilidad utilizable (Brier {metrics_scored['calibrado'][2]:.6f} frente a "
          f"{metrics_scored['crudo'][2]:.6f}) y el umbral por costo detecta "
          f"{frac(rows_scored[list(rows_scored)[2]]['tp'], rows_scored[list(rows_scored)[2]]['pos'])} de los fraudes con score frente a "
          f"{frac(rows_scored[list(rows_scored)[0]]['tp'], rows_scored[list(rows_scored)[0]]['pos'])} de la banda alta actual, con un costo esperado "
          f"de ${rows_scored[list(rows_scored)[2]]['cost_per_1000']:.2f} frente a ${rows_scored[list(rows_scored)[0]]['cost_per_1000']:.2f} por 1.000 movimientos. "
          f"Bajar a ojo el umbral del score crudo también sube el recall, pero con peor precisión ({frac(rows_scored[list(rows_scored)[1]]['tp'], rows_scored[list(rows_scored)[1]]['flag'])}); lo que aporta la calibración es poder razonar en "
          f"probabilidades y costos, no un mejor orden. En este dataset el calibrador es casi un escalón: el umbral equivale a "
          f"`fraud_score` ≥ {score_equiv:.1f}, por debajo del corte actual de 70 (y del 35 de la banda media).",
          ("2. **Modelo para movimientos sin score: sí aporta** (PR-AUC varias veces la prevalencia y menor costo esperado)."
           if model_useful else
           f"2. **Modelo para movimientos sin score: no mejora lo suficiente.** PR-AUC {ap_model:.4f} frente a una prevalencia de "
           f"{prevalence_ns:.4f}: las variables del movimiento casi no separan el fraude, y con el umbral de menor costo no baja el costo "
           "esperado frente a no priorizar. **No se integra**: esos movimientos siguen en la banda `desconocido`, con la regla actual "
           "(ofrecer el bloqueo; escalar si el monto es alto)."),
          "3. Todo depende de una etiqueta sintética y de costos supuestos. El riesgo solo cambia la ruta y la prioridad del caso.", ""]
    EXP.mkdir(exist_ok=True)
    (EXP / "EXP-20261001-risk-calibration.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[L.index("## Movimientos con score (prueba)"):]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
