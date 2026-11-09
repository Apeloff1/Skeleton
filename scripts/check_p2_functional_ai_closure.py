#!/usr/bin/env python3
"""Fail-closed verifier for the bounded P2 provider-independent AI frontier."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path("machine/ai_p2_functional_ai_closure.json")
P1 = Path("machine/ai_p1_terminal_closure.json")
P2 = Path("machine/ai_p2_execution_map.json")
BACKLOG = Path("machine/ai_p2_task_backlog.json")
TRANCHE = Path("machine/ai_p2_tranche1_plan.json")
P0 = Path("machine/ai_p0_edge_case_matrix.json")

CRITICAL = {"VOL-007", "VOL-097", "VOL-104"}
FUNCTIONAL_TASK = "P2-T1-FUNCTIONAL-01"
INFERENCE_TASK = "P2-T1-INFER-01"
FORBIDDEN_HOSTED_MARKERS = (
    "api.openai.com",
    "api.x.ai",
    "api.anthropic.com",
    "from openai import",
    "import openai",
)
REQUIRED_EXECUTABLE_SURFACES = {
    "local_inference",
    "llama_cpp_runtime",
    "functional_runtime",
    "local_inference_test",
    "llama_cpp_test",
    "vs001_test",
    "exact_head_receipt",
    "local_model_deployment",
    "local_model_deployment_test",
    "local_model_qualifier",
    "cognitive_execution_runtime",
    "cognitive_execution_runtime_test",
}
REQUIRED_EXACT_HEAD_POLICY = {
    "mode": "ephemeral_ci_receipt",
    "receipt_schema": "skeleton.p2.functional_ai.exact_head_receipt.v1",
    "workflow_name": "P2 Functional AI Acceptance",
    "head_binding": "github_exact_head",
}


class FunctionalAIClosureError(RuntimeError):
    pass


def _load(root: Path, rel: Path) -> dict[str, Any]:
    try:
        value = json.loads((root / rel).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FunctionalAIClosureError(f"cannot read {rel}") from exc
    if not isinstance(value, dict):
        raise FunctionalAIClosureError(f"{rel} must contain an object")
    return value


def validate(root: Path = ROOT, *, require_closed: bool = False) -> dict[str, Any]:
    root = root.resolve()
    manifest = _load(root, MANIFEST)
    p1 = _load(root, P1)
    p2 = _load(root, P2)
    backlog = _load(root, BACKLOG)
    tranche = _load(root, TRANCHE)
    p0 = _load(root, P0)
    errors: list[str] = []

    if manifest.get("schema_version") != "skeleton.p2.functional_ai_closure.v1":
        errors.append("functional closure schema drift")
    allowed_status = {"candidate", "closed"}
    if manifest.get("status") not in allowed_status:
        errors.append("functional closure status must be candidate or closed")
    if require_closed and manifest.get("status") != "closed":
        errors.append("functional closure is not closed")
    if manifest.get("claim_scope") != "provider_independent_functional_ai_frontier":
        errors.append("functional closure claim scope drift")

    claim_limits = manifest.get("claim_limits")
    if not isinstance(claim_limits, dict):
        errors.append("functional closure claim_limits missing")
        claim_limits = {}
    required_true_claims = (
        "provider_independent_execution_proven",
        "advanced_claim_requires_digest_bound_model_eval",
    )
    required_false_claims = (
        "advanced_model_capability_proven",
        "general_intelligence_proven",
        "superintelligence_proven",
        "reference_model_is_quality_target",
        "remaining_p2_capability_volumes_complete",
    )
    for key in required_true_claims:
        if claim_limits.get(key) is not True:
            errors.append(f"claim limit {key} must be true")
    for key in required_false_claims:
        if claim_limits.get(key) is not False:
            errors.append(f"claim limit {key} must be false")
    if claim_limits.get("local_reference_model_kind") != "reference_ngram":
        errors.append("local reference model kind must remain reference_ngram")

    if p1.get("status") != "closed":
        errors.append("P1 terminal authority must be closed")
    if tranche.get("status") != "activated":
        errors.append("P2 T1 must be activated")

    source = set(p2.get("source_scope", {}).get("volume_refs", []))
    scheduled = set(p2.get("first_tranche", {}).get("scheduled_volume_refs", []))
    queued = set(p2.get("first_tranche", {}).get("queued_volume_refs", []))
    if len(source) != 314 or len(scheduled) != 57 or len(queued) != 257:
        errors.append("P2 functional frontier requires exact 314/57/257 partition")
    if source != scheduled | queued or scheduled & queued:
        errors.append("P2 scheduled/queued partition is invalid")
    if not CRITICAL <= scheduled:
        errors.append("critical Functional-AI volumes are not scheduled")
    declared_frontier = set(manifest.get("functional_frontier_volume_refs", []))
    if len(declared_frontier) != 15 or not declared_frontier <= scheduled:
        errors.append("functional frontier must contain the 15 activated T1 volumes")
    if set(manifest.get("critical_volume_refs", [])) != CRITICAL:
        errors.append("critical volume set must be VOL-007/VOL-097/VOL-104")

    tasks = {
        item.get("task_id"): item
        for item in backlog.get("tasks", [])
        if isinstance(item, dict) and item.get("task_id")
    }
    infer = tasks.get(INFERENCE_TASK, {})
    functional = tasks.get(FUNCTIONAL_TASK, {})
    if set(infer.get("primary_volume_refs", [])) != {"VOL-007"}:
        errors.append("VOL-007 must be owned by P2-T1-INFER-01")
    if set(functional.get("primary_volume_refs", [])) != {"VOL-097", "VOL-104"}:
        errors.append("VOL-097/VOL-104 must be owned by P2-T1-FUNCTIONAL-01")

    surfaces = manifest.get("executable_surfaces")
    if not isinstance(surfaces, dict):
        errors.append("executable_surfaces must be an object")
        surfaces = {}
    missing_surface_keys = REQUIRED_EXECUTABLE_SURFACES - set(map(str, surfaces))
    if missing_surface_keys:
        errors.append(
            "functional closure missing executable surface key(s): "
            + ", ".join(sorted(missing_surface_keys))
        )
    for key, rel in surfaces.items():
        if not isinstance(rel, str) or not (root / rel).is_file():
            errors.append(f"missing executable surface {key}: {rel!r}")

    for rel in (
        "skeleton/ai/runtime/inference/local.py",
        "skeleton/ai/runtime/inference/llama_cpp.py",
        "skeleton/ai/runtime/functional_ai.py",
    ):
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except OSError:
            continue
        hits = [marker for marker in FORBIDDEN_HOSTED_MARKERS if marker in text]
        if hits:
            errors.append(f"{rel} owns hosted-provider marker(s): {hits}")

    local = root / "skeleton/ai/runtime/inference/local.py"
    if local.is_file():
        text = local.read_text(encoding="utf-8")
        for marker in (
            "class ReferenceNGramModel",
            "class CallableLocalModel",
            "class LocalInferenceEngine",
            "class LocalInferenceScheduler",
            "class LocalModelAdapter",
        ):
            if marker not in text:
                errors.append(f"local inference missing {marker}")

    llama_path = root / "skeleton/ai/runtime/inference/llama_cpp.py"
    if llama_path.is_file():
        text = llama_path.read_text(encoding="utf-8")
        for marker in (
            "class LlamaCppModel",
            "class LlamaCppConfig",
            "runtime_digest",
            "model_digest",
            "shell=False",
            "prompt_file",
            "LocalToolCall",
            "max_output_bytes",
            "_tool_response_schema",
            "--json-schema-file",
            "validate_json_value",
            "structured_output_schema",
            "class GgufHeader",
            "inspect_gguf",
            "unsupported GGUF version",
        ):
            if marker not in text:
                errors.append(f"llama.cpp local runtime missing marker {marker}")

    deployment_path = root / "skeleton/ai/runtime/inference/deployment.py"
    if deployment_path.is_file():
        text = deployment_path.read_text(encoding="utf-8")
        for marker in (
            "class LocalModelDeployment",
            "load_local_model_adapter",
            "qualify_local_model_deployment",
            "executable_sha256",
            "model_sha256",
        ):
            if marker not in text:
                errors.append(f"local model deployment missing marker {marker}")

    functional_path = root / "skeleton/ai/runtime/functional_ai.py"
    if functional_path.is_file():
        text = functional_path.read_text(encoding="utf-8")
        for marker in (
            "LocalModelAdapter",
            "CognitiveExecutionRuntime",
            "SQLiteExecutionRepository",
            "provider:local:",
            "from_local_model_manifest",
            "local_runtime_digest",
            "startup_qualification_receipt",
            "qualify_local_model_deployment_sync",
        ):
            if marker not in text:
                errors.append(f"VS-001 binding missing marker {marker}")

    w11 = next(
        (
            item
            for item in p0.get("packages", [])
            if isinstance(item, dict) and item.get("id") == "WP-W11"
        ),
        None,
    )
    if not isinstance(w11, dict):
        errors.append("P0 WP-W11 Cognitive Runtime is missing")
    else:
        if w11.get("edge_coverage_status") not in {
            "test_implemented",
            "evidence_passing",
            "accepted",
        }:
            errors.append("P0 WP-W11 has not reached executable test coverage")
        targets = set(map(str, w11.get("test_targets", [])))
        for required in (
            "skeleton/testing/test_local_inference.py",
            "skeleton/testing/test_vs001_functional_ai.py",
        ):
            if required not in targets:
                errors.append(f"P0 WP-W11 missing test target {required}")
        if not w11.get("evidence"):
            errors.append("P0 WP-W11 requires implementation evidence")

    requirements = manifest.get("requirements")
    if not isinstance(requirements, dict):
        errors.append("functional closure requirements missing")
    else:
        false_required = (
            "hosted_provider_credentials_required",
            "network_required_for_model_inference",
        )
        true_required = (
            "local_model_identity_required",
            "governed_tool_authority_required",
            "durable_terminal_state_required",
            "reconnect_replay_required",
            "independent_verification_required",
            "exact_head_ci_required",
            "production_local_weights_runtime_required",
            "runtime_binary_identity_required",
            "model_artifact_identity_required",
            "prompt_argv_forbidden",
            "shell_execution_forbidden",
            "exact_head_receipt_required",
            "deployment_manifest_bootstrap_required",
            "operator_local_model_qualification_required",
            "gguf_format_validation_required",
            "nonzero_tensor_model_required",
            "runtime_identity_bound_to_execution_evidence_required",
            "governed_tool_generation_schema_required",
            "live_startup_local_model_qualification_required",
            "provider_deadline_cancellation_required",
            "cooperative_local_provider_cancellation_required",
            "local_structured_output_schema_parity_required",
        )
        for key in false_required:
            if requirements.get(key) is not False:
                errors.append(f"{key} must be false")
        for key in true_required:
            if requirements.get(key) is not True:
                errors.append(f"{key} must be true")

    exact_head_policy = manifest.get("exact_head_policy")
    if not isinstance(exact_head_policy, dict):
        errors.append("functional closure exact_head_policy missing")
    else:
        for key, value in REQUIRED_EXACT_HEAD_POLICY.items():
            if exact_head_policy.get(key) != value:
                errors.append(f"exact_head_policy {key} drift")

    if manifest.get("status") == "closed":
        for task_id in (
            "P2-T1-DATA-01",
            "P2-T1-SEC-01",
            "P2-T1-INFER-01",
            "P2-T1-RECOVERY-01",
            "P2-T1-FUNCTIONAL-01",
        ):
            task = tasks.get(task_id, {})
            if task.get("status") not in {"landed_unpromoted", "closed"}:
                errors.append(f"closed functional frontier requires {task_id} landed_unpromoted or closed")
            refs = list(map(str, task.get("evidence_refs", [])))
            if not any(ref.startswith("workflow:P2 Functional AI Acceptance@") and ref.endswith(":success") for ref in refs):
                errors.append(f"{task_id} lacks Functional-AI exact-head evidence")

    return {
        "schema_version": 1,
        "status": "valid" if not errors else "rejected",
        "closure_status": manifest.get("status"),
        "source_volume_count": len(source),
        "scheduled_volume_count": len(scheduled),
        "queued_volume_count": len(queued),
        "critical_volume_count": len(CRITICAL),
        "provider_independent": not any(
            "hosted-provider marker" in error for error in errors
        ),
        "claim_limits": dict(claim_limits),
        "production_local_weights_runtime": not any(
            "llama.cpp local runtime" in error for error in errors
        ),
        "exact_head_receipt_policy": not any(
            "exact_head_policy" in error or "executable surface" in error
            for error in errors
        ),
        "errors": errors,
        "valid": not errors,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--require-closed", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = validate(ROOT, require_closed=args.require_closed)
    except FunctionalAIClosureError as exc:
        print(f"P2 Functional AI closure: rejected: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    if not result["valid"]:
        if not args.json:
            for error in result["errors"]:
                print(f"  - {error}", file=sys.stderr)
        return 1
    if not args.json:
        print(
            "P2 Functional AI closure: "
            + ("CLOSED" if result["closure_status"] == "closed" else "CANDIDATE")
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
