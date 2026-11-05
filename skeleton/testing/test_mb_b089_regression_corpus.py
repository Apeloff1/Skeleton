import pytest
from skeleton.mass_build.b081_b100 import b089_regression_corpus as m
def corpus():
    c = m.Corpus(); c.add(m.Case("c1", "xss", "<script>")); c.add(m.Case("c2", "path", "../etc"))
    return c
D = {"xss": lambda p: "<script" in p, "path": lambda p: ".." in p}
def test_passes_and_regresses():
    assert m.evaluate(corpus(), D).passed
    v = m.evaluate(corpus(), {**D, "path": lambda p: False})
    assert v.findings == ("regressed:c2",)
def test_append_only():
    prev = corpus().manifest(); c = m.Corpus(); c.add(m.Case("c1", "xss", "<script>"))
    assert "removed:c2" in m.evaluate(c, D, prev).findings
def test_missing_defense_and_crash():
    assert "no_defense:path" in m.evaluate(corpus(), {"xss": D["xss"]}).findings
    with pytest.raises(m.ContractError): m.evaluate(corpus(), {**D, "xss": lambda p: 1 / 0})
    with pytest.raises(m.ContractError): corpus().add(m.Case("c1", "x", ""))
