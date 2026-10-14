from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts" / "check_advanced_ai_structure.py"
VERIFIER = ROOT / "scripts" / "verify_advanced_ai_structure.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _payloads():
    return {
        "contract": json.loads(
            (ROOT / "machine" / "advanced_ai_structure_100.json").read_text(
                encoding="utf-8"
            )
        ),
        "construction": json.loads(
            (ROOT / "machine" / "ai_app_construction.json").read_text(
                encoding="utf-8"
            )
        ),
        "enterprise": json.loads(
            (ROOT / "machine" / "enterprise_system_architecture.json").read_text(
                encoding="utf-8"
            )
        ),
    }


def _validate(checker, payloads):
    return checker.validate_payloads(
        payloads["contract"],
        payloads["construction"],
        payloads["enterprise"],
        repo_root=ROOT,
    )


def test_advanced_ai_structure_is_valid() -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker")
    assert checker.validate() == []


def test_exactly_100_contiguous_levels_and_ten_strata() -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker_counts")
    payloads = _payloads()
    contract = payloads["contract"]
    assert [level["ordinal"] for level in contract["levels"]] == list(
        range(1, 101)
    )
    assert [level["id"] for level in contract["levels"]] == [
        f"L{i:03d}" for i in range(1, 101)
    ]
    assert len(contract["strata"]) == 10
    assert _validate(checker, payloads) == []


def test_missing_level_fails_closed() -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker_missing")
    payloads = _payloads()
    payloads["contract"] = copy.deepcopy(payloads["contract"])
    payloads["contract"]["levels"].pop(44)
    errors = _validate(checker, payloads)
    assert "advanced AI structure must contain exactly 100 levels" in errors
    assert "advanced level IDs must be exactly L001 through L100" in errors


def test_forward_promotion_dependency_fails_closed() -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker_forward")
    payloads = _payloads()
    payloads["contract"] = copy.deepcopy(payloads["contract"])
    payloads["contract"]["levels"][49]["promotion_prerequisites"] = ["L051"]
    errors = _validate(checker, payloads)
    assert "L050 must promote from exactly L049" in errors
    assert "L050 prerequisite must point backward: L051" in errors


def test_unknown_plane_fails_closed() -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker_plane")
    payloads = _payloads()
    payloads["contract"] = copy.deepcopy(payloads["contract"])
    payloads["contract"]["strata"][0]["planes"].append("shadow-cognition")
    payloads["contract"]["levels"][0]["required_planes"].append(
        "shadow-cognition"
    )
    errors = _validate(checker, payloads)
    assert any("references unknown planes" in error for error in errors)


def test_every_tenth_level_is_gate_and_only_every_tenth() -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker_gate")
    payloads = _payloads()
    for level in payloads["contract"]["levels"]:
        assert level["gate"] is (level["ordinal"] % 10 == 0)
    assert _validate(checker, payloads) == []


def test_planning_change_cannot_pre_promote_or_sign_levels() -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker_promotion")
    payloads = _payloads()
    payloads["contract"] = copy.deepcopy(payloads["contract"])
    payloads["contract"]["completion"]["promoted_levels"] = ["L001"]
    payloads["contract"]["completion"]["signed_levels"] = ["L001"]
    errors = _validate(checker, payloads)
    assert "planning change must not pre-promote levels" in errors
    assert "planning change must not pre-sign levels" in errors


def test_level_99_and_100_guardrails_are_fixed() -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker_frontier")
    payloads = _payloads()
    payloads["contract"] = copy.deepcopy(payloads["contract"])
    payloads["contract"]["levels"][98]["title"] = "Unbounded Self Evolution"
    payloads["contract"]["levels"][99]["title"] = "Automatic Self Approval"
    errors = _validate(checker, payloads)
    assert "L099 must preserve bounded self-evolution governance" in errors
    assert "L100 must remain Frontier System Acceptance" in errors


