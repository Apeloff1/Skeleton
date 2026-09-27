from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
from types import ModuleType

import pytest

from skeleton.contracts.canonical import EvidenceRef
from skeleton.contracts.promotion_evidence import PromotionEvidenceReceipt
from skeleton.contracts.reproducibility import bundle_from_receipt


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/check_p1_reproducibility.py"
POLICY = Path("machine/p1_reproducibility_policy.json")
HEAD = "a" * 40
NOW = datetime(2026, 9, 27, 20, 0, tzinfo=timezone.utc)


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "check_p1_reproducibility",
        SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _receipt(
    run_id: str = "baseline",
    *,
    environment_digest: str = "c" * 64,
) -> PromotionEvidenceReceipt:
    return PromotionEvidenceReceipt(
        repository="Apeloff1/Skeleton",
        commit_sha=HEAD,
        task_id="P1-EVID-05",
        accountability_id="ACC-P1-EVID-05",
        configuration_digest="b" * 64,
        environment_digest=environment_digest,
        verifier_id="ci:p1-reproducibility",
        verifier_digest="d" * 64,
        test_manifest_digest="e" * 64,
        run_id=run_id,
        run_attempt=1,
        observed_at=NOW,
        evidence=(
            EvidenceRef(
                source="tests:test",
                digest="1" * 64,
                category="test",
            ),
        ),
    )


def _receipt_payload(receipt: PromotionEvidenceReceipt) -> dict:
    return {
        **receipt.to_payload(),
        "receipt_digest": receipt.receipt_digest,
    }


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _copy_policy_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    policy = json.loads((ROOT / POLICY).read_text(encoding="utf-8"))
    _write(root / POLICY, policy)
    for row in policy["runners"]:
        source = ROOT / row["path"]
        target = root / row["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return root


def test_live_policy_resolves_repository_owned_runner_and_budgets() -> None:
    module = _module()

    runners, budgets = module.validate_policy(ROOT)

    assert set(runners) == {
        "promotion-evidence-emitter",
        "provenance-pytest-manifest",
        "p1-reproducibility-verifier",
    }
    assert set(budgets) == {"focused-ci", "independent-replay"}
    assert all(len(row["digest"]) == 64 for row in runners.values())
    assert all(len(row["digest"]) == 64 for row in budgets.values())


def test_policy_contains_no_arbitrary_command_surface() -> None:
    policy = json.loads((ROOT / POLICY).read_text(encoding="utf-8"))

    for runner in policy["runners"]:
        assert set(runner) == {"id", "path", "purpose"}
        assert "command" not in runner
        assert "shell" not in runner


def test_policy_rejects_missing_runner_file(tmp_path: Path) -> None:
    module = _module()
    root = _copy_policy_repo(tmp_path)
    policy = json.loads((root / POLICY).read_text(encoding="utf-8"))
    (root / policy["runners"][0]["path"]).unlink()

    with pytest.raises(module.ReproducibilityCliError, match="runner file missing"):
        module.validate_policy(root)


def test_receipt_loader_rejects_tampered_digest() -> None:
    module = _module()
    payload = _receipt_payload(_receipt())
    payload["subject_digest"] = "f" * 64

    with pytest.raises(module.ReproducibilityCliError, match="subject_digest"):
        module._receipt(payload)


def test_bundle_loader_rejects_tampered_digest() -> None:
    module = _module()
    receipt = _receipt()
    runner_digest, budget_digest = module._policy_binding(
        ROOT,
        "p1-reproducibility-verifier",
        "focused-ci",
    )
    bundle = bundle_from_receipt(
        receipt,
        runner_id="p1-reproducibility-verifier",
        runner_digest=runner_digest,
        budget_id="focused-ci",
        budget_digest=budget_digest,
        source_date_epoch=1_798_000_000,
        inputs=(
            EvidenceRef(
                source="machine/p1_reproducibility_policy.json",
                digest=hashlib.sha256((ROOT / POLICY).read_bytes()).hexdigest(),
                category="configuration",
            ),
        ),
    )
    payload = {**bundle.as_dict(), "bundle_digest": "f" * 64}

    with pytest.raises(module.ReproducibilityCliError, match="bundle_digest"):
        module._bundle(payload)


def _build_bundle(
    module: ModuleType,
    root: Path,
    baseline: PromotionEvidenceReceipt,
) -> Path:
    baseline_file = root / "baseline.json"
    inputs_file = root / "inputs.json"
    bundle_file = root / "bundle.json"
    _write(baseline_file, _receipt_payload(baseline))
    _write(
        inputs_file,
        [
            {
                "source": "machine/p1_reproducibility_policy.json",
                "digest": hashlib.sha256((root / POLICY).read_bytes()).hexdigest(),
                "category": "configuration",
            }
        ],
    )
    args = argparse.Namespace(
        receipt=baseline_file,
        inputs=inputs_file,
        runner_id="p1-reproducibility-verifier",
        budget_id="focused-ci",
        source_date_epoch=1_798_000_000,
        out=bundle_file,
    )
    assert module.build(args) == 0
    return bundle_file


def test_build_and_verify_independent_receipt_end_to_end(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    root = _copy_policy_repo(tmp_path)
    monkeypatch.setattr(module, "ROOT", root)

    bundle_file = _build_bundle(module, root, _receipt("baseline-run"))
    replay_file = root / "replay.json"
    evaluation_file = root / "evaluation.json"
    _write(replay_file, _receipt_payload(_receipt("independent-run")))

    args = argparse.Namespace(
        bundle=bundle_file,
        receipt=replay_file,
        failure_digest=None,
        runner_id="p1-reproducibility-verifier",
        budget_id="focused-ci",
        source_date_epoch=1_798_000_000,
        out=evaluation_file,
    )
    assert module.verify(args) == 0

    evaluation = json.loads(evaluation_file.read_text(encoding="utf-8"))
    assert evaluation["disposition"] == "reproduced"
    assert evaluation["reproduced"] is True
    assert len(evaluation["evaluation_digest"]) == 64


def test_verify_returns_nonzero_with_deterministic_incompatibility(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    root = _copy_policy_repo(tmp_path)
    monkeypatch.setattr(module, "ROOT", root)

    bundle_file = _build_bundle(module, root, _receipt("baseline-run"))
    replay_file = root / "replay.json"
    evaluation_file = root / "evaluation.json"
    _write(
        replay_file,
        _receipt_payload(
            _receipt("independent-run", environment_digest="9" * 64)
        ),
    )

    args = argparse.Namespace(
        bundle=bundle_file,
        receipt=replay_file,
        failure_digest=None,
        runner_id="p1-reproducibility-verifier",
        budget_id="focused-ci",
        source_date_epoch=1_798_000_000,
        out=evaluation_file,
    )
    assert module.verify(args) == 1

    evaluation = json.loads(evaluation_file.read_text(encoding="utf-8"))
    assert evaluation["disposition"] == "incompatible"
    assert evaluation["compatible"] is False
    assert any(
        "environment_digest mismatch" in item
        for item in evaluation["incompatibilities"]
    )
