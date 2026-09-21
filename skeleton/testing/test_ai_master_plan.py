from __future__ import annotations

import json

from scripts import check_ai_master_plan as checker


def test_master_plan_machine_contract_is_complete() -> None:
    data = checker.load_plan()
    assert checker.validate(data) == []
    assert len(data["volumes"]) == 421
    assert data["volumes"][0]["key"] == "VOL-000"
    assert data["volumes"][-1]["key"] == "VOL-420"
    assert data["breadth_freeze"]["enabled"] is True


def test_master_plan_volume_ids_are_contiguous_and_titles_nonempty() -> None:
    data = json.loads(checker.MACHINE.read_text(encoding="utf-8"))
    assert [v["id"] for v in data["volumes"]] == list(range(421))
    assert all(v["title"].strip() for v in data["volumes"])


def test_volume_maturity_policy_is_machine_enforced() -> None:
    data = checker.load_plan()
    policy = data["volume_maturity_policy"]
    assert policy["specified"]["required_nonempty_fields"] == []
    assert "evidence" in policy["verified"]["required_nonempty_fields"]
    assert "implementation_paths" in policy["implemented"]["required_nonempty_fields"]


def test_promoted_volume_without_required_depth_fails_validation() -> None:
    data = checker.load_plan()
    mutated = json.loads(json.dumps(data))
    mutated["volumes"][0]["status"] = "implemented"
    mutated["volumes"][0]["requirements"] = []
    errors = checker.validate(mutated)
    assert any("status implemented requires non-empty requirements" in e for e in errors)
