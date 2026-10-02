"""scripts/final_eval.sh y su tabla: el ensayo nunca toca el split test ni la API; la tabla marca las corridas no válidas."""
import importlib.util
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("final_eval_table", REPO / "scripts" / "final_eval_table.py")
table = importlib.util.module_from_spec(spec)
spec.loader.exec_module(table)


def raw(tmp_path, name, failed=(0, 100), provider="anthropic_api"):
    summary = {"casos_que_pasan_todo": [58, 60], "resultados_inseguros": [0, 60], "resolucion_automatica_segura": [40, 41],
               "escalamientos_correctos": [9, 9], "latencia_turno_ms": {"p50": 1500.0, "p95": 4600.0}, "costo_por_caso_usd": 0.0079,
               "llamadas_llm_fallidas": list(failed)}
    p = tmp_path / f"{name}.json"
    p.write_text(json.dumps({"variant": name, "split": "dev", "config": {"env": {"LLM_PROVIDER": provider}}, "summary_all": summary}))
    return p


def test_table_has_fractions_latency_and_cost(tmp_path, capsys):
    assert table.main([str(raw(tmp_path, "sistema_api")), "--out", str(tmp_path / "t.md")]) == 0
    text = (tmp_path / "t.md").read_text()
    assert "58/60 (96,7%)" in text and "0/60 (0,0%)" in text and "1,5 s / 4,6 s" in text and "$0.0079" in text
    assert "Sistema (API) · `anthropic_api`" in text


def test_table_flags_a_run_with_too_many_failed_llm_calls(tmp_path, capsys):
    assert table.main([str(raw(tmp_path, "sistema_api", failed=(30, 100)))]) == 3
    assert "Corrida no válida" in capsys.readouterr().out


def test_rehearsal_never_runs_the_test_split_or_the_api():
    sh = (REPO / "scripts" / "final_eval.sh").read_text()
    rehearsal = sh[sh.index('if [[ -z "$FINAL" ]]; then'):sh.index("else\n  MODE=\"CORRIDA FINAL")]
    assert "SPLITS=(dev)" in rehearsal and "PROVIDER=fake" in rehearsal and "test" not in re.sub(r"#.*", "", rehearsal)
    assert "SPLITS+=(dev_noisy)" not in rehearsal and sh.count("SPLITS+=(test)") == 1 and "--i-know-this-is-final" in sh
    assert '[[ "${DBURL##*/}" == *_test* ]]' in sh          # nunca "bank" ni la base desplegada
