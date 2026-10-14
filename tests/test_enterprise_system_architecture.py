from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts" / "check_enterprise_system_architecture.py"
VERIFIER = ROOT / "scripts" / "verify_enterprise_system_architecture.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _payloads():
    return {
        "contract": json.loads(
            (ROOT / "machine" / "enterprise_system_architecture.json").read_text(
                encoding="utf-8"
            )
        ),
        "architecture": json.loads(
            (ROOT / "machine" / "architecture.json").read_text(encoding="utf-8")
        ),
        "construction": json.loads(
            (ROOT / "machine" / "ai_app_construction.json").read_text(
                encoding="utf-8"
            )
        ),
        "interfaces": json.loads(
            (ROOT / "machine" / "capability_interfaces.json").read_text(
                encoding="utf-8"
            )
        ),
        "state_topology": json.loads(
            (ROOT / "machine" / "state_topology.json").read_text(encoding="utf-8")
        ),
        "runtime_manifest": json.loads(
            (ROOT / "skeleton" / "app" / "manifest.json").read_text(
                encoding="utf-8"
            )
        ),
    }


def _validate_payloads(checker, payloads):
    return checker.validate_payloads(
        payloads["contract"],
        payloads["architecture"],
        payloads["construction"],
        payloads["interfaces"],
        payloads["state_topology"],
        payloads["runtime_manifest"],
        repo_root=ROOT,
    )


def test_enterprise_architecture_contract_is_structurally_valid() -> None:
    checker = _load_module(CHECKER, "enterprise_checker")
    assert checker.validate() == []


def test_all_construction_planes_are_mapped_exactly_once() -> None:
    checker = _load_module(CHECKER, "enterprise_checker_planes")
    payloads = _payloads()
    contract = payloads["contract"]
    mapped = [
        plane
        for domain in contract["enterprise_domains"]
        for plane in domain["planes"]
    ]
    construction = {plane["id"] for plane in payloads["construction"]["planes"]}
    assert len(mapped) == len(set(mapped))
    assert set(mapped) == construction
    assert _validate_payloads(checker, payloads) == []


def test_duplicate_enterprise_plane_mapping_fails_closed() -> None:
    checker = _load_module(CHECKER, "enterprise_checker_duplicate_plane")
    payloads = _payloads()
    payloads["contract"] = copy.deepcopy(payloads["contract"])
    payloads["contract"]["enterprise_domains"][0]["planes"].append("foundation")
    errors = _validate_payloads(checker, payloads)
    assert "AI capability plane is mapped to multiple enterprise domains" in errors


def test_runtime_cell_dependency_drift_fails_closed() -> None:
    checker = _load_module(CHECKER, "enterprise_checker_runtime_drift")
    payloads = _payloads()
    payloads["contract"] = copy.deepcopy(payloads["contract"])
    backend = next(
        service
        for service in payloads["contract"]["runtime_cell"]["services"]
        if service["id"] == "backend"
    )
    backend["depends_on"] = ["mongo"]
    errors = _validate_payloads(checker, payloads)
    assert any(
        error.startswith("runtime cell dependency drift for backend:")
        for error in errors
    )


def test_production_serving_tier_cannot_be_single_replica() -> None:
    checker = _load_module(CHECKER, "enterprise_checker_replicas")
    payloads = _payloads()
    payloads["contract"] = copy.deepcopy(payloads["contract"])
    engine = next(
        service
        for service in payloads["contract"]["runtime_cell"]["services"]
        if service["id"] == "skeleton"
    )
    engine["minimum_production_replicas"] = 1
    errors = _validate_payloads(checker, payloads)
    assert "production serving tier skeleton must be redundant" in errors


def test_workstream_cycle_fails_closed() -> None:
    checker = _load_module(CHECKER, "enterprise_checker_cycle")
    payloads = _payloads()
    payloads["contract"] = copy.deepcopy(payloads["contract"])
    ent01 = next(
        workstream
        for workstream in payloads["contract"]["implementation_workstreams"]
        if workstream["id"] == "ENT-01"
    )
    ent01["depends_on"] = ["ENT-16"]
    errors = _validate_payloads(checker, payloads)
    assert any(
        error.startswith("enterprise implementation workstream DAG contains cycle:")
        for error in errors
    )


def test_production_claim_requires_runtime_evidence() -> None:
    checker = _load_module(CHECKER, "enterprise_checker_production_claim")
    payloads = _payloads()
    payloads["contract"] = copy.deepcopy(payloads["contract"])
    payloads["contract"]["production_claim"] = True
    errors = _validate_payloads(checker, payloads)
    assert (
        "production_claim=true requires completion.implementation_state=evidenced"
        in errors
    )
    assert "production_claim=true requires production_evidence object" in errors


def test_structural_receipt_is_independently_rehashed(tmp_path: Path) -> None:
    checker = _load_module(CHECKER, "enterprise_checker_receipt")
    verifier = _load_module(VERIFIER, "enterprise_independent_verifier")
    head = "a" * 40
    receipt = checker.evidence(head)
    receipt_path = tmp_path / "enterprise-architecture.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    result = verifier.verify(receipt_path, head)
    assert result["valid"] is True
    assert result["errors"] == []
    assert result["plan_complete"] is True
    assert result["production_claim"] is False
    assert result["structural_evidence_digest"] == (
        result["recomputed_structural_evidence_digest"]
    )
    assert len(result["contract_digest"]) == 64
    assert len(result["receipt_digest"]) == 64
    assert len(result["verifier_digest"]) == 64
    assert len(result["file_digests"]) >= 10


def test_independent_verifier_rejects_tampered_receipt(tmp_path: Path) -> None:
    checker = _load_module(CHECKER, "enterprise_checker_tamper")
    verifier = _load_module(VERIFIER, "enterprise_independent_tamper")
    head = "b" * 40
    receipt = checker.evidence(head)
    first = next(iter(receipt["file_digests"]))
    receipt["file_digests"][first] = "0" * 64
    receipt_path = tmp_path / "tampered.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    result = verifier.verify(receipt_path, head)
    assert result["valid"] is False
    assert "enterprise independent file digest map mismatch" in result["errors"]
    assert "enterprise structural evidence digest mismatch" in result["errors"]
