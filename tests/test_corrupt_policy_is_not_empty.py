"""A corrupt learned policy is not an empty history, and a nameless failure is not a plan."""

import pytest

from skeleton.forge.repair import _targets
from skeleton.intelligence.learned_repair import learn_from_repair, load_learned_policy


def test_corrupt_policy_and_a_nameless_failure_are_refused(tmp_path) -> None:
    path = tmp_path / "learned_repair_policy.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError):
        load_learned_policy(tmp_path)
    path.unlink()
    with pytest.raises(ValueError):
        learn_from_repair({"ok": True}, root=tmp_path)
    assert _targets({"reason": "mystery"}) == []
    assert _targets({"reason": "low_score", "weakest_path": "a.gd"}) == [
        {"target": "a.gd", "action": "repair weakest emitted file first"}
    ]
