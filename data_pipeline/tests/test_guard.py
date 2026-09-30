"""El guardia de aislamiento rechaza cualquier base que no sea *_test."""
import pytest

from data_pipeline.tests.conftest import require_test_url


@pytest.mark.parametrize("url", [
    "postgresql+psycopg://bank:x@127.0.0.1:5433/bank",
    "postgresql+psycopg://bank:x@127.0.0.1:5433/bank_test_copy",
    "postgresql+psycopg://bank:x@127.0.0.1:5433/test",
])
def test_guard_rejects_non_test_databases(url):
    with pytest.raises(pytest.fail.Exception):
        require_test_url(url)


def test_guard_accepts_test_databases():
    assert require_test_url("postgresql+psycopg://u:p@h:1/bank_perf_test").endswith("bank_perf_test")
