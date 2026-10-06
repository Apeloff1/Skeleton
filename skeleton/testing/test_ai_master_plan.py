from __future__ import annotations

import json
import pytest

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


def test_foundational_depth_pass_is_nonempty() -> None:
    data = checker.load_plan()
    depth = next(x for x in data["depth_passes"] if x["id"] == "DP-000-040")
    assert depth["volume_range"] == [0, 40]
    for volume in data["volumes"][:41]:
        assert volume["depth_pass"] == "DP-000-040"
        for field in depth["required_nonempty_fields"]:
            if checker._depth_field_requires_nonempty(volume, field):
                assert volume[field], (volume["key"], field)
            else:
                assert isinstance(volume[field], list)


def test_foundational_depth_doc_exists_and_spans_000_040() -> None:
    text = checker.DEPTH_000_040.read_text(encoding="utf-8")
    assert "VOL-000" in text
    assert "VOL-040" in text


def test_sequential_depth_pass_041_080_is_nonempty() -> None:
    data = checker.load_plan()
    depth = next(x for x in data["depth_passes"] if x["id"] == "DP-041-080")
    assert depth["volume_range"] == [41, 80]
    for volume in data["volumes"][41:81]:
        assert volume["depth_pass"] == "DP-041-080"
        for field in depth["required_nonempty_fields"]:
            if checker._depth_field_requires_nonempty(volume, field):
                assert volume[field], (volume["key"], field)
            else:
                assert isinstance(volume[field], list)


def test_sequential_depth_doc_exists_and_spans_041_080() -> None:
    text = checker.DEPTH_041_080.read_text(encoding="utf-8")
    assert "VOL-041" in text
    assert "VOL-080" in text


def test_sequential_depth_pass_081_120_is_nonempty() -> None:
    data = checker.load_plan()
    depth = next(x for x in data["depth_passes"] if x["id"] == "DP-081-120")
    assert depth["volume_range"] == [81, 120]
    for volume in data["volumes"][81:121]:
        assert volume["depth_pass"] == "DP-081-120"
        for field in depth["required_nonempty_fields"]:
            if checker._depth_field_requires_nonempty(volume, field):
                assert volume[field], (volume["key"], field)
            else:
                assert isinstance(volume[field], list)


def test_sequential_depth_doc_exists_and_spans_081_120() -> None:
    text = checker.DEPTH_081_120.read_text(encoding="utf-8")
    assert "VOL-081" in text
    assert "VOL-120" in text


def test_sequential_depth_pass_121_160_is_nonempty() -> None:
    data = checker.load_plan()
    depth = next(x for x in data["depth_passes"] if x["id"] == "DP-121-160")
    assert depth["volume_range"] == [121, 160]
    for volume in data["volumes"][121:161]:
        assert volume["depth_pass"] == "DP-121-160"
        for field in depth["required_nonempty_fields"]:
            if checker._depth_field_requires_nonempty(volume, field):
                assert volume[field], (volume["key"], field)
            else:
                assert isinstance(volume[field], list)


def test_sequential_depth_doc_exists_and_spans_121_160() -> None:
    text = checker.DEPTH_121_160.read_text(encoding="utf-8")
    assert "VOL-121" in text
    assert "VOL-160" in text


def test_sequential_depth_pass_161_200_is_nonempty() -> None:
    data = checker.load_plan()
    depth = next(x for x in data["depth_passes"] if x["id"] == "DP-161-200")
    assert depth["volume_range"] == [161, 200]
    for volume in data["volumes"][161:201]:
        assert volume["depth_pass"] == "DP-161-200"
        for field in depth["required_nonempty_fields"]:
            if checker._depth_field_requires_nonempty(volume, field):
                assert volume[field], (volume["key"], field)
            else:
                assert isinstance(volume[field], list)


def test_sequential_depth_doc_exists_and_spans_161_200() -> None:
    text = checker.DEPTH_161_200.read_text(encoding="utf-8")
    assert "VOL-161" in text
    assert "VOL-200" in text


def test_sequential_depth_pass_201_240_is_nonempty() -> None:
    data = checker.load_plan()
    depth = next(x for x in data["depth_passes"] if x["id"] == "DP-201-240")
    assert depth["volume_range"] == [201, 240]
    for volume in data["volumes"][201:241]:
        assert volume["depth_pass"] == "DP-201-240"
        for field in depth["required_nonempty_fields"]:
            if checker._depth_field_requires_nonempty(volume, field):
                assert volume[field], (volume["key"], field)
            else:
                assert isinstance(volume[field], list)


def test_sequential_depth_doc_exists_and_spans_201_240() -> None:
    text = checker.DEPTH_201_240.read_text(encoding="utf-8")
    assert "VOL-201" in text
    assert "VOL-240" in text


