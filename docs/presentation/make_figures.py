"""Figures for the slides, generated from the recorded results (nothing is typed by hand here).

    .venv/bin/python docs/presentation/make_figures.py

Where each number comes from (the script fails with a clear message if a source file or row is missing):
- risk-frauds-caught.png   docs/experiments/EXP-20261001-risk-calibration.md (results table) + models/risk/risk-v1.json
- intent-cascade.png       docs/experiments/EXP-20261001-intent-cascade.md (cross-validation and harness tables)
- all-llm-vs-system.png    eval/results/20260930-2139_comparacion_dev.md (eval.compare report)
- evaluation-api.png       eval/results/20261001-1355_comparacion_dev.md, eval/results/20261001-1601_comparacion_dev_paraphrase.md
                           and, for the last row, the newest eval/results/*_tabla_final.md written by scripts/final_eval.sh --final
                           (until that file exists, the row says "pending")
- roi-break-even.png       backend/config/roi.toml through backend.app.observability.admin_metrics.roi_numbers
"""
from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = Path(__file__).resolve().parent / "figures"
RISK_EXP = "docs/experiments/EXP-20261001-risk-calibration.md"
RISK_MODEL = "models/risk/risk-v1.json"
CASCADE_EXP = "docs/experiments/EXP-20261001-intent-cascade.md"
DESIGN = "eval/results/20260930-2139_comparacion_dev.md"
API_DEV = "eval/results/20261001-1355_comparacion_dev.md"
API_PARAPHRASE = "eval/results/20261001-1601_comparacion_dev_paraphrase.md"
ROI = "backend/config/roi.toml"

INK, MUTED, ACCENT, GREY = "#14213d", "#5c677d", "#2a9d8f", "#c9ced6"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 12, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.edgecolor": MUTED, "text.color": INK, "axes.labelcolor": INK, "xtick.color": INK, "ytick.color": INK})


# ------------------------------------------------------------------ reading the sources
def read(rel: str) -> str:
    path = ROOT / rel
    if not path.exists():
        raise SystemExit(f"missing source file: {rel} (needed by docs/presentation/make_figures.py)")
    return path.read_text(encoding="utf-8")


def cells(line: str) -> list[str]:
    return [c.strip().strip("*`").strip() for c in line.strip().strip("|").split("|")]


def table_row(rel: str, row_key: str, header_key: str) -> dict[str, str]:
    """The row whose first cells contain `row_key`, from the first Markdown table whose header contains `header_key`,
    as {header: cell}."""
    lines = read(rel).splitlines()
    for i, line in enumerate(lines):
        if line.startswith("|") and header_key in line and i + 1 < len(lines) and set(lines[i + 1]) <= set("|-: "):
            header = cells(line)
            for row in lines[i + 2:]:
                if not row.startswith("|"):
                    break
                if row_key in row:
                    return dict(zip(header, cells(row)))
    raise SystemExit(f"{rel}: no row '{row_key}' in a table with a '{header_key}' column")


def frac(text: str) -> tuple[int, int]:
    """'1.082/708.054 (0.15 %)' → (1082, 708054). Thousands separators are dots in the Spanish reports."""
    m = re.search(r"([\d.]+)/([\d.]+)", text)
    if not m:
        raise SystemExit(f"cannot read a fraction from '{text}'")
    return int(m.group(1).replace(".", "")), int(m.group(2).replace(".", ""))


def usd(text: str) -> float:
    m = re.search(r"\$([\d.]+)", text)
    if not m:
        raise SystemExit(f"cannot read an amount from '{text}'")
    return float(m.group(1))


def latency(text: str) -> tuple[str, str]:
    """'1.5 s / 4.6 s' or '1,4 s / 4,4 s' → ('1.5 s', '4.6 s')."""
    p50, p95 = (x.strip().replace(",", ".") for x in text.split("/"))
    return p50, p95


def run_date(rel: str) -> str:
    m = re.search(r"·\s*(\d{4}-\d{2}-\d{2})", read(rel).splitlines()[0])
    if not m:
        raise SystemExit(f"{rel}: no run date in the title")
    return m.group(1)


