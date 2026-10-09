import pytest

from skeleton.p4.production import P4Reject, TASKS, admit


def _card(task: str) -> dict:
    base = {"task": task, "bound": 64, "evidence": "skeleton/p4/production.py", "stored_prose": 0}
    extra = {
        "P4-FARM-01": {"quota": 8, "queue": "build"},
        "P4-RIGHTS-01": {"allowed": True, "license": "internal"},
        "P4-LIFECYCLE-01": {"deprecated": False, "stage": "hold"},
        "P4-SANDBOX-01": {"isolated": True, "flag": "off"},
        "P4-LOCALITY-01": {"tier": "hot", "bytes": 16},
        "P4-CACHE-01": {"bound_cache": True, "speculative": False, "verified": False},
    }[task]
    return {**base, **extra}


@pytest.mark.parametrize("task", TASKS)
def test_p4_admits_and_rejects_adversary(task: str) -> None:
    assert admit(task, _card(task))["admitted"]
    bad = _card(task)
    if task == "P4-FARM-01":
        bad["quota"] = 999
    elif task == "P4-RIGHTS-01":
        bad["allowed"] = False
    elif task == "P4-LIFECYCLE-01":
        bad["deprecated"] = True
        bad["stage"] = "serve"
    elif task == "P4-SANDBOX-01":
        bad["isolated"] = False
    elif task == "P4-LOCALITY-01":
        bad["tier"] = "tape"
    else:
        bad["speculative"] = True
        bad["verified"] = False
    with pytest.raises(P4Reject):
        admit(task, bad)
