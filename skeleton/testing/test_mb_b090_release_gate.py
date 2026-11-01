from skeleton.mass_build.b081_b100 import b090_release_gate as m
from skeleton.mass_build.b081_b100._core import ContractError, verdict
import pytest


def ev(**over):
    e = {b: (verdict(b, []), 10) for b in m.REQUIRED}
    e.update(over)
    return e


def test_all_current_is_deterministic_but_never_provider_authorized():
    a, b = m.evaluate(ev(), 12, True), m.evaluate(ev(), 12, True)
    assert not a.passed and a.digest == b.digest
    assert m.UNVERIFIED_AUTHORITY in a.findings
    assert a.facts["release_authorized"] is False


def test_blocks():
    assert "stale:B081" in m.evaluate(ev(), 100, True).findings
    assert "failed:B084" in m.evaluate(ev(B084=(verdict("B084", ["x"]), 10)), 12, True).findings
    e = ev()
    del e["B089"]
    assert "missing:B089" in m.evaluate(e, 12, True).findings
    assert "policy" in m.evaluate(ev(), 12, False).findings
    assert "stale:B083" in m.evaluate(ev(B083=(verdict("B083", []), 50)), 12, True).findings


@pytest.mark.parametrize("bad_now,bad_policy", [(True, True), (-1, True), (12, "true")])
def test_rejects_malformed_clock_or_policy(bad_now, bad_policy):
    with pytest.raises(ContractError):
        m.evaluate(ev(), bad_now, bad_policy)


def test_forged_local_success_cannot_claim_provider_release():
    fake = ev()
    fake["B081"] = (verdict("B081", [], claimed_source="github", claimed_sha="0" * 40), 12)
    result = m.evaluate(fake, 12, True)
    assert not result.passed
    assert m.UNVERIFIED_AUTHORITY in result.findings
    assert result.facts["release_authorized"] is False


def test_canonical_evidence_rejects_nonfinite_and_oversized_facts(monkeypatch):
    from skeleton.mass_build.b081_b100 import _core

    with pytest.raises(ContractError, match="non-canonical"):
        _core.digest({"bad": float("nan")})
    with pytest.raises(ContractError, match="non-canonical"):
        _core.digest({"bad": float("inf")})
    monkeypatch.setattr(_core, "MAX_CANONICAL_BYTES", 64)
    with pytest.raises(ContractError, match="byte bound"):
        _core.digest({"large": "x" * 128})
