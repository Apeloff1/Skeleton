import pytest
from skeleton.mass_build.b081_b100 import b081_security_feed as m
OWN = {"skeleton/": "core", "skeleton/api/": "api"}
def a(i, sev, man="skeleton/api/req.txt"): return {"id": i, "package": f"p{i}", "severity": sev, "manifest": man}
def test_feed_sorted_and_owned():
    feed = m.build_feed([a(1, "low"), a(2, "critical", "skeleton/x.txt")], OWN)
    assert [n["id"] for n in feed] == ["2", "1"]
    assert feed[0]["owner"] == "core" and feed[1]["owner"] == "api"
    assert "security_review" in feed[0]["validation"]
def test_critical_blocks_and_deterministic():
    v1 = m.evaluate([a(1, "critical")], OWN); v2 = m.evaluate([a(1, "critical")], OWN)
    assert not v1.passed and v1.digest == v2.digest
def test_unknown_owner_and_dupes_fail_closed():
    assert not m.evaluate([a(1, "low", "other/x")], OWN).passed
    with pytest.raises(m.ContractError): m.build_feed([a(1, "low"), a(1, "low")], OWN)
    with pytest.raises(m.ContractError): m.normalize_alert(a(1, "bogus"), OWN)
def test_clean_passes():
    assert m.evaluate([a(1, "medium")], OWN).passed