def test_structural_receipt_independently_rehashes(tmp_path: Path) -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker_receipt")
    verifier = _load_module(VERIFIER, "advanced_ai_verifier")
    head = "a" * 40
    receipt = checker.evidence(head)
    path = tmp_path / "receipt.json"
    path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    result = verifier.verify(path, head)
    assert result["valid"] is True
    assert result["errors"] == []
    assert result["level_count"] == 100
    assert result["stratum_count"] == 10
    assert result["implementation_claim"] is False
    assert result["structural_evidence_digest"] == (
        result["recomputed_structural_evidence_digest"]
    )


def test_independent_verifier_rejects_tampered_receipt(tmp_path: Path) -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker_tamper")
    verifier = _load_module(VERIFIER, "advanced_ai_verifier_tamper")
    head = "b" * 40
    receipt = checker.evidence(head)
    first = next(iter(receipt["file_digests"]))
    receipt["file_digests"][first] = "0" * 64
    path = tmp_path / "tampered.json"
    path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    result = verifier.verify(path, head)
    assert result["valid"] is False
    assert "advanced AI independent file digest map mismatch" in result["errors"]
    assert "advanced AI evidence digest mismatch" in result["errors"]



def test_promotion_state_machine_is_fail_closed() -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker_state_machine")
    payloads = _payloads()
    payloads["contract"] = copy.deepcopy(payloads["contract"])
    payloads["contract"]["promotion_state_machine"]["initial"] = "PROMOTED"
    errors = _validate(checker, payloads)
    assert "advanced AI promotion initial state must be PLANNED" in errors


def test_cross_stratum_bridge_cannot_skip_forward() -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker_bridge")
    payloads = _payloads()
    payloads["contract"] = copy.deepcopy(payloads["contract"])
    payloads["contract"]["cross_stratum_bridges"][3]["to"] = "S09"
    errors = _validate(checker, payloads)
    assert "B04.to must be S05" in errors


def test_frontier_activation_profile_cannot_lower_acceptance_ceiling() -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker_profile")
    payloads = _payloads()
    payloads["contract"] = copy.deepcopy(payloads["contract"])
    profile = next(
        item
        for item in payloads["contract"]["activation_profiles"]
        if item["id"] == "frontier-governed-system"
    )
    profile["target_ceiling"] = "L099"
    errors = _validate(checker, payloads)
    assert (
        "activation profile frontier-governed-system target ceiling must be L100"
        in errors
    )



def test_maturity_dimension_set_cannot_hide_security() -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker_dimensions")
    payloads = _payloads()
    payloads["contract"] = copy.deepcopy(payloads["contract"])
    payloads["contract"]["maturity_dimensions"] = [
        item
        for item in payloads["contract"]["maturity_dimensions"]
        if item["id"] != "security"
    ]
    errors = _validate(checker, payloads)
    assert "advanced AI maturity dimension set drifted" in errors


def test_stratum_gate_cannot_average_away_authority_integrity() -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker_maturity_gate")
    payloads = _payloads()
    payloads["contract"] = copy.deepcopy(payloads["contract"])
    req = payloads["contract"]["stratum_maturity_requirements"][4]
    req["required_dimensions"].remove("authority_integrity")
    errors = _validate(checker, payloads)
    assert "S05 missing mandatory maturity dimension authority_integrity" in errors


def test_capability_ceiling_enforcement_points_are_mandatory() -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker_ceiling")
    payloads = _payloads()
    payloads["contract"] = copy.deepcopy(payloads["contract"])
    payloads["contract"]["capability_ceiling_control"]["enforcement_points"] = [
        "request admission"
    ]
    errors = _validate(checker, payloads)
    assert any(
        error.startswith(
            "capability_ceiling_control.enforcement_points must contain at least"
        )
        for error in errors
    )


def test_frontier_experiment_cannot_self_deploy() -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker_frontier_boundary")
    payloads = _payloads()
    payloads["contract"] = copy.deepcopy(payloads["contract"])
    payloads["contract"]["frontier_experiment_boundary"]["promotion_chain"] = [
        "experiment receipt",
        "independent evaluation",
        "security/governance review",
        "canary or shadow evidence",
        "release-authority decision",
        "production deployment",
    ]
    errors = _validate(checker, payloads)
    assert (
        "frontier experiment promotion chain must end in rollback-ready deployment"
        in errors
    )