def save(fig, name: str, source: str) -> None:
    fig.text(0.01, -0.04, f"Source: {source}", fontsize=8, color=MUTED, ha="left", va="top")   # below everything
    fig.savefig(OUT / name, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def three_panels(title: str, names: list[str], panels: list[tuple[str, list[float], list[str]]]):
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.9))
    for ax, (panel_title, values, labels) in zip(axes, panels):
        bars = ax.bar(names, values, color=[GREY, ACCENT], width=0.55)
        for b, label in zip(bars, labels):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height(), label, ha="center", va="bottom", fontsize=11)
        ax.set_ylim(0, max(values) * 1.28)
        ax.set_yticks([])
        ax.spines["left"].set_visible(False)
        ax.set_title(panel_title, fontsize=12, loc="left")
    fig.suptitle(title, x=0.01, ha="left", fontweight="bold")
    fig.tight_layout(rect=(0, 0.04, 1, 0.94))
    return fig


# ------------------------------------------------------------------ figures
def risk() -> None:
    model = json.loads(read(RISK_MODEL))
    before = table_row(RISK_EXP, "banda alta actual", "Fraudes detectados")
    after = table_row(RISK_EXP, "Score calibrado", "Fraudes detectados")
    rows = [("Previous band\n(score ≥ 70)", before), (f"{model['version']}\n(calibrated, cost-based threshold)", after)]
    caught = [frac(r["Fraudes detectados (recall)"]) for _, r in rows]
    precision = [frac(r["Precisión"]) for _, r in rows]
    total = caught[0][1]
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    bars = ax.bar([label for label, _ in rows], [n for n, _ in caught], color=[GREY, ACCENT], width=0.55)
    ax.axhline(total, color=MUTED, linestyle="--", linewidth=1)
    ax.text(1.42, total, f"{total} frauds with a score", va="center", ha="right", fontsize=10, color=MUTED, backgroundcolor="white")
    for b, (n, d), (pn, pd) in zip(bars, caught, precision):
        ax.text(b.get_x() + b.get_width() / 2, n + total * 0.02, f"{n}/{d} ({n / d:.1%})\nprecision {pn}/{pd}", ha="center", va="bottom", fontsize=11)
    ax.set_ylim(0, total * 1.23)
    ax.set_ylabel("Frauds routed to the fraud team")
    ax.set_title("Fraud risk: frauds caught in the held-out period", loc="left", fontweight="bold")
    save(fig, "risk-frauds-caught.png", f"{RISK_EXP.split('/')[-1]} and {RISK_MODEL} (trained {model['trained_on']}; synthetic dataset)")


def cascade() -> None:
    llm = table_row(CASCADE_EXP, "Haiku (solo LLM)", "Macro-F1")
    casc = table_row(CASCADE_EXP, "Cascada", "Macro-F1")
    acc_key, to_llm_key = list(llm)[1], list(llm)[3]
    acc = [frac(llm[acc_key]), frac(casc[acc_key])]
    to_llm = [frac(llm[to_llm_key]), frac(casc[to_llm_key])]
    api = table_row(CASCADE_EXP, "`sistema_api`", "Costo por caso")
    api_c = table_row(CASCADE_EXP, "`sistema_cascade`", "Costo por caso")
    costs = [usd(api["Costo por caso"]), usd(api_c["Costo por caso"])]
    n_cases = frac(api["Pasan todo"])[1]
    fig = three_panels("Intent cascade: a small local classifier first, the LLM only when unsure", ["LLM only", "Cascade"], [
        ("Intent accuracy\n(cross-validation)", [n / d for n, d in acc], [f"{n}/{d}" for n, d in acc]),
        ("Turns that reach the LLM\n(cross-validation)", [n / d for n, d in to_llm], [f"{n}/{d}" + ("" if n == d else f" ({n / d:.1%})") for n, d in to_llm]),
        (f"Cost per case\n(API, dev, {n_cases} cases)", costs, [f"${c:.4f}" for c in costs])])
    save(fig, "intent-cascade.png", f"{CASCADE_EXP.split('/')[-1]}. Latency did not improve; dev is contaminated for the cascade, hence the CV numbers")


