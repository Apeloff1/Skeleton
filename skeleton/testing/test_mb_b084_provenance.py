from skeleton.mass_build.b081_b100 import b084_provenance as m
H = "a" * 64
COMPS = [{"name": "b", "version": "1", "sha256": H}, {"name": "a", "version": "2", "sha256": H}]
def test_sbom_canonical_order():
    s = m.sbom(COMPS); assert [c["name"] for c in s["components"]] == ["a", "b"]
    assert s["digest"] == m.sbom(list(reversed(COMPS)))["digest"]
def test_attestation_roundtrip_and_tamper():
    s = m.sbom(COMPS); att = m.attest(H, "ci", s)
    assert m.verify_attestation(att, s)
    assert not m.verify_attestation({**att, "builder": "evil"}, s)
def test_evaluate():
    s = m.sbom(COMPS); att = m.attest(H, "ci", s)
    assert m.evaluate(COMPS, ["actions/checkout@" + "f" * 40], att, s).passed
    v = m.evaluate([{"name": "z", "sha256": "x"}], ["actions/checkout@v4"], att, s)
    assert "unhashed:z" in v.findings and "unpinned_action:actions/checkout@v4" in v.findings