def test_sequential_depth_pass_241_280_is_nonempty() -> None:
    data = checker.load_plan()
    depth = next(x for x in data["depth_passes"] if x["id"] == "DP-241-280")
    assert depth["volume_range"] == [241, 280]
    for volume in data["volumes"][241:281]:
        assert volume["depth_pass"] == "DP-241-280"
        for field in depth["required_nonempty_fields"]:
            if checker._depth_field_requires_nonempty(volume, field):
                assert volume[field], (volume["key"], field)
            else:
                assert isinstance(volume[field], list)


def test_sequential_depth_doc_exists_and_spans_241_280() -> None:
    text = checker.DEPTH_241_280.read_text(encoding="utf-8")
    assert "VOL-241" in text
    assert "VOL-280" in text


def test_sequential_depth_pass_281_320_is_nonempty() -> None:
    data = checker.load_plan()
    depth = next(x for x in data["depth_passes"] if x["id"] == "DP-281-320")
    assert depth["volume_range"] == [281, 320]
    for volume in data["volumes"][281:321]:
        assert volume["depth_pass"] == "DP-281-320"
        for field in depth["required_nonempty_fields"]:
            if checker._depth_field_requires_nonempty(volume, field):
                assert volume[field], (volume["key"], field)
            else:
                assert isinstance(volume[field], list)


def test_sequential_depth_doc_exists_and_spans_281_320() -> None:
    text = checker.DEPTH_281_320.read_text(encoding="utf-8")
    assert "VOL-281" in text
    assert "VOL-320" in text


def test_sequential_depth_pass_321_360_is_nonempty() -> None:
    data = checker.load_plan()
    depth = next(x for x in data["depth_passes"] if x["id"] == "DP-321-360")
    assert depth["volume_range"] == [321, 360]
    for volume in data["volumes"][321:361]:
        assert volume["depth_pass"] == "DP-321-360"
        for field in depth["required_nonempty_fields"]:
            if checker._depth_field_requires_nonempty(volume, field):
                assert volume[field], (volume["key"], field)
            else:
                assert isinstance(volume[field], list)


def test_sequential_depth_doc_exists_and_spans_321_360() -> None:
    text = checker.DEPTH_321_360.read_text(encoding="utf-8")
    assert "VOL-321" in text
    assert "VOL-360" in text


def test_master_plan_references_engineering_pass() -> None:
    data = checker.load_plan()
    engineering = data["engineering_pass"]
    assert engineering["machine_contract"] == "machine/ai_engineering_pass.json"
    assert engineering["human_contract"] == "docs/plan/ENGINEERING_PASS.md"
    assert engineering["required_for_promotion"] == ["verified", "hardened", "production"]


def test_master_plan_binds_adversarial_closure() -> None:
    data = checker.load_plan()
    closure = data["adversarial_closure"]
    assert closure["machine_contract"] == "machine/ai_adversarial_closure.json"
    assert closure["human_contract"] == "docs/plan/ADVERSARIAL_CLOSURE_PASS.md"
    assert closure["required_for_promotion"] == ["verified", "hardened", "production"]

def test_master_plan_references_engineering_task_matrix() -> None:
    data = checker.load_plan()
    engineering = data["engineering_pass"]
    assert engineering["task_matrix"] == "machine/ai_engineering_task_matrix.json"
    assert engineering["task_matrix_human"] == "docs/plan/ENGINEERING_TASK_MATRIX.md"


def test_sequential_depth_pass_361_400_is_nonempty() -> None:
    data = checker.load_plan()
    depth = next(x for x in data["depth_passes"] if x["id"] == "DP-361-400")
    assert depth["volume_range"] == [361, 400]
    for volume in data["volumes"][361:401]:
        assert volume["depth_pass"] == "DP-361-400"
        for field in depth["required_nonempty_fields"]:
            if checker._depth_field_requires_nonempty(volume, field):
                assert volume[field], (volume["key"], field)
            else:
                assert isinstance(volume[field], list)


def test_sequential_depth_doc_exists_and_spans_361_400() -> None:
    text = checker.DEPTH_361_400.read_text(encoding="utf-8")
    assert "VOL-361" in text
    assert "VOL-400" in text


def test_final_depth_pass_401_420_is_nonempty() -> None:
    data = checker.load_plan()
    depth = next(x for x in data["depth_passes"] if x["id"] == "DP-401-420")
    assert depth["volume_range"] == [401, 420]
    for volume in data["volumes"][401:421]:
        assert volume["depth_pass"] == "DP-401-420"
        for field in depth["required_nonempty_fields"]:
            if checker._depth_field_requires_nonempty(volume, field):
                assert volume[field], (volume["key"], field)
            else:
                assert isinstance(volume[field], list)


