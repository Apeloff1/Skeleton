from skeleton.mass_build.b081_b100 import b090_release_gate as m
from skeleton.mass_build.b081_b100._core import verdict
def ev(**over):
    e = {b: (verdict(b, []), 10) for b in m.REQUIRED}; e.update(over); return e
def test_all_current_passes_deterministically():
    a, b = m.evaluate(ev(), 12, True), m.evaluate(ev(), 12, True)
    assert a.passed and a.digest == b.digest
def test_blocks():
    assert "stale:B081" in m.evaluate(ev(), 100, True).findings
    assert "failed:B084" in m.evaluate(ev(B084=(verdict("B084", ["x"]), 10)), 12, True).findings
    e = ev(); del e["B089"]
    assert "missing:B089" in m.evaluate(e, 12, True).findings
    assert "policy" in m.evaluate(ev(), 12, False).findings
    assert "stale:B083" in m.evaluate(ev(B083=(verdict("B083", []), 50)), 12, True).findings
