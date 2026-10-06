from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import shutil

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_enterprise_ai_superiority",
    ROOT / "scripts" / "check_enterprise_ai_superiority.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _fixture(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "machine").mkdir(parents=True)
    for relative in (
        "machine/enterprise_ai_superiority.json",
        "machine/ai_master_plan.json",
        "machine/competitive_ai_engineering_ladder.json",
    ):
        source = ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return root


def _load(root: Path, relative: str) -> dict:
    return json.loads((root / relative).read_text(encoding="utf-8"))


def _write(root: Path, relative: str, payload: dict) -> None:
    (root / relative).write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )


def test_current_enterprise_superiority_authority_is_valid() -> None:
    result = MODULE.validate(ROOT)

    assert result["status"] == "valid"
    assert result["master_volume_count"] == 421
    assert result["dedicated_profile_count"] == 87
    assert result["archetype_count"] >= 20
    assert result["golden_journey_count"] == 12
    assert result["enterprise_qualified_profiles"] == 0
    assert result["superior_profiles"] == 0
    assert result["all_volumes_inherit_common_contract"] is True
    assert result["competitive_engineering_family_count"] == 20
    assert result["competitive_engineering_level_count"] == 200


def test_core_and_advanced_serving_volumes_have_dedicated_profiles() -> None:
    policy = _load(ROOT, "machine/enterprise_ai_superiority.json")
    refs = set(policy["coverage"]["dedicated_profiles_required_for"])

    assert {f"VOL-{index:03d}" for index in range(4, 51)} <= refs
    assert {f"VOL-{index:03d}" for index in range(381, 421)} <= refs


def test_every_profile_declares_real_comparator_and_dominance_targets() -> None:
    policy = _load(ROOT, "machine/enterprise_ai_superiority.json")

    for profile in policy["profiles"]:
        assert profile["comparator"].strip()
        assert profile["primary_outcome"].strip()
        assert len(profile["dominance_targets"]) >= 3
        assert len(profile["hard_gates"]) >= 5
        assert len(profile["evidence_required"]) >= 7
        assert profile["qualification_state"] == "unqualified"
        for target in profile["dominance_targets"]:
            assert target["metric"].strip()
            assert target["target"].strip()
            assert target["comparison"].strip()


def test_every_masterplan_volume_has_enterprise_grade_and_target() -> None:
    policy = _load(ROOT, "machine/enterprise_ai_superiority.json")
    master = _load(ROOT, "machine/ai_master_plan.json")
    dedicated = set(policy["coverage"]["dedicated_profiles_required_for"])

    assert len(master["volumes"]) == 421
    for volume in master["volumes"]:
        assert volume["enterprise_grade_state"] == "designed"
        expected_target = (
            "superior"
            if volume["key"] in dedicated
            else "enterprise_qualified"
        )
        assert volume["enterprise_grade_target"] == expected_target


def test_masterplan_binds_each_dedicated_volume_to_superiority_profile() -> None:
    policy = _load(ROOT, "machine/enterprise_ai_superiority.json")
    master = _load(ROOT, "machine/ai_master_plan.json")
    volumes = {row["key"]: row for row in master["volumes"]}

    for profile in policy["profiles"]:
        volume = volumes[profile["volume_ref"]]
        assert volume["enterprise_superiority_profile"] == profile["id"]
        assert volume["enterprise_grade_state"] == "designed"
        assert volume["enterprise_grade_target"] == "superior"


