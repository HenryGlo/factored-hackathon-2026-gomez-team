"""La puerta de calidad no aprueba con resultados de otro commit ni con corridas incompletas."""
from eval.ci_gate import freshness_problem

HEAD = "a" * 40


def raw(sha, total):
    return {"config": {"git_commit": sha}, "summary_all": {"casos_que_pasan_todo": [total, total]}}


def test_result_of_this_commit_and_complete_is_accepted():
    assert freshness_problem(raw(HEAD, 105), HEAD, 105) is None
    assert freshness_problem(raw(HEAD, 315), HEAD, 105) is None          # 3 repeticiones


def test_result_of_another_commit_is_rejected():
    assert "otro commit" in freshness_problem(raw("b" * 40, 105), HEAD, 105)
    assert "otro commit" in freshness_problem({"summary_all": {"casos_que_pasan_todo": [105, 105]}}, HEAD, 105)


def test_incomplete_run_is_rejected():
    assert "incompleta" in freshness_problem(raw(HEAD, 102), HEAD, 105)
