#!/usr/bin/env python3
"""Validate bounded local-training resume contracts without granting closure."""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = Path("machine/ai_training_resume_contract.json")
OWNERS = {
    "control": "skeleton/ai/runtime/training/control.py",
    "trainer": "skeleton/ai/runtime/training/trainer.py",
}
TESTS = (
    "skeleton/testing/test_p3_training_resume.py",
    "skeleton/testing/test_p3_training_control.py",
    "skeleton/testing/test_p3_local_training_evaluation.py",
)
BINDING_FIELDS = (
    "manifest_digest",
    "dataset_digest",
    "split_name",
    "split_digest",
    "corpus_digest",
    "document_sequence_digest",
    "document_count",
    "token_count",
    "corpus_bytes",
    "model_config",
)
MODEL_CONFIG_FIELDS = ("kind", "model_id", "order", "estimator")
PAYLOAD_FIELDS = (
    "schema_version",
    "binding_digest",
    "cursor",
    "usage",
    "model",
    "finished",
)
CURSOR_FIELDS = ("document_index", "step", "corpus_bytes")
USAGE_FIELDS = ("steps", "documents", "corpus_bytes", "batches")
LIMITS = {
    "default_checkpoint_every_documents": 16,
    "max_checkpoint_every_documents": 4096,
    "max_checkpoint_payload_bytes": 16 * 1024 * 1024,
    "max_document_bytes": 1024 * 1024,
    "max_training_corpus_bytes": 64 * 1024 * 1024,
}
FAILURE_REQUIREMENTS = (
    "payload or binding corruption",
    "immutable retry conflict",
    "stale workers",
    "budget exhaustion",
    "legacy digest-only",
)
RECOVERY_REQUIREMENTS = (
    "initial cursor-zero checkpoint",
    "exact manifest, governed dataset, split, corpus document sequence and model configuration",
    "advancing worker epoch and invalidating old leases",
    "continue after the last committed document without retraining prior batches",
    "reload completed artifact idempotently",
    "fence checkpoint, failure, telemetry and completion",
)
SCOPE_LIMITATIONS = (
    "reference count estimator only",
    "single local worker only",
    "no neural optimizer or collective execution",
    "no automatic production candidate promotion",
    "no blanket AI masterplan closure",
)


class TrainingResumeContractError(RuntimeError):
    pass


def _object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TrainingResumeContractError(f"{field} must contain an object")
    return value


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TrainingResumeContractError(f"{field} must contain non-empty text")
    return value


def _texts(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise TrainingResumeContractError(
            f"{field} must contain non-empty text entries"
        )
    entries = [_text(item, field) for item in value]
    if len(entries) != len(set(entries)):
        raise TrainingResumeContractError(f"{field} contains duplicates")
    return entries


def _fields(value: Any, expected: Sequence[str], field: str) -> None:
    if tuple(_texts(value, field)) != tuple(expected):
        raise TrainingResumeContractError(f"{field} identity drift")


def _read_python(root: Path, path: str) -> ast.Module:
    try:
        return ast.parse((root / path).read_text(encoding="utf-8"), filename=path)
    except (OSError, UnicodeError, SyntaxError) as exc:
        raise TrainingResumeContractError(
            f"cannot read executable surface: {path}"
        ) from exc


def _class(tree: ast.Module, name: str) -> ast.ClassDef:
    node = next(
        (
            item
            for item in tree.body
            if isinstance(item, ast.ClassDef) and item.name == name
        ),
        None,
    )
    if node is None:
        raise TrainingResumeContractError(f"missing canonical API: {name}")
    return node


def _method(owner: ast.ClassDef, name: str, *, parameters: Sequence[str] = ()) -> None:
    node = next(
        (
            item
            for item in owner.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            and item.name == name
        ),
        None,
    )
    if node is None:
        raise TrainingResumeContractError(f"missing canonical API: {owner.name}.{name}")
    args = {
        item.arg
        for item in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)
    }
    if not set(parameters).issubset(args):
        raise TrainingResumeContractError(
            f"canonical API parameter drift: {owner.name}.{name}"
        )


def _check_api(root: Path) -> None:
    control = _read_python(root, OWNERS["control"])
    checkpoint = _class(control, "TrainingCheckpoint")
    fields = {
        node.target.id
        for node in checkpoint.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }
    if "payload_digest" not in fields:
        raise TrainingResumeContractError(
            "TrainingCheckpoint lacks payload_digest identity"
        )
    repository = _class(control, "TrainingRepository")
    for method in (
        "bind_execution",
        "execution_binding",
        "checkpoint_payload",
        "recover",
    ):
        _method(repository, method)
    _method(repository, "checkpoint", parameters=("payload", "lease"))
    for method in ("record_telemetry", "fail", "complete"):
        _method(repository, method, parameters=("lease",))
    trainer = _class(_read_python(root, OWNERS["trainer"]), "ReferenceLocalTrainer")
    _method(trainer, "train", parameters=("checkpoint_every_documents",))


def _reject_promotion(value: Any, path: str = "contract") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            location = f"{path}.{key}"
            if (
                key
                in {
                    "completion_checkbox",
                    "implementation_signed",
                    "verification_signed",
                    "may_self_close",
                    "promotion_authority",
                }
                and child is not False
            ):
                raise TrainingResumeContractError(
                    f"resume contract cannot grant closure authority: {location}"
                )
            _reject_promotion(child, location)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_promotion(child, f"{path}[{index}]")


