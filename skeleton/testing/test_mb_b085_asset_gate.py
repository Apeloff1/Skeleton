from skeleton.mass_build.b081_b100 import b085_asset_gate as m
R = {"license": "CC0-1.0", "author": "me"}
def test_clean_asset_passes():
    assert m.evaluate([m.Asset("a.png", b"\x89PNG", R)]).passed
def test_findings():
    v = m.evaluate([m.Asset("x.bin", b"MZ\x00", R), m.Asset("t.txt", b"token=supersecret99", {"license": "GPL"})],
                   frozenset({"slur"}))
    assert "x.bin:pe_executable" in v.findings and "t.txt:license:GPL" in v.findings
    assert "t.txt:no_author" in v.findings and any("secret" in f for f in v.findings)
def test_blocked_terms():
    assert not m.evaluate([m.Asset("d.txt", b"a SLUR here", R)], frozenset({"slur"})).passed
