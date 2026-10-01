"""Kit para el test escrito a mano: N fichas de escenario para redactores que no ven el código.

    .venv/bin/python scripts/make_writer_kit.py --n 40            # 20 es + 20 pt, balanceadas por categoría
    .venv/bin/python scripts/make_writer_kit.py --format md       # Markdown en vez de HTML

- Cada ficha: el escenario en una frase, el nombre visible del cliente, sus movimientos recientes (comercio, monto,
  fecha, estado) con el cargo objetivo marcado, y el resultado esperado. Sin IDs del dataset.
- Las fichas van a eval/manual/fichas/ (fuera de git: muestran datos del dataset). La asignación ficha → escenario,
  idioma, selector, pick y fecha de sesión queda en eval/manual/assignments.json (versionado, sin IDs), y es lo que
  usa `python -m eval.import_manual` para convertir el CSV de los redactores en casos del split test.
- Los clientes de las fichas no se repiten entre sí ni con los casos de dev (se saltan los picks cuyo cliente ya se usó).
- Si assignments.json ya existe, se reutiliza (regenerar las fichas no cambia la asignación); --reassign la rehace.
"""
from __future__ import annotations

import argparse
import asyncio
import html
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

from backend.app.controller.blocks import CARD_LABEL, fmt_date, fmt_money, tx_label  # noqa: E402
from backend.app.llm.nodes import STATUS_LABEL  # noqa: E402
from eval.cases.schema import load_cases  # noqa: E402
from eval.cases.selectors import SELECTORS, resolve  # noqa: E402
from eval.harness.env import eval_urls, plain  # noqa: E402
from eval.manual.scenarios import BY_KEY, CATEGORIES, SCENARIOS  # noqa: E402

MANUAL = ROOT / "eval" / "manual"
ASSIGN = MANUAL / "assignments.json"
FIRST_PICK = 0
LANG_NAME = {"es": "español (como escribiría un cliente de México, Colombia, Argentina u otro país hispanohablante)",
             "pt": "portugués de Brasil"}


def plan(n: int) -> list[tuple[str, str]]:
    """(escenario, idioma) intercalando categorías e idiomas: con n = 2 × escenarios, cada uno una vez por idioma."""
    by_cat = {c: [s for s in SCENARIOS if s.category == c] for c in CATEGORIES}
    order, i = [], 0
    while len(order) < n:
        for lang in ("es", "pt"):
            for c in CATEGORIES:
                scen = by_cat[c][(i + (lang == "pt")) % len(by_cat[c])]    # es y pt rotan desfasados
                if len(order) < n:
                    order.append((scen.key, lang))
        i += 1
    return order


async def dev_customers(urls, sd: date) -> set[str]:
    eng = create_async_engine(urls["admin"])
    out = set()
    try:
        async with eng.connect() as c:
            for case in load_cases("dev"):
                try:
                    out.add((await resolve(c, case.selector, case.pick, case.session_date or sd))["customer_id"])
                except LookupError:
                    pass
    finally:
        await eng.dispose()
    return out


async def assign(n: int, urls, sd: date) -> list[dict]:
    used = await dev_customers(urls, sd)
    next_pick = {k: FIRST_PICK for k in SELECTORS}
    eng = create_async_engine(urls["admin"])
    out = []
    try:
        async with eng.connect() as c:
            for i, (key, lang) in enumerate(plan(n), 1):
                sel = BY_KEY[key].selector
                while True:
                    r = await resolve(c, sel, next_pick[sel], sd)       # LookupError si se agota el selector
                    next_pick[sel] += 1
                    if r["customer_id"] not in used:
                        used.add(r["customer_id"])
                        break
                out.append({"ficha_id": f"F{i:02d}", "scenario": key, "category": BY_KEY[key].category, "language": lang,
                            "selector": sel, "pick": next_pick[sel] - 1, "session_date": sd.isoformat()})
    finally:
        await eng.dispose()
    return out