def test_kill_controls_include_global_frontier_stop() -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker_kill")
    payloads = _payloads()
    payloads["contract"] = copy.deepcopy(payloads["contract"])
    payloads["contract"]["kill_and_suspend_controls"]["levels"] = [
        item
        for item in payloads["contract"]["kill_and_suspend_controls"]["levels"]
        if item["scope"] != "global-frontier"
    ]
    errors = _validate(checker, payloads)
    assert "kill/suspend scope set drifted" in errors



def test_risk_class_freshness_cannot_be_relaxed_silently() -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker_risk")
    payloads = _payloads()
    payloads["contract"] = copy.deepcopy(payloads["contract"])
    critical = next(
        item
        for item in payloads["contract"]["risk_and_freshness_policy"]["classes"]
        if item["id"] == "critical"
    )
    critical["maximum_evidence_age_days"] = 90
    errors = _validate(checker, payloads)
    assert "critical maximum_evidence_age_days must be 7" in errors


def test_level_risk_must_match_stratum_default() -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker_level_risk")
    payloads = _payloads()
    payloads["contract"] = copy.deepcopy(payloads["contract"])
    payloads["contract"]["levels"][40]["risk_class"] = "standard"
    payloads["contract"]["levels"][40]["maximum_evidence_age_days"] = 30
    errors = _validate(checker, payloads)
    assert "L041.risk_class must equal stratum default critical" in errors


def test_evidence_status_model_cannot_drop_invalidated_state() -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker_evidence_status")
    payloads = _payloads()
    payloads["contract"] = copy.deepcopy(payloads["contract"])
    payloads["contract"]["evidence_status_model"]["statuses"] = [
        "CURRENT",
        "STALE",
        "MISSING",
        "SUPERSEDED",
    ]
    errors = _validate(checker, payloads)
    assert "evidence status model drifted" in errors



def test_level_cannot_drop_operational_readiness_requirement() -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker_operability")
    payloads = _payloads()
    payloads["contract"] = copy.deepcopy(payloads["contract"])
    payloads["contract"]["levels"][70]["operational_readiness_required"] = False
    errors = _validate(checker, payloads)
    assert "L071 must require operational readiness" in errors


def test_control_profile_must_match_stratum() -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker_control_profile")
    payloads = _payloads()
    payloads["contract"] = copy.deepcopy(payloads["contract"])
    payloads["contract"]["levels"][40]["control_profile"] = copy.deepcopy(
        payloads["contract"]["level_control_profiles"]["S02"]
    )
    errors = _validate(checker, payloads)
    assert "L041.control_profile must match S05" in errors


def test_deprecation_state_model_cannot_be_bypassed() -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker_deprecation")
    payloads = _payloads()
    payloads["contract"] = copy.deepcopy(payloads["contract"])
    payloads["contract"]["deprecation_and_migration"]["states"] = [
        "ACTIVE",
        "RETIRED",
    ]
    errors = _validate(checker, payloads)
    assert "deprecation/migration state model drifted" in errors


def test_shadow_authority_detector_is_mandatory() -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker_shadow_authority")
    payloads = _payloads()
    payloads["contract"] = copy.deepcopy(payloads["contract"])
    payloads["contract"]["dependency_integrity"]["shadow_authority_detector"] = ""
    errors = _validate(checker, payloads)
    assert "dependency_integrity.shadow_authority_detector must be non-empty" in errors



def test_every_level_has_exactly_one_executable_blueprint() -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker_blueprints")
    payloads = _payloads()
    contract = payloads["contract"]
    assert len(contract["level_blueprints"]) == 100
    assert {item["id"] for item in contract["level_blueprints"]} == {
        f"ADV-L{i:03d}" for i in range(1, 101)
    }
    assert _validate(checker, payloads) == []


def test_blueprint_owner_must_be_canonical_for_level() -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker_blueprint_owner")
    payloads = _payloads()
    payloads["contract"] = copy.deepcopy(payloads["contract"])
    payloads["contract"]["level_blueprints"][40][
        "primary_owner_plane"
    ] = "memory"
    errors = _validate(checker, payloads)
    assert (
        "ADV-L041.primary_owner_plane must be in level required planes"
        in errors
    )


