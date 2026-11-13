"""Exact-head CI evidence *shape* gate with no fabricated check results."""
from __future__ import annotations
from ..contracts import fail
from ..engine import validate

REQUIRED=(
    "Merge Readiness","Backend Quality","App Foundation E2E",
    "Workflow Input Security","Sealed Context Guard","Artifact Policy",
    "Malware Gate","Repository Hygiene","Secret Scanning","Dependency Review")

def qualify_record(*, head_sha, observed, reviewed, native_e2e,
                   rights_approved, installation_proved):
    if type(observed) is not dict or set(observed)!=set(REQUIRED):
        fail("missing or additional required check names")
    for item in observed.values():
        if item not in ("success","failure","pending","cancelled","skipped"):
            fail("ambiguous CI status")
    return validate("promotion",{
        "head_sha":head_sha,"checks":dict(observed),
        "independent_review":reviewed,"real_model_e2e":native_e2e,
        "model_rights":rights_approved,"installation":installation_proved})