def design() -> None:
    rows = [table_row(DESIGN, "`claude_cli`", "Pasan todo"), table_row(DESIGN, "`sistema`", "Pasan todo")]
    passed = [frac(r["Pasan todo"]) for r in rows]
    unsafe = [frac(r["Inseguros"]) for r in rows]
    lat = [latency(r["Latencia/turno p50 / p95"]) for r in rows]
    costs = [usd(r["Costo por caso"]) for r in rows]
    reps = int(rows[0]["Rep."])
    fig = three_panels("Templates and code where the LLM adds nothing: same safety, faster and cheaper", ["All-LLM", "System"], [
        ("Pass all checks / unsafe", [n / d for n, d in passed], [f"{n}/{d}\n{u} unsafe" for (n, d), (u, _) in zip(passed, unsafe)]),
        ("Latency per turn, p50 (p95)", [float(p50.split()[0]) for p50, _ in lat], [f"{p50} ({p95})" for p50, p95 in lat]),
        ("Cost per case", costs, [f"${c:.4f}" for c in costs])])
    save(fig, "all-llm-vs-system.png", f"{DESIGN.split('/')[-1]} ({run_date(DESIGN)}, dev, {passed[0][1] // reps} cases x {reps} repeats), "
                                       "both with the local CLI (claude -p): relative comparison, not production figures")


def final_row() -> tuple[list[str], str]:
    """Last row of the evaluation table: the frozen test from the newest final table of scripts/final_eval.sh --final."""
    finals = sorted((ROOT / "eval/results").glob("*_tabla_final.md"))
    if not finals:
        return ["hand-written test (frozen), final API run", "pending", "pending", "pending", "pending"], "final run pending (scripts/final_eval.sh --final)"
    rel = str(finals[-1].relative_to(ROOT))
    text = read(rel)
    if "### Split `test`" not in text:
        raise SystemExit(f"{rel}: the final table has no test split (was the hand-written test imported before the final run?)")
    section = text.split("### Split `test`", 1)[1].split("###", 1)[0]
    line = next((x for x in section.splitlines() if x.startswith("|") and "Sistema (API)" in x), None)
    if line is None:
        raise SystemExit(f"{rel}: no 'Sistema (API)' row in the test split")
    c = cells(line)
    (n, d), (u, ud), (p50, p95) = frac(c[1]), frac(c[2]), latency(c[5])
    day = re.match(r"(\d{4})(\d{2})(\d{2})", finals[-1].name)
    date = "-".join(day.groups()) if day else "?"
    return [f"hand-written test (frozen), {d} cases, API run {date}", f"{n}/{d}", f"{u}/{ud}", f"{p50} / {p95}", c[6]], rel


def api() -> None:
    rows = []
    for rel, label in ((API_DEV, "dev"), (API_PARAPHRASE, "paraphrased dev")):
        r = table_row(rel, "`sistema_api`", "Pasan todo")
        (n, d), (u, ud), (p50, p95) = frac(r["Pasan todo"]), frac(r["Inseguros"]), latency(r["Latencia/turno p50 / p95"])
        rows.append([f"{label}, {d} cases, API run {run_date(rel)}", f"{n}/{d}", f"{u}/{ud}", f"{p50} / {p95}", f"${usd(r['Costo por caso']):.4f}"])
    last, last_source = final_row()
    rows.append(last)
    fig, ax = plt.subplots(figsize=(11.5, 2.6))
    ax.axis("off")
    table = ax.table(cellText=rows, colLabels=["System, Claude API", "Pass all", "Unsafe", "Latency p50 / p95", "Cost per case"],
                     loc="center", cellLoc="center", colWidths=[0.46, 0.11, 0.10, 0.18, 0.15])
    table.auto_set_font_size(False)
    table.set_fontsize(11)
    table.scale(1, 1.9)
    pending = last[1] == "pending"
    for (r, c), cell in table.get_celld().items():
        cell.set_edgecolor(GREY)
        if r == 0:
            cell.set_facecolor(INK)
            cell.set_text_props(color="white", fontweight="bold")
        elif r == len(rows) and pending:
            cell.set_text_props(color=MUTED, style="italic")
        elif c in (1, 2):
            cell.set_text_props(fontweight="bold", color=ACCENT)
    ax.set_title("Measured with deterministic checkers (no LLM judge)", loc="left", fontweight="bold")
    save(fig, "evaluation-api.png", f"{API_DEV.split('/')[-1]}, {API_PARAPHRASE.split('/')[-1]}; last row: {last_source}. "
                                    "Each row is the case set as it was on that date")


