import pytest

from skeleton.domains.quad import CS_STRATUM_1, DomainReject, admit


def _card(plane: str) -> dict:
    base = {"plane": plane, "bound": 32, "evidence": "skeleton/domains/quad.py", "stored_prose": 0}
    extra = {
        "engineering": {"map": "p3-engineering-closed", "self_promoting": False},
        "computer_science": {"layers": list(CS_STRATUM_1), "boundary": "halting"},
        "reverse_engineering": {"provenance": "sha256:aa", "unsigned": False},
        "security": {"secret": "", "may_self_close": False},
    }[plane]
    return {**base, **extra}


@pytest.mark.parametrize("plane", ["engineering", "computer_science", "reverse_engineering", "security"])
def test_plane_admits_and_rejects(plane: str) -> None:
    assert admit(plane, _card(plane))["admitted"]
    bad = _card(plane)
    if plane == "engineering":
        bad["self_promoting"] = True
    elif plane == "computer_science":
        bad["layers"] = ["CS300-001"]
    elif plane == "reverse_engineering":
        bad["unsigned"] = True
    else:
        bad["secret"] = "token"
    with pytest.raises(DomainReject):
        admit(plane, bad)