def test_blueprint_cannot_drop_rollback_mode() -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker_blueprint_rollback")
    payloads = _payloads()
    payloads["contract"] = copy.deepcopy(payloads["contract"])
    payloads["contract"]["level_blueprints"][79]["rollback_mode"] = ""
    errors = _validate(checker, payloads)
    assert "ADV-L080.rollback_mode must be non-empty" in errors


def test_blueprint_cannot_drop_adversarial_focus() -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker_blueprint_adversarial")
    payloads = _payloads()
    payloads["contract"] = copy.deepcopy(payloads["contract"])
    payloads["contract"]["level_blueprints"][98]["adversarial_focus"] = []
    errors = _validate(checker, payloads)
    assert any(
        error.startswith(
            "ADV-L099.adversarial_focus must contain at least"
        )
        for error in errors
    )


def test_blueprint_owner_and_collaborators_cover_level_planes() -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker_blueprint_coverage")
    payloads = _payloads()
    payloads["contract"] = copy.deepcopy(payloads["contract"])
    payloads["contract"]["level_blueprints"][20][
        "collaborating_planes"
    ] = []
    errors = _validate(checker, payloads)
    assert (
        "ADV-L021 owner/collaborator planes must cover the level plane set"
        in errors
    )



def test_model_runtime_identity_cannot_drop_policy_binding() -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker_model_identity")
    payloads = _payloads()
    payloads["contract"] = copy.deepcopy(payloads["contract"])
    payloads["contract"]["model_and_runtime_lifecycle"]["identity_fields"] = [
        item
        for item in payloads["contract"]["model_and_runtime_lifecycle"][
            "identity_fields"
        ]
        if item != "policy_bundle_version"
    ]
    errors = _validate(checker, payloads)
    assert any(
        error.startswith(
            "model_and_runtime_lifecycle.identity_fields must contain at least"
        )
        for error in errors
    )


def test_evaluation_partition_rules_cannot_be_removed() -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker_eval_partition")
    payloads = _payloads()
    payloads["contract"] = copy.deepcopy(payloads["contract"])
    payloads["contract"]["data_and_evaluation_lifecycle"][
        "partition_rules"
    ] = []
    errors = _validate(checker, payloads)
    assert any(
        error.startswith(
            "data_and_evaluation_lifecycle.partition_rules must contain at least"
        )
        for error in errors
    )


def test_portability_default_must_fail_closed_unknown() -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker_portability")
    payloads = _payloads()
    payloads["contract"] = copy.deepcopy(payloads["contract"])
    payloads["contract"]["compatibility_and_portability"]["default"] = "PORTABLE"
    errors = _validate(checker, payloads)
    assert "compatibility portability default must be UNKNOWN" in errors


def test_prompt_supply_chain_requires_versioned_artifacts() -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker_prompt_supply")
    payloads = _payloads()
    payloads["contract"] = copy.deepcopy(payloads["contract"])
    payloads["contract"]["policy_and_prompt_supply_chain"][
        "requirements"
    ] = ["looks good"]
    errors = _validate(checker, payloads)
    assert any(
        error.startswith(
            "policy_and_prompt_supply_chain.requirements must contain at least"
        )
        for error in errors
    )


def test_hardware_scheduler_inputs_cannot_collapse_to_device_only() -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker_hardware")
    payloads = _payloads()
    payloads["contract"] = copy.deepcopy(payloads["contract"])
    payloads["contract"]["hardware_aware_execution"]["scheduler_inputs"] = [
        "hardware"
    ]
    errors = _validate(checker, payloads)
    assert any(
        error.startswith(
            "hardware_aware_execution.scheduler_inputs must contain at least"
        )
        for error in errors
    )


def test_evaluator_independence_requires_all_four_tiers() -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker_evaluator")
    payloads = _payloads()
    payloads["contract"] = copy.deepcopy(payloads["contract"])
    payloads["contract"]["evaluator_independence"]["tiers"] = (
        payloads["contract"]["evaluator_independence"]["tiers"][:2]
    )
    errors = _validate(checker, payloads)
    assert "evaluator independence tier set drifted" in errors