def test_final_depth_doc_closes_at_scope_freeze() -> None:
    text = checker.DEPTH_401_420.read_text(encoding="utf-8")
    assert "VOL-401" in text
    assert "VOL-420" in text
    assert "Architecture Scope Freeze" in text


def test_depth_pass_coverage_rejects_overlap() -> None:
    data = checker.load_plan()
    mutated = json.loads(json.dumps(data))
    mutated["depth_passes"].append(
        {
            "id": "DP-OVERLAP-TEST",
            "volume_range": [0, 0],
            "required_nonempty_fields": ["requirements"],
        }
    )
    errors = checker.validate(mutated)
    assert any("depth coverage for VOL-000 must be exactly one pass" in e for e in errors)

def test_master_plan_binds_scope_freeze_adr_register() -> None:
    data = checker.load_plan()

    assert (
        data["authority"]["p1_scope_freeze_adr_register"]
        == "machine/ai_scope_freeze_adrs.json"
    )
    assert (
        data["breadth_freeze"]["exception_register"]
        == "machine/ai_scope_freeze_adrs.json"
    )
    assert data["breadth_freeze"]["p1_application_policy"] == "forbid"


def test_master_plan_rejects_scope_freeze_policy_weakening() -> None:
    data = checker.load_plan()
    mutated = json.loads(json.dumps(data))
    mutated["breadth_freeze"]["p1_application_policy"] = "allow"
    mutated["authority"]["p1_scope_freeze_adr_register"] = "machine/wrong.json"

    errors = checker.validate(mutated)

    assert "breadth_freeze.p1_application_policy must equal forbid" in errors
    assert "authority.p1_scope_freeze_adr_register path drifted" in errors



@pytest.mark.parametrize(
    "implementation_status",
    (
        "evidence_pending",
        "implemented",
        "integrated",
        "verified",
        "hardened",
        "production",
    ),
)
def test_closed_gaps_are_allowed_after_implementation_materializes(
    implementation_status: str,
) -> None:
    data = checker.load_plan()
    mutated = json.loads(json.dumps(data))
    volume = mutated["volumes"][13]
    volume["implementation_status"] = implementation_status
    volume["gaps"] = []

    errors = checker.validate(mutated)

    assert "VOL-013: depth pass requires non-empty gaps" not in errors


def test_unverified_depth_pass_still_requires_gap_inventory() -> None:
    data = checker.load_plan()
    mutated = json.loads(json.dumps(data))
    volume = mutated["volumes"][13]
    volume["implementation_status"] = "unverified"
    volume["gaps"] = []

    errors = checker.validate(mutated)

    assert "VOL-013: depth pass requires non-empty gaps" in errors


def test_master_plan_rejects_stale_execution_frontier_snapshot() -> None:
    data = checker.load_plan()
    mutated = json.loads(json.dumps(data))
    mutated["execution_frontier"]["queue_snapshot"]["done"] = 41
    mutated["execution_frontier"]["queue_snapshot"]["pending"] = 1

    errors = checker.validate(mutated)

    assert (
        "execution_frontier queue_snapshot disagrees with canonical frontier"
        in errors
    )



def test_lifecycle_volumes_bind_landed_shared_contracts() -> None:
    data = checker.load_plan()
    ids = {407, 408, 410, 411, 412, 413, 416, 417, 418}
    for volume in data["volumes"]:
        if volume["id"] not in ids:
            continue
        assert "skeleton/ai/runtime/deferred/lifecycle_governance.py" in volume["implementation_paths"]
        assert volume["tests"] == ["skeleton/testing/test_lifecycle_governance.py"]
        assert not any(path.startswith("planned:") for path in volume["implementation_paths"] + volume["tests"])
        assert volume["implementation_status"] == "unverified"
        assert volume["completion_checkbox"] is False


def test_master_plan_binds_200_level_competitive_engineering_overlay() -> None:
    data = checker.load_plan()
    overlay = data["competitive_engineering_ladder"]
    ladder = json.loads(checker.COMPETITIVE_LADDER.read_text(encoding="utf-8"))

    assert overlay["authority"] == "machine/competitive_ai_engineering_ladder.json"
    assert overlay["human_spec"] == "docs/architecture/COMPETITIVE_AI_ENGINEERING_LADDER.md"
    assert overlay["family_count"] == 20
    assert overlay["levels_per_family"] == 10
    assert overlay["total_levels"] == 200
    assert len(ladder["families"]) == 20
    assert len(ladder["levels"]) == 200
    assert ladder["levels"][0]["id"] == "ENG-001"
    assert ladder["levels"][-1]["id"] == "ENG-200"