def roi() -> None:
    from backend.app.observability.admin_metrics import roi_numbers      # the same calculation as the endpoint and analytics.md
    a = tomllib.loads(read(ROI))["assumptions"]
    r = roi_numbers(a)
    break_even, assumed = r["break_even_cases_per_month"], a["cases_per_month"]
    if not break_even:
        raise SystemExit(f"{ROI}: with these assumptions there is no saving per case, so there is no break-even point")
    xs = [0, max(assumed, break_even * 2) * 1.1]
    net = [x * r["saving_per_case_usd"] - a["fixed_monthly_cost_usd"] for x in xs]
    at_assumed = assumed * r["saving_per_case_usd"] - a["fixed_monthly_cost_usd"]
    fig, ax = plt.subplots(figsize=(8.5, 4.4))
    ax.plot(xs, net, color=ACCENT, linewidth=2.5)
    ax.axhline(0, color=MUTED, linewidth=1)
    ax.scatter([break_even], [0], color=INK, zorder=3)
    ax.annotate(f"break-even: {break_even:,} cases / month", (break_even, 0), xytext=(break_even + xs[1] * 0.10, -at_assumed * 0.13),
                arrowprops={"arrowstyle": "-", "color": MUTED}, fontsize=11)
    at = assumed * r["saving_per_case_usd"] - a["fixed_monthly_cost_usd"]
    ax.scatter([assumed], [at], color=ACCENT, zorder=3)
    ax.annotate(f"{assumed:,} cases / month (assumed)\n≈ ${at:,.0f} / month", (assumed, at), xytext=(assumed * 0.52, at * 0.93), fontsize=11)
    ax.set_ylim(bottom=-at_assumed * 0.2)             # room for the break-even label under the zero line
    ax.set_xlabel("Cases per month")
    ax.set_ylabel("Estimated net saving per month (USD)")
    ax.xaxis.set_major_formatter(lambda x, _: f"{x:,.0f}")
    ax.yaxis.set_major_formatter(lambda y, _: f"-${-y:,.0f}" if y < 0 else f"${y:,.0f}")
    ax.set_title("ROI: an estimate with explicit assumptions, not a result", loc="left", fontweight="bold")
    note = (f"Assumptions: ${a['agent_cost_per_minute_usd']:.2f} per agent minute · {a['minutes_per_case_human']} min per case (measured in the dataset) · "
            f"{a['automatable_share']:.0%} of cases not reaching a person\n"
            f"${a['llm_cost_per_case_usd']:.4f} LLM cost per case (measured, API) · ${a['fixed_monthly_cost_usd']:,.2f} fixed cost per month · "
            f"saving per case ${r['saving_per_case_usd']:.2f} (human-handled case: ${r['human_cost_per_case_usd']:.2f})")
    fig.text(0.01, -0.02, note.replace("$", r"\$"), fontsize=9, color=INK, ha="left", va="top")   # "$" literal, no mathtext
    fig.text(0.01, -0.13, f"Source: {ROI} (team assumptions, editable) and roi_numbers(); same numbers as docs/analytics.md §4", fontsize=8, color=MUTED, ha="left", va="top")
    fig.savefig(OUT / "roi-break-even.png", dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for make in (risk, cascade, design, api, roi):
        make()
    print("\n".join(sorted(p.name for p in OUT.glob("*.png"))))
