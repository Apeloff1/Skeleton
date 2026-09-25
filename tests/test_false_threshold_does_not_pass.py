"""A stored false is not a threshold of zero, and an unknown surface is not 0.7."""

import json
from pathlib import Path

import pytest

from skeleton.organism.policy_enforcement import gate_check, repair_enabled_for, threshold_for
from skeleton.organism.policy_state import load_policy


def test_a_false_threshold_is_refused(tmp_path: Path) -> None:
    assert threshold_for("forge", root=tmp_path) == 0.7
    assert repair_enabled_for("forge", root=tmp_path) is True
    with pytest.raises(ValueError):
        threshold_for("not-a-surface", root=tmp_path)
    with pytest.raises(ValueError):
        repair_enabled_for("not-a-surface", root=tmp_path)
    with pytest.raises(ValueError):
        gate_check("forge", True, root=tmp_path)
    broken = tmp_path / "policy.json"
    broken.write_text(json.dumps({"quality_thresholds": {"forge": False}}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_policy(root=tmp_path)
    broken.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError):
        load_policy(root=tmp_path)
