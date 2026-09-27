from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/check_p1_required_gate_authority.py"
AUTHORITY = ROOT / "machine/p1_required_gate_authority.json"
MASTER_PLAN = ROOT / "machine/ai_master_plan.json"


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "check_p1_required_gate_authority",
        SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _copy_contract(tmp_path: Path) -> Path:
    authority = json.loads(AUTHORITY.read_text(encoding="utf-8"))
    target = tmp_path / "machine/p1_required_gate_authority.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(authority, indent=2) + "\n",
        encoding="utf-8",
    )
    master_target = tmp_path / "machine/ai_master_plan.json"
    master_target.write_text(
        MASTER_PLAN.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    for gate in authority["gates"]:
        source = ROOT / gate["workflow_file"]
        dest = tmp_path / gate["workflow_file"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return target


def _mutate_authority(tmp_path: Path, mutation) -> Path:
    path = _copy_contract(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutation(payload)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def test_repository_required_gate_authority_is_valid() -> None:
    module = _module()

    errors, summary = module.validate_authority(ROOT)

    assert errors == []
    assert summary["valid"] is True
    assert summary["required_gate_count"] == 22
    assert summary["group_count"] == 10
    assert len(summary["authority_digest"]) == 64


def test_authority_rejects_missing_gate(tmp_path: Path) -> None:
    module = _module()
    path = _mutate_authority(
        tmp_path,
        lambda payload: payload["gates"].pop(),
    )

    errors, _ = module.validate_authority(
        tmp_path,
        authority_path=path.relative_to(tmp_path),
    )

    assert any("required gate count drift" in error for error in errors)
    assert any("membership drift" in error for error in errors)


def test_authority_rejects_workflow_name_drift(tmp_path: Path) -> None:
    module = _module()

    def mutate(payload: dict) -> None:
        payload["gates"][0]["workflow_name"] = "Renamed Merge Gate"

    path = _mutate_authority(tmp_path, mutate)
    errors, _ = module.validate_authority(
        tmp_path,
        authority_path=path.relative_to(tmp_path),
    )

    assert any("workflow name mismatch" in error for error in errors)


def test_authority_rejects_missing_workflow_file(tmp_path: Path) -> None:
    module = _module()
    path = _copy_contract(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    workflow = tmp_path / payload["gates"][0]["workflow_file"]
    workflow.unlink()

    errors, _ = module.validate_authority(
        tmp_path,
        authority_path=path.relative_to(tmp_path),
    )

    assert any("workflow file missing" in error for error in errors)


def test_authority_rejects_non_success_acceptance(tmp_path: Path) -> None:
    module = _module()

    def mutate(payload: dict) -> None:
        payload["gates"][0]["accepted_conclusions"] = ["success", "neutral"]

    path = _mutate_authority(tmp_path, mutate)
    errors, _ = module.validate_authority(
        tmp_path,
        authority_path=path.relative_to(tmp_path),
    )

    assert any(
        "accepted_conclusions must be success-only" in error
        for error in errors
    )


def test_authority_rejects_nonterminal_acceptance(tmp_path: Path) -> None:
    module = _module()

    def mutate(payload: dict) -> None:
        payload["gates"][0]["accepted_statuses"] = ["completed", "in_progress"]

    path = _mutate_authority(tmp_path, mutate)
    errors, _ = module.validate_authority(
        tmp_path,
        authority_path=path.relative_to(tmp_path),
    )

    assert any(
        "accepted_statuses must be completed-only" in error
        for error in errors
    )


def test_authority_rejects_group_membership_drift(tmp_path: Path) -> None:
    module = _module()

    def mutate(payload: dict) -> None:
        payload["groups"][0]["gate_ids"].append(
            payload["groups"][1]["gate_ids"][0]
        )

    path = _mutate_authority(tmp_path, mutate)
    errors, _ = module.validate_authority(
        tmp_path,
        authority_path=path.relative_to(tmp_path),
    )

    assert any("membership drift" in error for error in errors)


def test_authority_rejects_fail_closed_policy_drift(tmp_path: Path) -> None:
    module = _module()

    def mutate(payload: dict) -> None:
        payload["fail_closed_rules"]["cancelled_conclusion"] = "warn"

    path = _mutate_authority(tmp_path, mutate)
    errors, _ = module.validate_authority(
        tmp_path,
        authority_path=path.relative_to(tmp_path),
    )

    assert "authority fail_closed_rules drift" in errors


def test_authority_rejects_terminal_policy_drift(tmp_path: Path) -> None:
    module = _module()

    def mutate(payload: dict) -> None:
        payload["terminal_policy"]["all_required_gates_must_pass"] = False

    path = _mutate_authority(tmp_path, mutate)
    errors, _ = module.validate_authority(
        tmp_path,
        authority_path=path.relative_to(tmp_path),
    )

    assert any(
        "terminal_policy all_required_gates_must_pass drift" in error
        for error in errors
    )

def test_authority_rejects_masterplan_pointer_drift(tmp_path: Path) -> None:
    module = _module()
    path = _copy_contract(tmp_path)
    master = tmp_path / "machine/ai_master_plan.json"
    payload = json.loads(master.read_text(encoding="utf-8"))
    payload["authority"]["p1_required_gate_authority"] = "machine/wrong.json"
    master.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    errors, _ = module.validate_authority(
        tmp_path,
        authority_path=path.relative_to(tmp_path),
    )

    assert "master plan required-gate authority pointer drift" in errors

def _passing_rows(authority: dict, head: str = "a" * 40) -> list[dict]:
    return [
        {
            "workflow_name": gate["workflow_name"],
            "head_sha": head,
            "run_id": f"run-{index}",
            "run_attempt": 1,
            "event": "pull_request",
            "status": "completed",
            "conclusion": "success",
            "completed_at": "2026-09-27T18:00:00Z",
        }
        for index, gate in enumerate(authority["gates"], start=1)
        if gate["required_for_terminal_p1_promotion"] is True
    ]


def test_observation_evaluator_accepts_exact_complete_set(tmp_path: Path) -> None:
    module = _module()
    authority_path = _copy_contract(tmp_path)
    authority = json.loads(authority_path.read_text(encoding="utf-8"))
    observations = tmp_path / "observations.json"
    observations.write_text(
        json.dumps(_passing_rows(authority), indent=2) + "\n",
        encoding="utf-8",
    )

    payload = module.evaluate_observations(
        tmp_path,
        observations_path=observations,
        target_sha="a" * 40,
        authority_path=authority_path.relative_to(tmp_path),
    )

    decision = payload["decision"]
    assert decision["accepted"] is True
    assert decision["required_gate_count"] == 22
    assert decision["passing_gate_count"] == 22
    assert len(decision["decision_digest"]) == 64


def test_observation_evaluator_rejects_stale_required_gate(tmp_path: Path) -> None:
    module = _module()
    authority_path = _copy_contract(tmp_path)
    authority = json.loads(authority_path.read_text(encoding="utf-8"))
    rows = _passing_rows(authority)
    rows[0]["head_sha"] = "b" * 40
    observations = tmp_path / "observations.json"
    observations.write_text(
        json.dumps(rows, indent=2) + "\n",
        encoding="utf-8",
    )

    payload = module.evaluate_observations(
        tmp_path,
        observations_path=observations,
        target_sha="a" * 40,
        authority_path=authority_path.relative_to(tmp_path),
    )

    assert payload["decision"]["accepted"] is False
    assert payload["decision"]["stale"] == [authority["gates"][0]["workflow_name"]]


def test_observation_evaluator_rejects_non_array_input(tmp_path: Path) -> None:
    module = _module()
    authority_path = _copy_contract(tmp_path)
    observations = tmp_path / "observations.json"
    observations.write_text("{}", encoding="utf-8")

    try:
        module.evaluate_observations(
            tmp_path,
            observations_path=observations,
            target_sha="a" * 40,
            authority_path=authority_path.relative_to(tmp_path),
        )
    except module.GateAuthorityValidationError as exc:
        assert "JSON array" in str(exc)
    else:
        raise AssertionError("non-array observations unexpectedly accepted")


def test_observation_evaluator_rejects_unknown_fields(tmp_path: Path) -> None:
    module = _module()
    authority_path = _copy_contract(tmp_path)
    authority = json.loads(authority_path.read_text(encoding="utf-8"))
    rows = _passing_rows(authority)
    rows[0]["payload"] = "forbidden"
    observations = tmp_path / "observations.json"
    observations.write_text(
        json.dumps(rows, indent=2) + "\n",
        encoding="utf-8",
    )

    try:
        module.evaluate_observations(
            tmp_path,
            observations_path=observations,
            target_sha="a" * 40,
            authority_path=authority_path.relative_to(tmp_path),
        )
    except module.GateAuthorityValidationError as exc:
        assert "unknown fields" in str(exc)
    else:
        raise AssertionError("observation with unknown fields unexpectedly accepted")

def test_authority_rejects_policy_version_and_self_path_drift(tmp_path: Path) -> None:
    module = _module()

    def mutate(payload: dict) -> None:
        payload["policy_version"] = "2.0.0"
        payload["authority"] = "machine/other.json"

    path = _mutate_authority(tmp_path, mutate)
    errors, _ = module.validate_authority(
        tmp_path,
        authority_path=path.relative_to(tmp_path),
    )

    assert "authority policy_version drift" in errors
    assert "authority self-path drift" in errors


def test_authority_rejects_invalid_gate_id(tmp_path: Path) -> None:
    module = _module()

    def mutate(payload: dict) -> None:
        payload["gates"][0]["id"] = "gate bad"

    path = _mutate_authority(tmp_path, mutate)
    errors, _ = module.validate_authority(
        tmp_path,
        authority_path=path.relative_to(tmp_path),
    )

    assert "invalid gate id: gate bad" in errors


def test_authority_rejects_duplicate_group_name(tmp_path: Path) -> None:
    module = _module()

    def mutate(payload: dict) -> None:
        payload["groups"].append(json.loads(json.dumps(payload["groups"][0])))

    path = _mutate_authority(tmp_path, mutate)
    errors, _ = module.validate_authority(
        tmp_path,
        authority_path=path.relative_to(tmp_path),
    )

    assert any("duplicate authority group name" in error for error in errors)