def test_maturity_ledger_starts_with_100_planned_levels() -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker_ledger")
    payloads = _payloads()
    ledger = json.loads(
        (ROOT / "machine" / "advanced_ai_maturity_ledger.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(ledger["levels"]) == 100
    assert all(item["state"] == "PLANNED" for item in ledger["levels"])
    assert all(
        item["evidence_state"] == "MISSING"
        for item in ledger["levels"]
    )
    assert ledger["production_maturity_level"] == 0
    assert _validate(checker, payloads) == []


def test_maturity_ledger_cannot_fabricate_promoted_level(
    monkeypatch,
    tmp_path: Path,
) -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker_ledger_fake")
    payloads = _payloads()
    ledger = json.loads(
        (ROOT / "machine" / "advanced_ai_maturity_ledger.json").read_text(
            encoding="utf-8"
        )
    )
    ledger["levels"][0]["state"] = "PROMOTED"
    ledger["levels"][0]["evidence_state"] = "CURRENT"
    ledger["levels"][0]["current_evidence_receipts"] = ["fake"]
    ledger_path = tmp_path / "advanced_ai_maturity_ledger.json"
    ledger_path.write_text(
        json.dumps(ledger, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    original_load = checker._load

    def fake_load(path: Path):
        if path.name == "advanced_ai_maturity_ledger.json":
            return json.loads(ledger_path.read_text(encoding="utf-8"))
        return original_load(path)

    monkeypatch.setattr(checker, "_load", fake_load)
    errors = checker.validate_payloads(
        payloads["contract"],
        payloads["construction"],
        payloads["enterprise"],
        repo_root=ROOT,
    )
    assert "planning maturity ledger L001 must be PLANNED" in errors
    assert "planning maturity ledger L001 evidence must be MISSING" in errors
    assert (
        "planning maturity ledger L001 cannot have evidence receipts"
        in errors
    )


def test_maturity_ledger_owner_drift_fails_closed(
    monkeypatch,
    tmp_path: Path,
) -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker_ledger_owner")
    payloads = _payloads()
    ledger = json.loads(
        (ROOT / "machine" / "advanced_ai_maturity_ledger.json").read_text(
            encoding="utf-8"
        )
    )
    ledger["levels"][40]["primary_owner_plane"] = "memory"
    ledger_path = tmp_path / "advanced_ai_maturity_ledger.json"
    ledger_path.write_text(
        json.dumps(ledger, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    original_load = checker._load

    def fake_load(path: Path):
        if path.name == "advanced_ai_maturity_ledger.json":
            return json.loads(ledger_path.read_text(encoding="utf-8"))
        return original_load(path)

    monkeypatch.setattr(checker, "_load", fake_load)
    errors = checker.validate_payloads(
        payloads["contract"],
        payloads["construction"],
        payloads["enterprise"],
        repo_root=ROOT,
    )
    assert "maturity ledger L041 owner drifted" in errors


def test_maturity_ledger_summary_cannot_claim_progress(
    monkeypatch,
    tmp_path: Path,
) -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker_ledger_summary")
    payloads = _payloads()
    ledger = json.loads(
        (ROOT / "machine" / "advanced_ai_maturity_ledger.json").read_text(
            encoding="utf-8"
        )
    )
    ledger["summary"]["promoted"] = 100
    ledger["summary"]["planned"] = 0
    ledger_path = tmp_path / "advanced_ai_maturity_ledger.json"
    ledger_path.write_text(
        json.dumps(ledger, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    original_load = checker._load

    def fake_load(path: Path):
        if path.name == "advanced_ai_maturity_ledger.json":
            return json.loads(ledger_path.read_text(encoding="utf-8"))
        return original_load(path)

    monkeypatch.setattr(checker, "_load", fake_load)
    errors = checker.validate_payloads(
        payloads["contract"],
        payloads["construction"],
        payloads["enterprise"],
        repo_root=ROOT,
    )
    assert "planning maturity ledger summary drifted" in errors
