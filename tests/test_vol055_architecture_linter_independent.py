from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from scripts import verify_vol055_architecture_linter as verifier


ROOT = Path(__file__).resolve().parents[1]


def _fixture() -> Path:
    temp = Path(tempfile.mkdtemp(prefix="vol055-independent-"))
    for relative in (
        verifier.MASTER,
        verifier.ACCOUNTABILITY,
        verifier.REGISTRY,
        verifier.ARCHITECTURE,
        verifier.VALIDATOR,
        verifier.TESTS,
    ):
        source = ROOT / relative
        target = temp / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    registry = json.loads((ROOT / verifier.REGISTRY).read_text(encoding="utf-8"))
    for rule in registry["rules"]:
        relative = Path(rule["validator_path"])
        source = ROOT / relative
        target = temp / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return temp


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_current_repository_passes_independent_vol055_verification() -> None:
    receipt = verifier.verify_repository(ROOT)
    assert receipt["valid"] is True, receipt["errors"]
    assert receipt["volume"] == "VOL-055"
    binding = receipt["registry_binding"]
    assert binding["rule_count"] >= 10
    assert binding["registered_validator_count"] == binding["discovered_validator_count"]
    assert binding["allowed_waiver_rule_count"] > 0
    assert binding["nonwaivable_rule_count"] > 0
    assert len(receipt["receipt_digest"]) == 64


def test_rejects_unregistered_architecture_validator() -> None:
    root = _fixture()
    extra = root / "scripts/check_architecture_unregistered_probe.py"
    extra.write_text("raise SystemExit(0)\n", encoding="utf-8")

    receipt = verifier.verify_repository(root)
    assert receipt["valid"] is False
    assert any("validator inventory drift" in error for error in receipt["errors"])


def test_rejects_nonblocking_rule() -> None:
    root = _fixture()
    path = root / verifier.REGISTRY
    data = _load(path)
    data["rules"][0]["severity"] = "advisory"
    _write(path, data)

    receipt = verifier.verify_repository(root)
    assert receipt["valid"] is False
    assert any("severity must remain blocking" in error for error in receipt["errors"])


def test_rejects_unbounded_waiver_policy() -> None:
    root = _fixture()
    path = root / verifier.REGISTRY
    data = _load(path)
    rule = next(
        item for item in data["rules"]
        if item["waiver_policy"]["allowed"] is True
    )
    rule["waiver_policy"]["max_ttl_days"] = 999
    _write(path, data)

    receipt = verifier.verify_repository(root)
    assert receipt["valid"] is False
    assert any("invalid bounded waiver TTL" in error for error in receipt["errors"])


def test_rejects_masterplan_gap_binding_loss() -> None:
    root = _fixture()
    path = root / verifier.MASTER
    data = _load(path)
    volume = next(item for item in data["volumes"] if item["key"] == "VOL-055")
    # A completed canonical volume has zero gaps. Introducing a new
    # unacknowledged gap is the live drift regression.
    volume["gaps"].append("new unacknowledged architecture requirement")
    _write(path, data)

    receipt = verifier.verify_repository(root)
    assert receipt["valid"] is False
    assert any("gap binding drift" in error for error in receipt["errors"])


def test_rejects_unverified_accountability_closure() -> None:
    root = _fixture()
    path = root / verifier.ACCOUNTABILITY
    data = _load(path)
    item = next(record for record in data["records"] if record["id"] == "ACC-VOL-055")
    item["verification_signoff"]["signed"] = False
    _write(path, data)

    receipt = verifier.verify_repository(root)
    assert receipt["valid"] is False
    assert any("verification_signoff is not signed" in error for error in receipt["errors"])


def test_rejects_nonindependent_signers() -> None:
    root = _fixture()
    path = root / verifier.ACCOUNTABILITY
    data = _load(path)
    item = next(record for record in data["records"] if record["id"] == "ACC-VOL-055")
    item["verification_signoff"]["signer_id"] = item["implementation_signoff"]["signer_id"]
    _write(path, data)

    receipt = verifier.verify_repository(root)
    assert receipt["valid"] is False
    assert any("independent identities" in error for error in receipt["errors"])


def test_rejects_mismatched_evidence_commits() -> None:
    root = _fixture()
    path = root / verifier.ACCOUNTABILITY
    data = _load(path)
    item = next(record for record in data["records"] if record["id"] == "ACC-VOL-055")
    item["verification_signoff"]["git_sha"] = "0" * 40
    _write(path, data)

    receipt = verifier.verify_repository(root)
    assert receipt["valid"] is False
    assert any("evidence commits must match" in error for error in receipt["errors"])


def test_rejects_missing_completed_lifecycle_event() -> None:
    root = _fixture()
    path = root / verifier.ACCOUNTABILITY
    data = _load(path)
    item = next(record for record in data["records"] if record["id"] == "ACC-VOL-055")
    item["history"] = [event for event in item["history"] if event["event_type"] != "completed"]
    _write(path, data)

    receipt = verifier.verify_repository(root)
    assert receipt["valid"] is False
    assert any("completion lifecycle evidence missing" in error for error in receipt["errors"])


def test_rejects_expiry_enforcement_source_weakening() -> None:
    root = _fixture()
    path = root / verifier.VALIDATOR
    source = path.read_text(encoding="utf-8")
    source = source.replace("is expired", "expiry ignored")
    path.write_text(source, encoding="utf-8")

    receipt = verifier.verify_repository(root)
    assert receipt["valid"] is False
    assert any("linter invariant missing" in error for error in receipt["errors"])
