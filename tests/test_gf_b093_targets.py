import pytest
from skeleton.gameforge.batch_b09x import b093_targets as m


def test_matrix_complete():
    assert {t.family for t in m.MATRIX.values()} == {"desktop", "mobile", "web"}
    assert all(t.recipe and t.max_mb > 0 for t in m.MATRIX.values())


def test_budgets_and_caps():
    assert m.evaluate("linux-x64", {"keyboard"}, 100, 10.0, True).passed
    v = m.evaluate("web-wasm", {"threads"}, 80, 40.0, False)
    assert set(v.findings) == {
        "missing_capability:threads",
        "size:80>50",
        "frame:40.0>33.3",
        "smoke",
    }
    with pytest.raises(m.ContractError):
        m.evaluate("n64", set(), 1, 1, True)
