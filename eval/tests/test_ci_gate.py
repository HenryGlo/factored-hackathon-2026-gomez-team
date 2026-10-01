"""Puerta de calidad del harness en CI (eval/ci_gate.py)."""
from __future__ import annotations

import json

from eval import ci_gate


def write_run(root, variant: str, passed: int, total: int, unsafe: int, stamp: str = "20261001-1200") -> None:
    raw = root / "results" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / f"{stamp}_{variant}_dev.json").write_text(json.dumps({"summary_all": {
        "casos_que_pasan_todo": [passed, total], "resultados_inseguros": [unsafe, total]}}), encoding="utf-8")


def setup(tmp_path, monkeypatch, ref: dict | None):
    monkeypatch.setattr(ci_gate, "ROOT", tmp_path)
    monkeypatch.setattr(ci_gate, "REFERENCE", tmp_path / "ci_reference.json")
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    if ref:
        (tmp_path / "ci_reference.json").write_text(json.dumps({"variants": ref}), encoding="utf-8")


def test_passes_when_equal_or_better_and_safe(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch, {"baseline": {"passed": 50, "total": 54}})
    write_run(tmp_path, "baseline", 52, 54, 0)
    assert ci_gate.main(["--split", "dev", "baseline"]) == 0


def test_fails_on_regression(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch, {"baseline": {"passed": 54, "total": 54}})
    write_run(tmp_path, "baseline", 53, 54, 0)
    assert ci_gate.main(["--split", "dev", "baseline"]) == 1


def test_fails_on_any_unsafe_result_even_without_regression(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch, {"baseline": {"passed": 50, "total": 54}})
    write_run(tmp_path, "baseline", 54, 54, 1)
    assert ci_gate.main(["--split", "dev", "baseline"]) == 1


def test_uses_latest_run_and_update_rewrites_reference(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch, None)
    write_run(tmp_path, "baseline", 40, 54, 0, "20261001-1000")
    write_run(tmp_path, "baseline", 54, 54, 0, "20261001-1100")
    assert ci_gate.main(["--split", "dev", "baseline", "--update"]) == 0
    assert json.loads((tmp_path / "ci_reference.json").read_text())["variants"]["baseline"]["passed"] == 54