def _exact_head(root: Path, head: str | None) -> str | None:
    if head is None:
        return None
    if not isinstance(head, str) or re.fullmatch(r"[0-9a-f]{40}", head) is None:
        raise TrainingResumeContractError("invalid exact head")
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise TrainingResumeContractError("git identity unavailable") from exc
    if result.returncode != 0:
        raise TrainingResumeContractError("git identity unavailable")
    if result.stdout.strip() != head:
        raise TrainingResumeContractError("exact head mismatch")
    return head


def validate(root: Path = ROOT, *, head: str | None = None) -> dict[str, Any]:
    root = Path(root).resolve()
    reported_head = _exact_head(root, head)
    try:
        value = json.loads((root / CONTRACT).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TrainingResumeContractError(f"cannot read {CONTRACT}") from exc
    contract = _object(value, "contract")
    if contract.get("schema_version") != "skeleton.ai.training_resume_contract.v1":
        raise TrainingResumeContractError("resume schema drift")
    if contract.get("status") != "implemented_unpromoted":
        raise TrainingResumeContractError(
            "resume implementation must remain unpromoted"
        )
    if contract.get("claim_scope") != "bounded_single_worker_reference_ngram_resume":
        raise TrainingResumeContractError("bounded resume scope drift")
    for field in (
        "production_model_promotion_authorized",
        "distributed_neural_training_supported",
    ):
        if contract.get(field) is not False:
            raise TrainingResumeContractError(f"unsupported resume authority: {field}")
    _reject_promotion(contract)
    if contract.get("canonical_owners") != OWNERS:
        raise TrainingResumeContractError("canonical training owner drift")

    persistence = _object(contract.get("persistence"), "persistence")
    expected_store = {
        "authority": "existing TrainingRepository SQLite database",
        "binding_table": "training_execution_binding",
        "payload_table": "training_checkpoint_payload",
        "commit_boundary": "checkpoint metadata and full payload commit in one fenced BEGIN IMMEDIATE transaction",
    }
    for field, expected in expected_store.items():
        if persistence.get(field) != expected:
            raise TrainingResumeContractError(f"SQLite resume authority drift: {field}")
    for field in ("migration", "rollback"):
        _text(persistence.get(field), f"persistence.{field}")
    binding = _object(contract.get("binding"), "binding")
    if binding.get("schema_version") != "skeleton.reference_training_binding.v1":
        raise TrainingResumeContractError("binding schema drift")
    _fields(binding.get("immutable_fields"), BINDING_FIELDS, "binding.immutable_fields")
    _fields(
        binding.get("model_config_fields"),
        MODEL_CONFIG_FIELDS,
        "binding.model_config_fields",
    )
    _text(binding.get("document_sequence_digest"), "binding.document_sequence_digest")

    payload = _object(contract.get("resume_payload"), "resume_payload")
    if payload.get("schema_version") != "skeleton.reference_training_resume.v1":
        raise TrainingResumeContractError("payload schema drift")
    _fields(payload.get("fields"), PAYLOAD_FIELDS, "resume_payload.fields")
    _fields(payload.get("cursor_fields"), CURSOR_FIELDS, "resume_payload.cursor_fields")
    _fields(payload.get("usage_fields"), USAGE_FIELDS, "resume_payload.usage_fields")
    for field in ("model", "identity", "step_semantics", "budget_semantics"):
        _text(payload.get(field), f"resume_payload.{field}")
    limits = _object(contract.get("limits"), "limits")
    if set(limits) != set(LIMITS) or any(
        type(limits[field]) is not int or limits[field] != expected
        for field, expected in LIMITS.items()
    ):
        raise TrainingResumeContractError("bounded resume limits drift")
    recovery = _texts(contract.get("recovery"), "recovery")
    for requirement in RECOVERY_REQUIREMENTS:
        if not any(requirement in item for item in recovery):
            raise TrainingResumeContractError(
                f"missing recovery requirement: {requirement}"
            )
    failures = _texts(contract.get("failures"), "failures")
    for requirement in FAILURE_REQUIREMENTS:
        if not any(requirement in item for item in failures):
            raise TrainingResumeContractError(
                f"missing fail-closed requirement: {requirement}"
            )
    _fields(contract.get("tests"), TESTS, "tests")
    _fields(contract.get("scope_limitations"), SCOPE_LIMITATIONS, "scope_limitations")
    for path in TESTS:
        test = _read_python(root, path)
        if not any(
            isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            and item.name.startswith("test_")
            for item in ast.walk(test)
        ):
            raise TrainingResumeContractError(
                f"executable resume regression missing: {path}"
            )
    _check_api(root)
    return {
        "status": "valid",
        "claim_scope": contract["claim_scope"],
        "implementation_status": contract["status"],
        "canonical_owner_count": len(OWNERS),
        "executable_test_count": len(TESTS),
        "production_model_promotion_authorized": False,
        "distributed_neural_training_supported": False,
        "reported_head": reported_head,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--head", help="Require and report this exact checked-out commit."
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = validate(head=args.head)
    except TrainingResumeContractError as exc:
        print(f"AI training resume: FAIL: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(result, indent=2, sort_keys=True)
        if args.json
        else "AI training resume: OK (bounded single worker; no promotion authority)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
