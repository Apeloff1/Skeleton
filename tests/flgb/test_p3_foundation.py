import pytest

from skeleton.p3.foundation import P3Reject, TASKS, admit


def _card(task: str) -> dict:
    base = {"task": task, "bound": 32, "evidence": "skeleton/p3/foundation.py", "stored_prose": 0}
    extra = {
        "P3-MODEL-FOUNDATION-01": {"provenance": "sha256:aa", "provider_regression": False},
        "P3-DOMAIN-INTELLIGENCE-01": {"specialization": 4, "custody": "jeeves"},
        "P3-TRUST-EXPERIENCE-01": {"operation_id": "op-1", "presentation_only": False},
        "P3-VERTICAL-SUITE-01": {"slices": ["VS-002", "VS-003", "VS-004", "VS-005", "VS-006", "VS-007"], "independent": True},
        "P3-ACCEPTANCE-01": {"envelopes": ["negative", "aging", "recovery", "independent"]},
        "P3-CONSTRUCTION-AUTHORITY-01": {"projection": True, "self_promoting": False},
    }[task]
    return {**base, **extra}


@pytest.mark.parametrize("task", TASKS)
def test_task_admits_and_rejects_its_adversary(task: str) -> None:
    receipt = admit(task, _card(task))
    assert receipt["admitted"] and receipt["stored_prose"] == 0
    bad = _card(task)
    if task == "P3-MODEL-FOUNDATION-01":
        bad["provider_regression"] = True
    elif task == "P3-DOMAIN-INTELLIGENCE-01":
        bad["specialization"] = 999
    elif task == "P3-TRUST-EXPERIENCE-01":
        bad["presentation_only"] = True
    elif task == "P3-VERTICAL-SUITE-01":
        bad["slices"] = ["VS-002"]
    elif task == "P3-ACCEPTANCE-01":
        bad["envelopes"] = ["negative"]
    else:
        bad["self_promoting"] = True
    with pytest.raises(P3Reject):
        admit(task, bad)


def test_unknown_task_rejected() -> None:
    with pytest.raises(P3Reject):
        admit("P3-NOPE", {"task": "P3-NOPE", "bound": 1, "evidence": "x"})
