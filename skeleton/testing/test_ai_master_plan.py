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


def test_foundational_depth_pass_is_nonempty() -> None:
    data = checker.load_plan()
    depth = next(x for x in data["depth_passes"] if x["id"] == "DP-000-040")
    assert depth["volume_range"] == [0, 40]
    for volume in data["volumes"][:41]:
        assert volume["depth_pass"] == "DP-000-040"
        for field in depth["required_nonempty_fields"]:
            assert volume[field], (volume["key"], field)


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
            assert volume[field], (volume["key"], field)


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
            assert volume[field], (volume["key"], field)


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
            assert volume[field], (volume["key"], field)


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
            assert volume[field], (volume["key"], field)


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
            assert volume[field], (volume["key"], field)


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
            assert volume[field], (volume["key"], field)


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
            assert volume[field], (volume["key"], field)


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
            assert volume[field], (volume["key"], field)


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
            assert volume[field], (volume["key"], field)


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
            assert volume[field], (volume["key"], field)


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