def test_rejects_removal_of_non_compensable_security_gate(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    policy = _load(root, "machine/enterprise_ai_superiority.json")
    policy["common_contract"]["non_compensable_gates"] = [
        row
        for row in policy["common_contract"]["non_compensable_gates"]
        if "critical security regressions" not in row
    ]
    _write(root, "machine/enterprise_ai_superiority.json", policy)

    with pytest.raises(
        MODULE.EnterpriseSuperiorityError,
        match="critical security regressions",
    ):
        MODULE.validate(root)


def test_rejects_thin_superiority_profile(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    policy = _load(root, "machine/enterprise_ai_superiority.json")
    policy["profiles"][0]["dominance_targets"] = policy["profiles"][0][
        "dominance_targets"
    ][:2]
    _write(root, "machine/enterprise_ai_superiority.json", policy)

    with pytest.raises(
        MODULE.EnterpriseSuperiorityError,
        match="at least three dominance targets",
    ):
        MODULE.validate(root)


def test_rejects_duplicate_volume_profile_binding(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    policy = _load(root, "machine/enterprise_ai_superiority.json")
    duplicate = deepcopy(policy["profiles"][0])
    duplicate["id"] = "ENT-VOL-999"
    policy["profiles"].append(duplicate)
    _write(root, "machine/enterprise_ai_superiority.json", policy)

    with pytest.raises(
        MODULE.EnterpriseSuperiorityError,
        match="duplicate profile binding",
    ):
        MODULE.validate(root)


def test_rejects_enterprise_qualification_without_evidence(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    policy = _load(root, "machine/enterprise_ai_superiority.json")
    profile = policy["profiles"][0]
    profile["qualification_state"] = "enterprise_qualified"
    _write(root, "machine/enterprise_ai_superiority.json", policy)

    with pytest.raises(
        MODULE.EnterpriseSuperiorityError,
        match="qualification_evidence",
    ):
        MODULE.validate(root)


def test_rejects_master_grade_ahead_of_profile_evidence(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    policy = _load(root, "machine/enterprise_ai_superiority.json")
    master = _load(root, "machine/ai_master_plan.json")
    volume_ref = policy["profiles"][0]["volume_ref"]
    volume = next(row for row in master["volumes"] if row["key"] == volume_ref)
    volume["enterprise_grade_state"] = "enterprise_qualified"
    _write(root, "machine/ai_master_plan.json", master)

    with pytest.raises(
        MODULE.EnterpriseSuperiorityError,
        match="master grade exceeds profile evidence state",
    ):
        MODULE.validate(root)


def test_rejects_master_profile_binding_drift(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    policy = _load(root, "machine/enterprise_ai_superiority.json")
    master = _load(root, "machine/ai_master_plan.json")
    volume_ref = policy["profiles"][0]["volume_ref"]
    volume = next(row for row in master["volumes"] if row["key"] == volume_ref)
    volume["enterprise_superiority_profile"] = "ENT-WRONG"
    _write(root, "machine/ai_master_plan.json", master)

    with pytest.raises(
        MODULE.EnterpriseSuperiorityError,
        match="master binding",
    ):
        MODULE.validate(root)


def test_rejects_non_dedicated_volume_claiming_superior_target(
    tmp_path: Path,
) -> None:
    root = _fixture(tmp_path)
    policy = _load(root, "machine/enterprise_ai_superiority.json")
    master = _load(root, "machine/ai_master_plan.json")
    dedicated = set(policy["coverage"]["dedicated_profiles_required_for"])
    volume = next(
        row for row in master["volumes"]
        if row["key"] not in dedicated
    )
    volume["enterprise_grade_target"] = "superior"
    _write(root, "machine/ai_master_plan.json", master)

    with pytest.raises(
        MODULE.EnterpriseSuperiorityError,
        match="non-dedicated enterprise target",
    ):
        MODULE.validate(root)


def test_golden_journeys_cover_cross_plane_enterprise_failures() -> None:
    policy = _load(ROOT, "machine/enterprise_ai_superiority.json")
    journeys = policy["end_to_end_qualification"]["golden_journeys"]

    assert [row["id"] for row in journeys] == [
        f"ENT-E2E-{index:02d}" for index in range(1, 13)
    ]
    blob = "\n".join(
        proof
        for row in journeys
        for proof in row["must_prove"]
    ).lower()
    for concept in (
        "crash",
        "tenant",
        "rollback",
        "provider",
        "saturation",
        "injection",
        "duplicate",
        "recovery",
    ):
        assert concept in blob


def test_rejects_unknown_volume_in_golden_journey(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    policy = _load(root, "machine/enterprise_ai_superiority.json")
    policy["end_to_end_qualification"]["golden_journeys"][0][
        "volume_refs"
    ][0] = "VOL-999"
    _write(root, "machine/enterprise_ai_superiority.json", policy)

    with pytest.raises(
        MODULE.EnterpriseSuperiorityError,
        match="unknown volume VOL-999",
    ):
        MODULE.validate(root)


def test_no_profile_can_self_claim_superiority_in_design_authority() -> None:
    policy = _load(ROOT, "machine/enterprise_ai_superiority.json")

    assert all(
        profile["qualification_state"] == "unqualified"
        for profile in policy["profiles"]
    )


def test_enterprise_policy_binds_competitive_engineering_ladder() -> None:
    policy = _load(ROOT, "machine/enterprise_ai_superiority.json")
    ladder = _load(ROOT, "machine/competitive_ai_engineering_ladder.json")

    assert (
        policy["authority"]["competitive_engineering_ladder"]
        == "machine/competitive_ai_engineering_ladder.json"
    )
    assert policy["competitive_engineering_ladder"]["family_count"] == 20
    assert policy["competitive_engineering_ladder"]["total_levels"] == 200
    assert len(ladder["families"]) == 20
    assert len(ladder["levels"]) == 200
    assert ladder["levels"][0]["id"] == "ENG-001"
    assert ladder["levels"][-1]["id"] == "ENG-200"


def test_rejects_competitive_ladder_binding_drift(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    policy = _load(root, "machine/enterprise_ai_superiority.json")
    policy["competitive_engineering_ladder"]["total_levels"] = 199
    _write(root, "machine/enterprise_ai_superiority.json", policy)

    with pytest.raises(
        MODULE.EnterpriseSuperiorityError,
        match="competitive ladder topology binding drift",
    ):
        MODULE.validate(root)
