#!/usr/bin/env python3
"""Emit and verify a non-self-referential exact-head Functional-AI receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
CLOSURE = Path("machine/ai_p2_functional_ai_closure.json")
WORKFLOW = Path(".github/workflows/p2-functional-ai-acceptance.yml")
THIS_SCRIPT = Path("scripts/p2_functional_ai_exact_head.py")
SCHEMA = "skeleton.p2.functional_ai.exact_head_receipt.v1"
WORKFLOW_NAME = "P2 Functional AI Acceptance"
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_PROVIDER_SECRET_NAMES = (
    "OPENAI" + "_API_KEY",
    "ANTHROPIC" + "_API_KEY",
    "XAI" + "_API_KEY",
    "GOOGLE" + "_API_KEY",
    "AZURE_OPENAI" + "_API_KEY",
)
_REQUIRED_SURFACE_KEYS = {
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
}


class ExactHeadReceiptError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExactHeadReceiptError(f"cannot read JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ExactHeadReceiptError(f"JSON root must be an object: {path}")
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ExactHeadReceiptError(f"cannot hash surface: {path}") from exc
    return digest.hexdigest()


def _stable_digest(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _head(value: str) -> str:
    head = value.strip().lower()
    if not _HEX40.fullmatch(head):
        raise ExactHeadReceiptError("head_sha must be exactly 40 lowercase hex characters")
    return head


def _positive_int(value: int | str, field: str) -> int:
    if isinstance(value, bool):
        raise ExactHeadReceiptError(f"{field} must be a positive integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ExactHeadReceiptError(f"{field} must be a positive integer") from exc
    if parsed <= 0:
        raise ExactHeadReceiptError(f"{field} must be a positive integer")
    return parsed


def _surface_paths(root: Path, manifest: Mapping[str, Any]) -> dict[str, Path]:
    surfaces = manifest.get("executable_surfaces")
    if not isinstance(surfaces, dict):
        raise ExactHeadReceiptError("closure executable_surfaces must be an object")
    missing_keys = sorted(_REQUIRED_SURFACE_KEYS - set(map(str, surfaces)))
    if missing_keys:
        raise ExactHeadReceiptError(
            "closure is missing exact-head executable surfaces: " + ", ".join(missing_keys)
        )
    paths: dict[str, Path] = {}
    for key, value in sorted(surfaces.items()):
        if not isinstance(key, str) or not isinstance(value, str) or not value:
            raise ExactHeadReceiptError("closure surface entries must be non-empty strings")
        path = root / value
        if not path.is_file():
            raise ExactHeadReceiptError(f"closure surface is missing: {value}")
        paths[key] = path
    paths["acceptance_workflow"] = root / WORKFLOW
    paths["closure_manifest"] = root / CLOSURE
    paths["receipt_contract"] = root / THIS_SCRIPT
    for key, path in paths.items():
        if not path.is_file():
            raise ExactHeadReceiptError(f"exact-head surface is missing: {key}: {path}")
    return paths


def _assert_credentials_absent(environment: Mapping[str, str]) -> None:
    leaked = [name for name in _PROVIDER_SECRET_NAMES if environment.get(name)]
    if leaked:
        raise ExactHeadReceiptError(
            "hosted-provider credentials are present during standalone acceptance: "
            + ", ".join(leaked)
        )


def build_receipt(
    root: Path,
    *,
    head_sha: str,
    run_id: int | str,
    run_attempt: int | str,
    event_name: str,
    environment: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    head = _head(head_sha)
    run = _positive_int(run_id, "run_id")
    attempt = _positive_int(run_attempt, "run_attempt")
    if not isinstance(event_name, str) or not event_name.strip():
        raise ExactHeadReceiptError("event_name must be non-empty")
    _assert_credentials_absent(os.environ if environment is None else environment)

    manifest = _load(root / CLOSURE)
    if manifest.get("status") != "closed":
        raise ExactHeadReceiptError("Functional-AI closure must be closed before receipt emission")
    policy = manifest.get("exact_head_policy")
    if not isinstance(policy, dict):
        raise ExactHeadReceiptError("closure exact_head_policy is missing")
    expected_policy = {
        "mode": "ephemeral_ci_receipt",
        "receipt_schema": SCHEMA,
        "workflow_name": WORKFLOW_NAME,
        "head_binding": "github_exact_head",
    }
    for key, value in expected_policy.items():
        if policy.get(key) != value:
            raise ExactHeadReceiptError(f"exact_head_policy {key} drift")

    requirements = manifest.get("requirements")
    if not isinstance(requirements, dict):
        raise ExactHeadReceiptError("closure requirements are missing")
    for required in (
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
    ):
        if requirements.get(required) is not True:
            raise ExactHeadReceiptError(f"closure requirement {required} must be true")

    paths = _surface_paths(root, manifest)
    digests = {
        key: {
            "path": str(path.relative_to(root)).replace("\\", "/"),
            "sha256": _sha256_file(path),
        }
        for key, path in sorted(paths.items())
    }
    receipt: dict[str, Any] = {
        "schema_version": SCHEMA,
        "workflow_name": WORKFLOW_NAME,
        "head_sha": head,
        "run_id": run,
        "run_attempt": attempt,
        "event_name": event_name.strip(),
        "claim_scope": "provider_independent_functional_ai_frontier",
        "provider_credentials_present": False,
        "network_required_for_model_inference": False,
        "production_local_weights_runtime": {
            "kind": "llama.cpp-cli",
            "runtime_surface": "skeleton/ai/runtime/inference/llama_cpp.py",
            "model_identity": "sha256",
            "runtime_identity": "sha256",
            "shell": False,
            "prompt_transport": "0600-temporary-file",
        },
        "surface_digests": digests,
    }
    receipt["receipt_digest"] = _stable_digest(receipt)
    return receipt


def validate_receipt(
    root: Path,
    receipt: Mapping[str, Any],
    *,
    expected_head_sha: str,
) -> dict[str, Any]:
    root = root.resolve()
    expected_head = _head(expected_head_sha)
    errors: list[str] = []
    if receipt.get("schema_version") != SCHEMA:
        errors.append("receipt schema drift")
    if receipt.get("workflow_name") != WORKFLOW_NAME:
        errors.append("receipt workflow identity drift")
    if receipt.get("head_sha") != expected_head:
        errors.append("receipt is not bound to the expected exact head")
    if receipt.get("claim_scope") != "provider_independent_functional_ai_frontier":
        errors.append("receipt claim scope drift")
    if receipt.get("provider_credentials_present") is not False:
        errors.append("receipt must prove provider credentials absent")
    if receipt.get("network_required_for_model_inference") is not False:
        errors.append("receipt must prove model inference is network-independent")
    for field in ("run_id", "run_attempt"):
        try:
            _positive_int(receipt.get(field), field)
        except ExactHeadReceiptError as exc:
            errors.append(str(exc))

    runtime = receipt.get("production_local_weights_runtime")
    if not isinstance(runtime, dict):
        errors.append("receipt local weights runtime is missing")
    else:
        expected_runtime = {
            "kind": "llama.cpp-cli",
            "runtime_surface": "skeleton/ai/runtime/inference/llama_cpp.py",
            "model_identity": "sha256",
            "runtime_identity": "sha256",
            "shell": False,
            "prompt_transport": "0600-temporary-file",
        }
        for key, value in expected_runtime.items():
            if runtime.get(key) != value:
                errors.append(f"receipt local runtime {key} drift")

    try:
        manifest = _load(root / CLOSURE)
        paths = _surface_paths(root, manifest)
    except ExactHeadReceiptError as exc:
        errors.append(str(exc))
        paths = {}
    observed = receipt.get("surface_digests")
    if not isinstance(observed, dict):
        errors.append("receipt surface_digests must be an object")
        observed = {}
    expected_keys = set(paths)
    if set(observed) != expected_keys:
        errors.append("receipt surface set does not match current closure authority")
    for key, path in sorted(paths.items()):
        item = observed.get(key)
        if not isinstance(item, dict):
            errors.append(f"receipt surface entry missing: {key}")
            continue
        relative = str(path.relative_to(root)).replace("\\", "/")
        if item.get("path") != relative:
            errors.append(f"receipt surface path drift: {key}")
        try:
            digest = _sha256_file(path)
        except ExactHeadReceiptError as exc:
            errors.append(str(exc))
            continue
        if item.get("sha256") != digest:
            errors.append(f"receipt surface digest mismatch: {key}")

    claimed_digest = receipt.get("receipt_digest")
    core = dict(receipt)
    core.pop("receipt_digest", None)
    if claimed_digest != _stable_digest(core):
        errors.append("receipt self-digest mismatch")

    return {
        "schema_version": 1,
        "status": "valid" if not errors else "rejected",
        "head_sha": expected_head,
        "surface_count": len(paths),
        "errors": errors,
        "valid": not errors,
    }


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    emit = sub.add_parser("emit")
    emit.add_argument("--head-sha", required=True)
    emit.add_argument("--run-id", required=True)
    emit.add_argument("--run-attempt", required=True)
    emit.add_argument("--event-name", required=True)
    emit.add_argument("--output", type=Path, required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--head-sha", required=True)
    verify.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        if args.command == "emit":
            receipt = build_receipt(
                ROOT,
                head_sha=args.head_sha,
                run_id=args.run_id,
                run_attempt=args.run_attempt,
                event_name=args.event_name,
            )
            _write_json(args.output, receipt)
            print(json.dumps({
                "status": "emitted",
                "head_sha": receipt["head_sha"],
                "receipt_digest": receipt["receipt_digest"],
                "surface_count": len(receipt["surface_digests"]),
            }, sort_keys=True))
            return 0
        receipt = _load(args.receipt)
        result = validate_receipt(ROOT, receipt, expected_head_sha=args.head_sha)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["valid"] else 1
    except ExactHeadReceiptError as exc:
        print(f"P2 Functional AI exact-head receipt: rejected: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