def movements(conn, r: dict, sd: date) -> list[dict]:
    """Movimientos del cliente: los 8 más recientes de la ventana de 120 días + el objetivo y el parecido si quedaron fuera."""
    q = """SELECT transaction_id, transaction_date, amount, currency, merchant_name, transaction_category, transaction_type,
                  transaction_status FROM ref.transactions WHERE customer_id = %s
           AND transaction_date >= %s::date - 120 AND transaction_date < %s::date + 1 ORDER BY transaction_date DESC LIMIT 8"""
    rows = conn.execute(q, (r["customer_id"], sd, sd)).fetchall()
    have = {x["transaction_id"] for x in rows}
    for key in ("target", "second"):
        if r.get(key) and r[key]["transaction_id"] not in have:
            rows.append({k: r[key][k] for k in rows[0]} if rows else r[key])
    return sorted(rows, key=lambda x: x["transaction_date"], reverse=True)


def render(a: dict, r: dict, conn, sd: date, fmt: str) -> str:
    s, lang = BY_KEY[a["scenario"]], a["language"]
    name = conn.execute("SELECT display_name FROM ref.customers WHERE customer_id = %s", (r["customer_id"],)).fetchone()["display_name"]
    cards = conn.execute("""SELECT product_type FROM ref.products WHERE customer_id = %s AND product_status = 'Active'
                            AND product_type IN ('Tarjeta Crédito', 'Tarjeta Débito') ORDER BY product_type""", (r["customer_id"],)).fetchall()
    target = (r.get("target") or {}).get("transaction_id") if s.pick_target else None
    second = (r.get("second") or {}).get("transaction_id") if s.show_second else None
    rows = []
    for t in movements(conn, r, sd):
        mark = "◀ ESTE es el cargo del escenario" if t["transaction_id"] == target else (
            "parecido, NO es el que reclamas" if t["transaction_id"] == second else "")
        rows.append((tx_label(t, lang), fmt_money(t["amount"], t["currency"], lang), fmt_date(t["transaction_date"], lang),
                     STATUS_LABEL[lang].get(t["transaction_status"], t["transaction_status"]), mark))
    card_txt = ", ".join(f"tarjeta de {CARD_LABEL['es'].get(c['product_type'], c['product_type'])}" for c in cards) or "ninguna tarjeta activa"
    head = [("Ficha", a["ficha_id"]), ("Idioma en que escribes", LANG_NAME[lang]), ("Categoría", s.category),
            ("Escenario", s.sentence), ("Eres", f"{name} (así te saluda el asistente)"), ("Tus tarjetas activas", card_txt),
            ("\"Hoy\" es", fmt_date(sd, "es"))]
    if s.hint:
        head.append(("Indicación", s.hint))
    head.append(("Resultado esperado", s.expected_text))
    cols = ("Comercio", "Monto", "Fecha", "Estado", "")
    if fmt == "md":
        out = [f"# Ficha {a['ficha_id']}", ""] + [f"- **{k}:** {v}" for k, v in head[1:]]
        out += ["", "## Tus movimientos recientes", "", "| " + " | ".join(cols) + " |", "|---|---|---|---|---|"]
        out += ["| " + " | ".join(f"**{x}**" if row[4].startswith("◀") else x for x in row) + " |" for row in rows]
        out += ["", "Escribe tus mensajes en eval/manual/template.csv (una fila por mensaje) con este id de ficha. "
                "Instrucciones: eval/manual/README.md."]
        return "\n".join(out) + "\n"
    e = html.escape
    trs = "".join(f"<tr class='{'target' if row[4].startswith('◀') else 'second' if row[4] else ''}'>" +
                  "".join(f"<td>{e(x)}</td>" for x in row) + "</tr>" for row in rows)
    dl = "".join(f"<dt>{e(k)}</dt><dd>{e(v)}</dd>" for k, v in head[1:])
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ficha {e(a['ficha_id'])}</title><style>
body{{font:16px/1.45 system-ui,sans-serif;max-width:760px;margin:24px auto;padding:0 16px;color:#1d1d1f;background:#fff}}
h1{{font-size:24px;margin:0 0 12px}} dl{{display:grid;grid-template-columns:max-content 1fr;gap:6px 16px;margin:0 0 20px}}
dt{{font-weight:600;color:#555}} dd{{margin:0}} table{{border-collapse:collapse;width:100%}}
td,th{{border-bottom:1px solid #ddd;padding:6px 8px;text-align:left;font-size:15px}} tr.target{{background:#fff3c4;font-weight:600}}
tr.second{{background:#eef3ff}} footer{{margin-top:20px;color:#666;font-size:14px}}
@media print{{body{{margin:0}}}}</style></head><body>
<h1>Ficha {e(a['ficha_id'])}</h1><dl>{dl}</dl><h2>Tus movimientos recientes</h2>
<table><thead><tr>{''.join(f'<th>{c}</th>' for c in cols)}</tr></thead><tbody>{trs}</tbody></table>
<footer>Escribe tus mensajes en <code>eval/manual/template.csv</code>, una fila por mensaje, con el id <b>{e(a['ficha_id'])}</b>.
Instrucciones: <code>eval/manual/README.md</code>.</footer></body></html>
"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="scripts/make_writer_kit.py")
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--format", choices=["html", "md"], default="html")
    ap.add_argument("--out", type=Path, default=MANUAL / "fichas")
    ap.add_argument("--reassign", action="store_true")
    a = ap.parse_args(argv)
    urls = eval_urls()
    with psycopg.connect(plain(urls["admin"]), row_factory=dict_row) as conn:
        sd = conn.execute("SELECT max(transaction_date)::date AS d FROM ref.transactions").fetchone()["d"]
        if ASSIGN.exists() and not a.reassign:
            assignments = json.loads(ASSIGN.read_text(encoding="utf-8"))["fichas"]
            print(f"reutilizo {ASSIGN.relative_to(ROOT)} ({len(assignments)} fichas); --reassign para rehacerla")
        else:
            assignments = asyncio.run(assign(a.n, urls, sd))
            ASSIGN.write_text(json.dumps({"generated_by": "scripts/make_writer_kit.py", "n": len(assignments), "fichas": assignments},
                                         ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        a.out.mkdir(parents=True, exist_ok=True)
        eng_loop = asyncio.new_event_loop()
        eng = create_async_engine(urls["admin"])

        async def res(x):
            async with eng.connect() as c:
                return await resolve(c, x["selector"], x["pick"], date.fromisoformat(x["session_date"]))
        index = []
        for x in assignments:
            r = eng_loop.run_until_complete(res(x))
            text = render(x, r, conn, date.fromisoformat(x["session_date"]), a.format)
            path = a.out / f"{x['ficha_id']}.{a.format}"
            path.write_text(text, encoding="utf-8")
            index.append((x["ficha_id"], x["language"], x["category"], BY_KEY[x["scenario"]].sentence, path.name))
        eng_loop.run_until_complete(eng.dispose())
        eng_loop.close()
    if a.format == "html":
        lis = "".join(f"<li><a href='{p}'>{i}</a> · {lg} · {c} · {html.escape(s)}</li>" for i, lg, c, s, p in index)
        (a.out / "index.html").write_text(f"<!doctype html><meta charset='utf-8'><title>Fichas</title><body style='font:16px system-ui;"
                                          f"max-width:760px;margin:24px auto;padding:0 16px'><h1>Fichas de redacción</h1><ol>{lis}</ol>",
                                          encoding="utf-8")
    from collections import Counter
    print(f"{len(index)} fichas en {a.out}: idioma {dict(Counter(i[1] for i in index))}, "
          f"categoría {dict(Counter(i[2] for i in index))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
