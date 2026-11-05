import pytest

from skeleton.gameforge.batch_b074 import GateResult
from skeleton.gameforge.batch_b079 import CompatMatrix, MatrixError, Platform, ScenarioOutcome


def _ok(target, digest="d1", passed=True, budget=True):
    return ScenarioOutcome(passed, GateResult(target, budget, (), {}), digest)


def _matrix():
    return CompatMatrix([Platform("win", "desktop"), Platform("android", "mobile")], ["boot", "combat"])


def _fill(m, **over):
    for p, t in (("win", "desktop"), ("android", "mobile")):
        for s in ("boot", "combat"):
            m.observe(p, s, over.get(f"{p}/{s}", _ok(t)))


def test_unknown_cells_block():
    m = _matrix()
    m.observe("win", "boot", _ok("desktop"))
    assert not m.green and "android/boot" in m.evaluate()["unknown"]


def test_full_green():
    m = _matrix()
    _fill(m)
    assert m.green and m.to_dict()["cells"]["win/boot"]["passed"]


def test_failures_budget_and_visual_drift():
    m = _matrix()
    _fill(m, **{"android/combat": _ok("mobile", digest="d2", budget=False),
                "win/boot": _ok("desktop", passed=False)})
    p = m.evaluate()
    assert p["failed"] == ["win/boot"] and p["over_budget"] == ["android/combat"]
    assert p["visual_drift"] and p["visual_drift"][0].startswith("combat")
    m.declare_visual_difference("android", "combat")
    assert m.evaluate()["visual_drift"] == []


def test_rejects_mismatched_evidence():
    m = _matrix()
    with pytest.raises(MatrixError):
        m.observe("win", "boot", _ok("mobile"))
    with pytest.raises(MatrixError):
        m.observe("ps5", "boot", _ok("desktop"))
