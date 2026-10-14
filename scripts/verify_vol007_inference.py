#!/usr/bin/env python3
"""Independent exact-head verifier for VOL-007 inference correctness boundaries.

This verifier does not import the inference runtime. It binds the canonical
masterplan to required source/test/evaluation surfaces and independently
inspects provider-neutral streaming, cancellation/deadline/budget handling,
replay integrity, bounded batching, and speculative semantic-equivalence gates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
MASTER = Path("machine/ai_master_plan.json")
QUALIFICATION_GAP = (
    "independent exact-head VOL-007 Inference Engine Closure "
    "qualification remains pending"
)
SOURCES = (
    Path("skeleton/inference/session.py"),
    Path("skeleton/inference/provider_bridge.py"),
    Path("skeleton/inference/replay.py"),
    Path("skeleton/inference/async_runtime.py"),
    Path("skeleton/inference/batching.py"),
    Path("skeleton/inference/speculation.py"),
)
REQUIRED_PATHS = {
    "skeleton/provider_runtime.py",
    "skeleton/provider_contract.py",
    "backend/core/engine_text.py",
    "skeleton/inference/__init__.py",
    "skeleton/inference/session.py",
    "skeleton/inference/provider_bridge.py",
    "skeleton/inference/replay.py",
    "skeleton/inference/async_runtime.py",
    "skeleton/inference/batching.py",
    "skeleton/inference/speculation.py",
    "scripts/verify_vol007_inference.py",
    ".github/workflows/vol007-inference.yml",
}
REQUIRED_TESTS = {
    "tests/test_model_runtime.py",
    "backend/tests/test_ai_provider_reliability.py",
    "skeleton/testing/test_provider_stream_reliability_profiles.py",
    "skeleton/testing/test_vol007_inference_session.py",
    "skeleton/testing/test_vol007_provider_bridge.py",
    "skeleton/testing/test_vol007_inference_replay.py",
    "skeleton/testing/test_vol007_async_runtime.py",
    "skeleton/testing/test_vol007_batching.py",
    "skeleton/testing/test_vol007_speculation.py",
    "tests/test_vol007_inference_independent.py",
}
REQUIRED_EVALUATIONS = {
    ".github/workflows/vol007-inference.yml",
    "scripts/verify_vol007_inference.py",
}
REQUIRED_CONTRACTS = {
    "ModelRequest",
    "ModelResult",
    "ModelStreamEvent",
    "InferenceUsage",
}

TOKENS = {
    "session.py": (
        "MAX_ATTEMPTS=8",
        "MAX_EVENTS=4096",
        "class ModelRequest",
        "class ModelStreamEvent",
        "class ModelResult",
        'authority_scope:str="inference-result-only"',
        "inference result cannot grant execution authority",
        "terminal stream event required",
        "non-completed result cannot publish response",
    ),
    "provider_bridge.py": (
        "provider delta sequence mismatch",
        "provider response identity mismatch",
        "provider stream did not terminate successfully",
        "terminate_provider_failure",
        "provider_payload_digest",
    ),
    "replay.py": (
        "class InferenceReplay",
        "cross-request replay",
        "replay provider identity mismatch",
        "replay event chain mismatch",
        "replay result mismatch",
    ),
    "async_runtime.py": (
        "class StreamDeadlineExceeded",
        "class StreamBudgetExceeded",
        "asyncio.wait_for",
        'reason="deadline"',
        'reason="cancelled"',
        "invalid stream event budget",
    ),
    "batching.py": (
        "MAX_BATCH_SIZE = 64",
        "MAX_QUEUE_SIZE = 4096",
        "class ContinuousBatchScheduler",
        "duplicate queued operation",
        "duplicate queued request digest",
        "batch queue capacity exceeded",
        'authority_scope: str = "batch-plan-only"',
        "batch plan cannot grant inference authority",
        "verify_batch_membership",
        "batch compatibility mismatch",
    ),
    "speculation.py": (
        "class SpeculativeCandidate",
        "class SpeculationDecision",
        'authority_scope: str = "speculative-candidate-only"',
        'authority_scope: str = "speculation-evidence-only"',
        "speculative candidate cannot grant inference authority",
        "speculation decision cannot grant inference authority",
        "assess_speculative_candidate",
        "require_speculative_equivalence",
        "speculative candidate diverged from authoritative inference result",
        "authoritative_result_digest",
    ),
}


class VerificationError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError(f"cannot load {path}") from exc
    if not isinstance(value, dict):
        raise VerificationError(f"{path} must contain an object")
    return value


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _verify_volume(master: Mapping[str, Any], errors: list[str]) -> dict[str, Any]:
    rows = master.get("volumes")
    volume = next(
        (
            row for row in rows
            if isinstance(row, dict) and row.get("key") == "VOL-007"
        ),
        None,
    ) if isinstance(rows, list) else None
    if not isinstance(volume, dict):
        errors.append("masterplan missing VOL-007")
        return {}

    if volume.get("title") != "Inference Engine":
        errors.append("VOL-007 title drift")
    if volume.get("scope") != "canonical-plan":
        errors.append("VOL-007 scope drift")
    if volume.get("implementation_status") not in {"implemented", "hardened", "verified"}:
        errors.append("VOL-007 implementation status below implemented")

    requirements = tuple(str(item) for item in volume.get("requirements") or [])
    for phrase in (
        "provider-neutral inference with streaming, cancellation, structured output and bounded retries",
        "caches/batching/speculation as optimizations that cannot alter semantic correctness",
        "usage, latency, provider/model identity and terminal reason",
    ):
        if not any(phrase in requirement for requirement in requirements):
            errors.append(f"VOL-007 requirement invariant lost: {phrase}")

    paths = set(volume.get("implementation_paths") or [])
    tests = set(volume.get("tests") or [])
    evaluations = set(volume.get("evaluations") or [])
    contracts = set(volume.get("contracts") or [])
    for label, required, actual in (
        ("implementation path", REQUIRED_PATHS, paths),
        ("test", REQUIRED_TESTS, tests),
        ("evaluation", REQUIRED_EVALUATIONS, evaluations),
        ("contract", REQUIRED_CONTRACTS, contracts),
    ):
        missing = sorted(required - actual)
        if missing:
            errors.append(
                f"VOL-007 {label} binding incomplete: {', '.join(missing)}"
            )

    gaps = list(volume.get("gaps") or [])
    if gaps not in ([QUALIFICATION_GAP], []):
        errors.append(
            "VOL-007 gap state must be qualification-only or signed"
        )
    if gaps and volume.get("completion_checkbox") is True:
        errors.append("VOL-007 cannot remain signed with pending qualification")
    if not gaps and volume.get("completion_checkbox") is not True:
        errors.append("VOL-007 cannot clear qualification gap before signoff")
    if not gaps and volume.get("implementation_status") != "verified":
        errors.append("signed VOL-007 must have verified implementation status")

    binding = {
        "key": volume.get("key"),
        "title": volume.get("title"),
        "implementation_status": volume.get("implementation_status"),
        "completion_checkbox": volume.get("completion_checkbox"),
        "completion_checkbox_mark": volume.get("completion_checkbox_mark"),
        "gaps": gaps,
        "implementation_paths": sorted(paths),
        "tests": sorted(tests),
        "evaluations": sorted(evaluations),
        "contracts": sorted(contracts),
    }
    binding["binding_digest"] = _digest(binding)
    return binding


def verify_repository(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    errors: list[str] = []
    master = _load(root / MASTER)
    binding = _verify_volume(master, errors)
    source_digests: dict[str, str] = {}
    inspected = 0

    for relative in SOURCES:
        path = root / relative
        try:
            data = path.read_bytes()
        except OSError as exc:
            errors.append(f"cannot read inference source {relative}: {type(exc).__name__}")
            continue
        source_digests[relative.as_posix()] = hashlib.sha256(data).hexdigest()
        source = data.decode("utf-8")
        for token in TOKENS[relative.name]:
            inspected += 1
            if token not in source:
                errors.append(
                    f"VOL-007 invariant missing from {relative.name}: {token}"
                )

    receipt: dict[str, Any] = {
        "schema_version": 1,
        "verifier": "independent-vol007-inference-v1",
        "volume": "VOL-007",
        "head_sha": (
            os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
            or os.environ.get("GITHUB_SHA", "").strip()
            or "unknown"
        ),
        "source_digests": source_digests,
        "checked_invariant_count": inspected,
        "volume_binding": binding,
        "errors": errors,
        "valid": not errors,
    }
    receipt["receipt_digest"] = _digest(receipt)
    return receipt


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-out", type=Path)
    parser.add_argument("--print-evidence", action="store_true")
    args = parser.parse_args(argv)
    try:
        receipt = verify_repository(ROOT)
    except VerificationError as exc:
        receipt = {
            "schema_version": 1,
            "verifier": "independent-vol007-inference-v1",
            "volume": "VOL-007",
            "head_sha": (
                os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
                or os.environ.get("GITHUB_SHA", "").strip()
                or "unknown"
            ),
            "errors": [str(exc)],
            "valid": False,
        }
        receipt["receipt_digest"] = _digest(receipt)

    rendered = json.dumps(receipt, sort_keys=True, indent=2)
    if args.evidence_out is not None:
        args.evidence_out.parent.mkdir(parents=True, exist_ok=True)
        args.evidence_out.write_text(rendered + "\n", encoding="utf-8")
    if args.print_evidence:
        print(rendered)
    elif receipt["valid"]:
        print(f"VOL-007 independent inference verification: OK ({receipt['receipt_digest']})")
    else:
        print("VOL-007 independent inference verification: FAIL")
        for error in receipt["errors"]:
            print(f" - {error}")
    return 0 if receipt["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
