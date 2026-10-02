"""Figures for the slides. Every number is copied from a recorded run or document (source next to it); nothing is computed
from the dataset here, so the script runs anywhere:  .venv/bin/python docs/presentation/make_figures.py"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

OUT = Path(__file__).resolve().parent / "figures"
INK, MUTED, ACCENT, GREY = "#14213d", "#5c677d", "#2a9d8f", "#c9ced6"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 12, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.edgecolor": MUTED, "text.color": INK, "axes.labelcolor": INK, "xtick.color": INK, "ytick.color": INK})


def save(fig, name: str, source: str) -> None:
    fig.text(0.01, -0.04, f"Source: {source}", fontsize=8, color=MUTED, ha="left", va="top")   # debajo de todo: no pisa los ejes
    fig.savefig(OUT / name, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def risk() -> None:
    # docs/experiments/EXP-20261001-risk-calibration.md: held-out period, 620 frauds with a score
    labels, caught, precision = ["Previous band\n(score ≥ 70)", "risk-v1\n(calibrated, cost-based threshold)"], [182, 446], ["182/182", "446/446"]
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    bars = ax.bar(labels, caught, color=[GREY, ACCENT], width=0.55)
    ax.axhline(620, color=MUTED, linestyle="--", linewidth=1)
    ax.text(1.42, 620, "620 frauds with a score", va="center", ha="right", fontsize=10, color=MUTED, backgroundcolor="white")
    for b, n, p in zip(bars, caught, precision):
        ax.text(b.get_x() + b.get_width() / 2, n + 12, f"{n}/620 ({n / 620:.1%})\nprecision {p}", ha="center", va="bottom", fontsize=11)
    ax.set_ylim(0, 760)
    ax.set_ylabel("Frauds routed to the fraud team")
    ax.set_title("Fraud risk: frauds caught in the held-out period", loc="left", fontweight="bold")
    save(fig, "risk-frauds-caught.png", "EXP-20261001-risk-calibration (synthetic dataset; 217-day test period)")


def cascade() -> None:
    # docs/experiments/EXP-20261001-intent-cascade.md: 5-fold grouped CV (187 messages); harness with the API on dev (81 cases)
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.9))
    names, colors = ["LLM only", "Cascade"], [GREY, ACCENT]
    for ax, title, values, fmt, top in (
            (axes[0], "Intent accuracy\n(cross-validation)", [183 / 187, 183 / 187], ["183/187", "183/187"], 1.18),
            (axes[1], "Turns that reach the LLM\n(cross-validation)", [1.0, 26 / 187], ["187/187", "26/187 (13.9%)"], 1.18),
            (axes[2], "Cost per case\n(API, dev, 81 cases)", [0.0072, 0.0044], ["$0.0072", "$0.0044"], 0.0088)):
        bars = ax.bar(names, values, color=colors, width=0.55)
        for b, label in zip(bars, fmt):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height(), label, ha="center", va="bottom", fontsize=11)
        ax.set_ylim(0, top)
        ax.set_yticks([])
        ax.spines["left"].set_visible(False)
        ax.set_title(title, fontsize=12, loc="left")
    fig.suptitle("Intent cascade: a small local classifier first, the LLM only when unsure", x=0.01, ha="left", fontweight="bold")
    fig.tight_layout(rect=(0, 0.04, 1, 0.94))
    save(fig, "intent-cascade.png", "EXP-20261001-intent-cascade. Latency did not improve; dev is contaminated for the cascade, hence the CV numbers")


def design() -> None:
    # eval/results/20260930-2139_comparacion_dev.md: dev (50 cases x 3 repeats), both variants with claude -p (local CLI)
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.9))
    names, colors = ["All-LLM", "System"], [GREY, ACCENT]
    for ax, title, values, fmt, top in (
            (axes[0], "Pass all checks / unsafe", [1.0, 1.0], ["150/150\n0 unsafe", "150/150\n0 unsafe"], 1.3),
            (axes[1], "Latency per turn, p50 (p95)", [7.5, 3.9], ["7.5 s (19.8 s)", "3.9 s (13.0 s)"], 9.5),
            (axes[2], "Cost per case", [0.0218, 0.0151], ["$0.0218", "$0.0151"], 0.027)):
        bars = ax.bar(names, values, color=colors, width=0.55)
        for b, label in zip(bars, fmt):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height(), label, ha="center", va="bottom", fontsize=11)
        ax.set_ylim(0, top)
        ax.set_yticks([])
        ax.spines["left"].set_visible(False)
        ax.set_title(title, fontsize=12, loc="left")
    fig.suptitle("Templates and code where the LLM adds nothing: same safety, faster and cheaper", x=0.01, ha="left", fontweight="bold")
    fig.tight_layout(rect=(0, 0.04, 1, 0.94))
    save(fig, "all-llm-vs-system.png", "comparison 2026-09-30, dev, 3 repeats, both with the local CLI (claude -p): relative comparison, not production figures")


def api() -> None:
    # docs/llm-data.md (checkpoint 1) and eval/results/20261001-1601_comparacion_dev_paraphrase.md: system with the Claude API
    rows = [("dev (60 cases)", "60/60", "0/60", "1.5 s / 4.6 s", "$0.0079"),
            ("paraphrased dev (96 cases)", "96/96", "0/96", "1.4 s / 4.5 s", "$0.0073"),
            ("hand-written test (frozen)", "TBD", "TBD", "TBD", "TBD")]
    fig, ax = plt.subplots(figsize=(10.5, 2.6))
    ax.axis("off")
    table = ax.table(cellText=rows, colLabels=["System, Claude API", "Pass all", "Unsafe", "Latency p50 / p95", "Cost per case"],
                     loc="center", cellLoc="center", colWidths=[0.34, 0.14, 0.12, 0.22, 0.18])
    table.auto_set_font_size(False)
    table.set_fontsize(11)
    table.scale(1, 1.9)
    for (r, c), cell in table.get_celld().items():
        cell.set_edgecolor(GREY)
        if r == 0:
            cell.set_facecolor(INK)
            cell.set_text_props(color="white", fontweight="bold")
        elif r == 3:
            cell.set_text_props(color=MUTED, style="italic")
        elif c in (1, 2):
            cell.set_text_props(fontweight="bold", color=ACCENT)
    ax.set_title("Measured with 18 deterministic checkers (no LLM judge)", loc="left", fontweight="bold")
    save(fig, "evaluation-api.png", "checkpoint 1 (docs/llm-data.md) and comparison 2026-10-01 (paraphrase). Final row: scripts/final_eval.sh --final")


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for make in (risk, cascade, design, api):
        make()
    print("\n".join(sorted(p.name for p in OUT.glob("*.png"))))
