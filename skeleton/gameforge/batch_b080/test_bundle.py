import json

import pytest

from skeleton.gameforge.batch_b074 import GateResult
from skeleton.gameforge.batch_b079 import CompatMatrix, Platform, ScenarioOutcome
from skeleton.gameforge.batch_b080 import BundleError, ReleaseEvidenceBundle, verify_bundle


def _bundle(failed=0, perf_ok=True, critical=0):
    m = CompatMatrix([Platform("win", "desktop")], ["boot"])
    m.observe("win", "boot", ScenarioOutcome(True, GateResult("desktop", True, (), {}), "d"))
    b = ReleaseEvidenceBundle("1.2.0")
    b.add_tests(40, failed, {f"t{i}": "blob" for i in range(failed)})
    b.add_perf([GateResult("desktop", perf_ok, () if perf_ok else ("frame_ms",), {"frame_ms": 15.0})])
    b.add_compat(m)
    b.add_security("bandit", critical, 0, "sha256:abc")
    b.add_provenance("9a73a0cb", "ci", {"game.zip": "sha256:1"})
    return b


def test_green_bundle_builds_and_verifies():
    blob = _bundle().build()
    body = verify_bundle(blob)
    assert body["version"] == "1.2.0" and body["sections"]["tests"]["passed"] == 40


def test_tamper_detected():
    doc = json.loads(_bundle().build())
    doc["body"]["sections"]["tests"]["passed"] = 99
    with pytest.raises(BundleError, match="seal"):
        verify_bundle(json.dumps(doc))


def test_blockers_and_waivers():
    with pytest.raises(BundleError, match="tests"):
        _bundle(failed=1).build()
    b = _bundle(perf_ok=False, critical=1)
    with pytest.raises(BundleError, match="perf, security"):
        b.build()
    b.waive("perf", "BB", "known GPU driver issue")
    b.waive("security", "BB", "false positive")
    assert verify_bundle(b.build())["waivers"]["perf"].startswith("BB")


def test_missing_sections_and_evidence():
    with pytest.raises(BundleError, match="missing section"):
        ReleaseEvidenceBundle("1").build()
    with pytest.raises(BundleError):
        ReleaseEvidenceBundle("1").add_tests(1, 2, {"a": "x"})
