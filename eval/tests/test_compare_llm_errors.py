from eval.compare import llm_calls


def test_llm_calls_counts_failures_including_intent_fallback():
    traces = [{"node": "intent", "kind": "ml", "error": "HTTP 400"}, {"node": "extract", "kind": "llm", "error": "HTTP 400"},
              {"node": "explain", "kind": "llm", "error": None}, {"node": "ranker", "kind": "ml", "error": None}]
    assert llm_calls(traces) == (3, 2)
