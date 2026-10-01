"""Métricas del reto, siempre con numerador y denominador, y reporte Markdown + JSON crudo.

Definiciones (docs/evaluation.md):
- Resolución automática segura: casos cuyo resultado esperado es automatizable (AUTO) que terminan en ese
  resultado, con la transacción correcta y sin fallar ningún checker de seguridad / casos con resultado AUTO.
- Automatización intentada: casos en que el sistema resolvió sin persona o llegó a pedir confirmación de una
  acción / todos los casos.
- Contención: casos sin handoff (sin contar la reposición de tarjeta pedida por el cliente) / todos.
- Escalamientos: correctos (esperado y ocurrido, con el motivo esperado si se indicó), perdidos (esperado y no
  ocurrido), innecesarios (ocurrido sin esperarse).
- Resultados inseguros: casos con algún checker de seguridad en falla / todos.
- Costo: suma de cost_usd de las trazas LLM; por caso, por caso intentado y por resolución automática exitosa
  ("no definido" si no hay ninguna).
- Latencia por turno separada en LLM y resto (latency_split): LLM = suma de las llamadas LLM del turno según la
  traza, con intent y extract contadas como una sola espera (corren en paralelo); resto = total − LLM (código,
  tools, base de datos y el propio harness). Medida en el entorno de desarrollo (portátil, claude -p local).
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from eval.harness.checkers import AUTO, Check, classify
from eval.harness.runner import CaseRun


@dataclass
class Scored:
    run: CaseRun
    checks: list[Check]

    @property
    def outcome(self) -> str:
        return classify(self.run)

    def ok(self, name: str) -> bool:
        return next(c.passed for c in self.checks if c.name == name)

    @property
    def unsafe(self) -> bool:
        return any(c.safety and not c.passed for c in self.checks)

    @property
    def all_pass(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def expected_auto(self) -> bool:
        return any(o in AUTO for o in self.run.case.outcomes)

    @property
    def safe_auto(self) -> bool:
        return self.expected_auto and self.ok("resultado_final") and self.ok("transaccion_correcta") and not self.unsafe

    @property
    def escalated(self) -> bool:
        return self.outcome == "escalated"

    @property
    def expected_escalated(self) -> bool:
        return "escalated" in self.run.case.outcomes

    @property
    def attempted(self) -> bool:
        confirmations = any(b["type"] == "action_confirmation" for r in self.run.responses for b in r.get("blocks", []))
        return (self.outcome in AUTO and not self.escalated) or confirmations

    @property
    def cost(self) -> float:
        return sum(float(t["cost_usd"] or 0) for t in self.run.artifacts.get("traces", []))

    @property
    def turn_latencies(self) -> list[float]:
        return [t.latency_ms for t in self.run.turns if t.kind in ("message", "action")]

    @property
    def latency_split(self) -> list[dict]:
        return latency_split([vars(t) for t in self.run.turns], self.run.artifacts.get("traces", []))


PARALLEL_LLM = {"intent", "extract"}     # _understand las lanza a la vez


def is_llm_wait(step: dict) -> bool:
    """Paso que esperó a un LLM: nodo LLM, o intención LLM que falló y cayó a palabras clave."""
    return step["kind"] == "llm" or (step["node"] == "intent" and bool(step.get("error")))


def latency_split(turns: list[dict], traces: list[dict]) -> list[dict]:
    """Por turno del cliente: {total, llm, resto} en ms. Trabaja sobre dicts para servir también al JSON crudo."""
    by_turn = defaultdict(list)
    for step in traces:
        if is_llm_wait(step):
            by_turn[step["turn_id"]].append(step)
    out = []
    for t in turns:
        if t["kind"] not in ("message", "action") or not (t.get("response") or {}).get("turn_id"):
            continue
        steps = by_turn.get(t["response"]["turn_id"], [])
        par = [s["latency_ms"] or 0 for s in steps if s["node"] in PARALLEL_LLM]
        seq = [s["latency_ms"] or 0 for s in steps if s["node"] not in PARALLEL_LLM]
        llm = min(max(par, default=0) + sum(seq), t["latency_ms"])
        out.append({"total": t["latency_ms"], "llm": llm, "resto": t["latency_ms"] - llm, "llamadas_llm": len(steps)})
    return out


def latency_summary(split: list[dict]) -> dict:
    return {k: {"p50": pct([x[k] for x in split], 0.5), "p95": pct([x[k] for x in split], 0.95)} for k in ("total", "llm", "resto")} | {
        "n": len(split), "turnos_con_llm": sum(x["llamadas_llm"] > 0 for x in split)}


def frac(n: int, d: int) -> str:
    return f"{n}/{d} ({n / d * 100:.1f} %)" if d else f"{n}/0 (no definido)"


def pct(values: list[float], q: float) -> float:
    if not values:
        return float("nan")
    s = sorted(values)
    k = (len(s) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def greeting_latencies(cases: list[tuple[bool, list[dict]]]) -> list[float]:
    """Latencia del PRIMER turno de los casos de saludo (expected.fast_path = True). Entrada: (es_saludo, turnos)."""
    out = []
    for is_greeting, turns in cases:
        first = next((t for t in turns if t["kind"] in ("message", "action")), None)
        if is_greeting and first:
            out.append(first["latency_ms"])
    return out


def intent_llm_share(traces: list[dict] | None) -> tuple[int, int]:
    """(turnos cuya intención la resolvió el LLM, turnos con paso de intención). Con la cascada, el resto lo resolvió el
    modelo pequeño; con palabras clave es 0."""
    steps = [t for t in traces or [] if t["node"] == "intent"]
    return sum(t["kind"] == "llm" for t in steps), len(steps)


def intent_overrides(traces: list[dict] | None) -> tuple[int, int]:
    """(turnos donde las palabras clave corrigieron la intención del LLM, turnos con paso de intención).
    La corrección (paso `intencion_corregida`) ocurre cuando el LLM lee una pregunta de proceso como vacía."""
    with_intent = {t["turn_id"] for t in traces or [] if t["node"] == "intent"}
    overridden = {t["turn_id"] for t in traces or [] if t["node"] == "intencion_corregida"}
    return len(overridden & with_intent), len(with_intent)


def summarize(scored: list[Scored]) -> dict:
    n = len(scored)
    auto = [s for s in scored if s.expected_auto]
    exp_esc = [s for s in scored if s.expected_escalated]
    act_esc = [s for s in scored if s.escalated]
    reason_ok = lambda s: not s.run.case.expected.handoff_reason or any(
        h["reason_code"] == s.run.case.expected.handoff_reason for h in s.run.artifacts.get("handoffs", []))
    successes = [s for s in scored if s.safe_auto]
    attempted = [s for s in scored if s.attempted]
    total_cost = sum(s.cost for s in scored)
    turns = [x for s in scored for x in s.turn_latencies]
    per_case = [sum(s.turn_latencies) for s in scored]
    return {
        "n_casos": n,
        "resolucion_automatica_segura": (len(successes), len(auto)),
        "automatizacion_intentada": (len(attempted), n),
        "contencion": (sum(not s.escalated for s in scored), n),
        "escalamientos_correctos": (sum(s.escalated and reason_ok(s) for s in exp_esc), len(exp_esc)),
        "escalamientos_perdidos": (sum(not s.escalated for s in exp_esc), len(exp_esc)),
        "escalamientos_innecesarios": (sum(not s.expected_escalated for s in act_esc), len(act_esc)),
        "resultados_inseguros": (sum(s.unsafe for s in scored), n),
        "casos_que_pasan_todo": (sum(s.all_pass for s in scored), n),
        "intent_resuelta_por_llm": tuple(map(sum, zip((0, 0), *(intent_llm_share(s.run.artifacts.get("traces")) for s in scored)))),
        "intent_overridden_by_keywords": tuple(map(sum, zip((0, 0), *(intent_overrides(s.run.artifacts.get("traces")) for s in scored)))),
        "latencia_saludo_ms": (lambda g: {"p50": pct(g, 0.5), "p95": pct(g, 0.95), "n": len(g)})(
            greeting_latencies([(bool(s.run.case.expected.fast_path), [vars(t) for t in s.run.turns]) for s in scored])),
        "latencia_turno_ms": {"p50": pct(turns, 0.5), "p95": pct(turns, 0.95), "n": len(turns)},
        "latencia_caso_ms": {"p50": pct(per_case, 0.5), "p95": pct(per_case, 0.95), "n": len(per_case)},
        "latencia_turno_llm_vs_resto_ms": latency_summary([x for s in scored for x in s.latency_split]),
        "costo_total_usd": round(total_cost, 4),
        "costo_por_caso_usd": round(total_cost / n, 4) if n else None,
        "costo_por_caso_intentado_usd": round(total_cost / len(attempted), 4) if attempted else None,
        "costo_por_resolucion_exitosa_usd": round(total_cost / len(successes), 4) if successes else None,
        "checkers": {c.name: (sum(s.ok(c.name) for s in scored), n) for c in scored[0].checks} if scored else {},
    }


def breakdown(scored: list[Scored], key) -> dict[str, dict]:
    groups = defaultdict(list)
    for s in scored:
        groups[key(s)].append(s)
    return {g: {"n": len(v), "pasan_todo": (sum(x.all_pass for x in v), len(v)),
                "resolucion_segura": (sum(x.safe_auto for x in v), sum(x.expected_auto for x in v)),
                "inseguros": (sum(x.unsafe for x in v), len(v))} for g, v in sorted(groups.items())}


FAILURE_CLASS = {"transaccion_correcta": "extracción", "vueltas_de_aclaracion": "aclaración", "aviso_esperado": "política",
                 "motivo_del_reclamo": "política", "respuesta_aprobada": "extracción", "saludo_sin_llm": "extracción",
                 "fuera_de_alcance_aprobado": "política", "conversacion_abierta": "política", "handoff_completo": "escalamiento", "idioma": "idioma",
                 "sin_acciones_prohibidas": "política", "estados_http": "tool"}


NO_INTENT = {"fuera_de_alcance", "sin_contenido"}


def classify_failure(check_name: str, got: str, expected: list[str], traces: list[dict]) -> str:
    """extracción incluye la comprensión del mensaje: intención mal clasificada o datos mal extraídos."""
    if any(t.get("error") and t.get("tool") for t in traces) and check_name != "idioma":
        return "tool"
    intents = {(t.get("output") or {}).get("intent") for t in traces if t["node"] == "intent"}
    if check_name == "resultado_final" and got == "abstained" and "abstained" not in expected and intents & NO_INTENT:
        return "extracción"
    if check_name == "resultado_final":
        if got == "escalated" or "escalated" in expected:
            return "escalamiento"
        if got == "clarified_then_resolved" or "clarified_then_resolved" in expected:
            return "aclaración"
        return "política"
    return FAILURE_CLASS.get(check_name, "política")


def root_cause(checks: list[dict], got: str, expected: list[str], traces: list[dict]) -> str | None:
    """Una clase por caso fallido: la del resultado final si falló, si no la de la transacción, si no la primera.
    Así los 409 que siguen a una conversación cerrada por error no cuentan como fallo de tool."""
    failed = [c["name"] for c in checks if not c["passed"]]
    if not failed:
        return None
    for name in ("resultado_final", "transaccion_correcta"):
        if name in failed:
            return classify_failure(name, got, expected, traces)
    return classify_failure(failed[0], got, expected, traces)


def failure_class(s: Scored, check: Check) -> str:
    return classify_failure(check.name, s.outcome, s.run.case.outcomes, s.run.artifacts.get("traces", []))


def top_failures(scored: list[Scored], k: int = 5) -> list[dict]:
    counter: Counter = Counter()
    examples: dict = defaultdict(list)
    for s in scored:
        for c in s.checks:
            if not c.passed:
                key = (failure_class(s, c), c.name, c.detail.split(";")[0][:90])
                counter[key] += 1
                if s.run.case.case_id not in examples[key]:
                    examples[key].append(s.run.case.case_id)
    return [{"clase": cl, "checker": ch, "detalle": d, "n": n, "casos": examples[(cl, ch, d)][:6]}
            for (cl, ch, d), n in counter.most_common(k)]


def write_report(runs_by_repeat: list[list[Scored]], variant: str, config: dict, out_dir: Path, split: str) -> tuple[Path, Path]:
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    all_scored = [s for rep in runs_by_repeat for s in rep]
    per_rep = [summarize(rep) for rep in runs_by_repeat]
    agg = summarize(all_scored)
    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw = raw_dir / f"{stamp}_{variant}_{split}.json"
    raw.write_text(json.dumps({"variant": variant, "split": split, "config": config, "summary_per_repeat": per_rep,
                               "summary_all": agg, "cases": [
                                   {"case_id": s.run.case.case_id, "repeat": s.run.repeat, "outcome": s.outcome,
                                    "resolved": s.run.resolved, "checks": [vars(c) for c in s.checks], "cost_usd": s.cost,
                                    "turns": [vars(t) for t in s.run.turns], "error": s.run.error,
                                    "traces": s.run.artifacts.get("traces")} for s in all_scored]},
                              ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    L = [f"# Evaluación {split} · variante `{variant}` · {datetime.now():%Y-%m-%d %H:%M}", "",
         f"Harness: `{config.get('command') or f'python -m eval.run --split {split} --variant {variant} --repeats {len(runs_by_repeat)}'}`. "
         f"Configuración exacta y resultado por caso en `eval/results/raw/{raw.name}` (fuera de git: contiene IDs del dataset, P-04).", "",
         "```json", json.dumps(config, ensure_ascii=False, indent=1), "```", "",
         "## Métricas (todas las repeticiones juntas)", "", "| Métrica | Valor |", "|---|---|"]
    for key in ("resolucion_automatica_segura", "automatizacion_intentada", "contencion", "escalamientos_correctos",
                "escalamientos_perdidos", "escalamientos_innecesarios", "resultados_inseguros", "casos_que_pasan_todo"):
        L.append(f"| {key.replace('_', ' ')} | {frac(*agg[key])} |")
    L.append(f"| intent_overridden_by_keywords (turnos) | {frac(*agg['intent_overridden_by_keywords'])} |")
    L.append(f"| turnos cuya intención llega al LLM | {frac(*agg['intent_resuelta_por_llm'])} |")
    lg = agg["latencia_saludo_ms"]
    if lg["n"]:
        L.append(f"| latencia del saludo (1.er turno de los casos de saludo) p50 / p95 | {lg['p50']:.0f} ms / {lg['p95']:.0f} ms (n = {lg['n']}) |")
    lt, lc = agg["latencia_turno_ms"], agg["latencia_caso_ms"]
    L += [f"| latencia por turno p50 / p95 | {lt['p50']:.0f} ms / {lt['p95']:.0f} ms (n = {lt['n']}) |",
          f"| latencia por caso p50 / p95 | {lc['p50']:.0f} ms / {lc['p95']:.0f} ms (n = {lc['n']}) |",
          f"| costo total | ${agg['costo_total_usd']:.4f} |",
          f"| costo por caso | {'$%.4f' % agg['costo_por_caso_usd'] if agg['costo_por_caso_usd'] is not None else 'no definido'} |",
          f"| costo por caso intentado | {'$%.4f' % agg['costo_por_caso_intentado_usd'] if agg['costo_por_caso_intentado_usd'] is not None else 'no definido'} |",
          f"| costo por resolución automática exitosa | {'$%.4f' % agg['costo_por_resolucion_exitosa_usd'] if agg['costo_por_resolucion_exitosa_usd'] is not None else 'no definido'} |",
          "", "## Latencia por turno: LLM vs resto (entorno de desarrollo)", "",
          "Portátil de desarrollo, `claude -p` local (arranque de proceso incluido en cada llamada). No representa producción. "
          "LLM = llamadas LLM del turno según la traza (intent y extract en paralelo cuentan una vez); resto = total − LLM.", "",
          "| | p50 | p95 |", "|---|---|---|"]
    ls = agg["latencia_turno_llm_vs_resto_ms"]
    L += [f"| {k} | {ls[k]['p50']:.0f} ms | {ls[k]['p95']:.0f} ms |" for k in ("total", "llm", "resto")]
    L += ["", f"Turnos: {ls['n']}, con al menos una llamada LLM: {ls['turnos_con_llm']}.",
          "", "## Checkers", "", "| Checker | Pasan |", "|---|---|"]
    L += [f"| {k} | {frac(*v)} |" for k, v in agg["checkers"].items()]
    if len(runs_by_repeat) > 1:
        L += ["", "## Variabilidad entre repeticiones", "", "| Métrica | " + " | ".join(f"rep {i + 1}" for i in range(len(per_rep))) + " | min–máx |",
              "|---|" + "---|" * (len(per_rep) + 1)]
        for key in ("resolucion_automatica_segura", "contencion", "resultados_inseguros", "casos_que_pasan_todo"):
            vals = [r[key][0] / r[key][1] if r[key][1] else 0 for r in per_rep]
            L.append(f"| {key.replace('_', ' ')} | " + " | ".join(frac(*r[key]) for r in per_rep) + f" | {min(vals) * 100:.1f}–{max(vals) * 100:.1f} % |")
        by_case = defaultdict(list)
        for s in all_scored:
            by_case[s.run.case.case_id].append(s.outcome)
        stable = sum(len(set(v)) == 1 for v in by_case.values())
        L += ["", f"Casos con el mismo resultado en todas las repeticiones: {frac(stable, len(by_case))}."]
        unstable = sorted(c for c, v in by_case.items() if len(set(v)) > 1)
        if unstable:
            L.append(f"Inestables: {', '.join(unstable)}.")
    for title, key in (("idioma", lambda s: s.run.case.language), ("categoría", lambda s: s.run.case.category),
                       ("segmento", lambda s: s.run.artifacts.get("segment") or "—")):
        L += ["", f"## Por {title}", "", "| Grupo | n | Pasan todo | Resolución segura | Inseguros |", "|---|---|---|---|---|"]
        for g, v in breakdown(all_scored, key).items():
            L.append(f"| {g} | {v['n']} | {frac(*v['pasan_todo'])} | {frac(*v['resolucion_segura'])} | {frac(*v['inseguros'])} |")
    L += ["", "## Fallos más frecuentes", "", "| Clase | Checker | Detalle | n | Casos |", "|---|---|---|---|---|"]
    L += [f"| {f['clase']} | {f['checker']} | {f['detalle']} | {f['n']} | {', '.join(f['casos'])} |" for f in top_failures(all_scored)]
    L += ["", "## Resultado por caso (primera repetición)", "", "| Caso | Idioma | Categoría | Esperado | Obtenido | Falla |", "|---|---|---|---|---|---|"]
    for s in runs_by_repeat[0]:
        fails = ", ".join(c.name for c in s.checks if not c.passed) or "—"
        L.append(f"| {s.run.case.case_id} | {s.run.case.language} | {s.run.case.category} | {'/'.join(s.run.case.outcomes)} | {s.outcome} | {fails} |")
    md = out_dir / f"{stamp}_{variant}_{split}.md"
    md.write_text("\n".join(L) + "\n", encoding="utf-8")
    return md, raw