def test_master_plan_rejects_competitive_engineering_topology_drift() -> None:
    data = checker.load_plan()
    mutated = json.loads(json.dumps(data))
    mutated["competitive_engineering_ladder"]["total_levels"] = 199

    errors = checker.validate(mutated)

    assert "competitive engineering total_levels must equal 200" in errors


def test_master_plan_binds_500_level_ai_game_builder_overlay() -> None:
    data = checker.load_plan()
    overlay = data["ai_game_builder_500_levels"]
    authority = json.loads(checker.GAME_BUILDER.read_text(encoding="utf-8"))
    duel = json.loads(checker.GAME_BUILDER_DUEL.read_text(encoding="utf-8"))
    over = json.loads(checker.GAME_BUILDER_OVERENGINEERING.read_text(encoding="utf-8"))

    assert overlay["authority"] == "machine/ai_game_builder_500_levels.json"
    assert overlay["dual_rival_authority"] == "machine/ai_game_builder_dual_rival_forge.json"
    assert overlay["human_spec"] == "docs/architecture/AI_GAME_BUILDER_500_LEVELS.md"
    assert overlay["overengineering_authority"] == "machine/ai_game_builder_overengineering.json"
    assert overlay["overengineering_human_spec"] == "docs/architecture/AI_GAME_BUILDER_OVERENGINEERING.md"
    assert overlay["overengineering_planes"] == 48
    assert overlay["runtime_contracts"]["contracts"] == "skeleton/ai/game_builder/contracts.py"
    assert overlay["runtime_contracts"]["dual_rival_state_machine"] == "skeleton/ai/game_builder/dual_rival_forge.py"
    assert overlay["runtime_contracts"]["evaluation_panel"] == "skeleton/ai/game_builder/evaluation.py"
    assert overlay["runtime_contracts"]["resource_governor"] == "skeleton/ai/game_builder/resource_governor.py"
    assert overlay["runtime_contracts"]["quality_debt"] == "skeleton/ai/game_builder/quality_debt.py"
    assert overlay["runtime_contracts"]["integrated_control_plane"] == "skeleton/ai/game_builder/control_plane.py"
    assert overlay["runtime_contracts"]["resilience"] == "skeleton/ai/game_builder/resilience.py"
    assert overlay["runtime_contracts"]["gold_master"] == "skeleton/ai/game_builder/release.py"
    assert overlay["runtime_contracts"]["tests"] == [
        "tests/test_ai_game_builder_runtime.py",
        "tests/test_ai_game_builder_overengineering_runtime.py",
    ]
    assert overlay["governance_runtime"] == {
        "canon": "skeleton/ai/game_builder/canon.py",
        "rights": "skeleton/ai/game_builder/rights.py",
        "atom_lineage": "skeleton/ai/game_builder/atomizer.py",
        "tests": "tests/test_ai_game_builder_governance.py",
    }
    assert overlay["family_count"] == 50
    assert overlay["levels_per_family"] == 10
    assert overlay["total_levels"] == 500
    assert overlay["effort_modes"] == {
        "forge_100": 100,
        "forge_1000": 1000,
        "forge_10000": 10000,
    }
    assert overlay["stages_per_round"] == 3
    assert overlay["wall_clock_deadline"] is None
    assert len(authority["families"]) == 50
    assert authority["topology"]["total_levels"] == 500
    assert duel["effort_modes"]["forge_100"]["rounds"] == 100
    assert duel["effort_modes"]["forge_1000"]["rounds"] == 1000
    assert duel["effort_modes"]["forge_10000"]["rounds"] == 10000
    assert duel["overengineering_authority"] == "machine/ai_game_builder_overengineering.json"
    assert len(over["planes"]) == 48
    assert len(over["family_bindings"]) == 50


def test_master_plan_rejects_ai_game_builder_topology_drift() -> None:
    data = checker.load_plan()
    mutated = json.loads(json.dumps(data))
    mutated["ai_game_builder_500_levels"]["total_levels"] = 499
    mutated["ai_game_builder_500_levels"]["effort_modes"]["forge_10000"] = 9999
    mutated["ai_game_builder_500_levels"]["overengineering_planes"] = 47
    mutated["ai_game_builder_500_levels"]["runtime_contracts"]["contracts"] = "wrong.py"
    mutated["ai_game_builder_500_levels"]["governance_runtime"]["rights"] = "wrong.py"

    errors = checker.validate(mutated)

    assert "AI game builder total_levels must equal 500" in errors
    assert "AI game builder effort modes must equal 100/1000/10000" in errors
    assert "AI game builder overengineering_planes must equal 48" in errors
    assert "AI game builder runtime contract binding drifted" in errors
    assert "AI game builder governance runtime binding drifted" in errors
