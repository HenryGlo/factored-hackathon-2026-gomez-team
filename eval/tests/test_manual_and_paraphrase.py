"""Kit del test escrito a mano (import sin ejecutar), validación de paráfrasis y latencia LLM vs resto."""
from __future__ import annotations

import json
from collections import Counter

from eval.cases.schema import Case
from eval.generator.paraphrase import validate
from eval.harness.metrics import latency_split
from eval.import_manual import ASSIGN, build_case, read_rows, main as import_main
from eval.manual.scenarios import CATEGORIES, SCENARIOS


def test_assignments_are_balanced_and_without_dataset_ids():
    fichas = json.loads(ASSIGN.read_text(encoding="utf-8"))["fichas"]
    assert len(fichas) == 40
    assert Counter(f["language"] for f in fichas) == {"es": 20, "pt": 20}
    assert Counter(f["category"] for f in fichas) == {c: 10 for c in CATEGORIES}
    assert "CLI-" not in ASSIGN.read_text(encoding="utf-8") and "TRX" not in ASSIGN.read_text(encoding="utf-8")


def test_every_scenario_builds_a_valid_case():
    for s in SCENARIOS:
        a = {"ficha_id": "F01", "scenario": s.key, "language": "pt", "selector": s.selector, "pick": 0, "session_date": "2026-06-18"}
        raw = build_case(a, [{"momento": "inicio", "orden": 1, "mensaje": "oi {x}", "notas": "", "linea": 2}])
        case = Case.model_validate(raw)
        assert case.split == "test" and case.steps[0].message == "oi {{x}}" and case.steps[0].when is None
        assert all(st.when for st in case.steps[1:])          # todo lo que no es inicio depende del estado


def test_import_orders_by_moment_and_rejects_bad_rows(tmp_path):
    csv = tmp_path / "r.csv"
    csv.write_text("ficha_id,momento,orden,mensaje,notas\nEJEMPLO,inicio,1,x,\n"
                   "F01,si_muestra_cargo,1,sí ese,\nF01,inicio,2,son como 40 dólares,\nF01,inicio,1,hola no reconozco un cargo,\n"
                   "F02,despues,1,x,\nF03,si_pregunta,1,el martes,\n", encoding="utf-8")
    rows, errors = read_rows(csv)
    assert "EJEMPLO" not in rows and any("despues" in e for e in errors)
    fichas = {x["ficha_id"]: x for x in json.loads(ASSIGN.read_text(encoding="utf-8"))["fichas"]}
    case = build_case(fichas["F01"], rows["F01"])
    assert [s.get("message") for s in case["steps"][:2]] == ["hola no reconozco un cargo", "son como 40 dólares"]
    out = tmp_path / "manual.yaml"
    assert import_main(["--csv", str(csv), "--out", str(out)]) == 1 and not out.exists()   # errores: no escribe


def test_paraphrase_validation_keeps_placeholders_and_shape():
    orig = ["no reconozco {monto_es} en {comercio}", "sí"]
    assert validate(orig, [["che, {comercio} me cobró {monto_es}", "dale"], ["{monto_es} {comercio} ni idea", "sip"]]) == []
    errs = validate(orig, [["no reconozco {monto} en {comercio}", "sí"], ["uno solo"]])
    assert any("marcadores" in e for e in errs) and any("mensajes en vez de" in e for e in errs)
    assert validate(["hola"], [["hola {"], ["hola"]])


def test_latency_split_counts_parallel_llm_once():
    turns = [{"kind": "message", "latency_ms": 9000, "response": {"turn_id": "t1"}},
             {"kind": "action", "latency_ms": 50, "response": {"turn_id": "t2"}},
             {"kind": "relogin", "latency_ms": 0, "response": {}}]
    traces = [{"turn_id": "t1", "node": "intent", "kind": "llm", "latency_ms": 4000},
              {"turn_id": "t1", "node": "extract", "kind": "llm", "latency_ms": 5000},
              {"turn_id": "t1", "node": "confirm", "kind": "llm", "latency_ms": 3000},
              {"turn_id": "t1", "node": "clarify", "kind": "code", "latency_ms": 0},
              {"turn_id": "t2", "node": "intent", "kind": "ml", "latency_ms": 1}]
    assert latency_split(turns, traces) == [{"total": 9000, "llm": 8000, "resto": 1000, "llamadas_llm": 3},
                                            {"total": 50, "llm": 0, "resto": 50, "llamadas_llm": 0}]
