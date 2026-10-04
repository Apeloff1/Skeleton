#!/usr/bin/env python3
"""Validate the bounded governed pipeline's canonical contracts and APIs."""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSEMBLY = "machine/ai_training_pipeline.json"
CONTRACTS = {
    "machine/ai_governed_training_data.json": (
        "skeleton.ai.governed_training_data.v1",
        "canonical_owner",
        "skeleton/ai/runtime/training/data.py",
        "executable_tests",
    ),
    "machine/ai_multimodal_training_projection.json": (
        "skeleton.ai.multimodal_training_projection.v1",
        "owner",
        "skeleton/ai/runtime/learning_foundation/multimodal.py",
        "verification",
    ),
    "machine/ai_neural_training_resume_contract.json": (
        "skeleton.ai.neural_training_resume_contract.v1",
        None,
        "skeleton/ai/runtime/training/neural_trainer.py",
        "tests",
    ),
    "machine/ai_model_lifecycle_persistence.json": (
        1,
        "owner",
        "skeleton/ai/runtime/learning_foundation/lifecycle.py",
        "tests",
    ),
    "machine/ai_post_training_execution.json": (
        "skeleton.ai.post_training_execution.v1",
        None,
        "skeleton/ai/runtime/training/learning_pipeline.py",
        "tests",
    ),
    "machine/ai_governed_training_cli.json": (
        "skeleton.ai.governed_training_cli.v1",
        "canonical_owner",
        "skeleton/ai/runtime/training/cli.py",
        "tests",
    ),
    "machine/ai_local_provider_activation.json": (
        "skeleton.ai.local_provider_activation.v1",
        "canonical_owner",
        "skeleton/provider_runtime.py",
        "tests",
    ),
    "machine/ai_engine_provider_inventory.json": (
        "skeleton.ai.engine_provider_inventory.v1",
        "canonical_owner",
        "skeleton/api/engine_routes.py",
        "acceptance",
    ),
    "machine/ai_engine_handoff_recovery.json": (
        "skeleton.ai.engine_handoff_recovery.v1",
        "canonical_owner",
        "skeleton/api/engine_routes.py",
        "acceptance",
    ),
}
APIS = {
    "skeleton/api/engine_routes.py": {None: ("provider_inventory", "execution_handoff")},
    "skeleton/provider_runtime.py": {"LocalArtifactProviderAdapter": ("generate", "available")},
    "skeleton/ai/runtime/training/data.py": {
        "DatasetRegistry": (
            "ingest_materialized",
            "ingest_export",
            "materialized_ingestion",
            "training_corpus",
            "validate_training_corpus",
            "dataset_authority_epoch",
            "assert_dataset_authority",
            "training_authority",
            "source_envelope",
            "latest_materialized_version",
        )
    },
    "skeleton/ai/runtime/learning_foundation/multimodal.py": {
        "MultimodalCorpus": ("export_text_training",),
        "MultimodalTrainingManifest": ("validate_documents",),
    },
    "skeleton/ai/runtime/training/neural_trainer.py": {
        "NeuralLocalTrainer": ("initialize_model", "train", "load_artifact")
    },
    "skeleton/ai/runtime/learning_foundation/lifecycle.py": {
        "ModelLifecycleRegistry": (
            "decision",
            "backup",
            "restore_backup",
            "evaluate_migration",
            "apply_migration",
            "rollback_migration",
        )
    },
    "skeleton/ai/runtime/training/learning_pipeline.py": {
        "PostTrainingRunner": (
            "bind_execution",
            "run_episode",
            "evaluate_stage",
            "evaluate_candidate",
            "qualify_candidate",
            "cancel",
        )
    },
    "skeleton/ai/runtime/training/cli.py": {None: ("build_governed_artifact", "main")},
}
FORBIDDEN_AUTHORITIES = {
    "production_model_promotion_authorized",
    "masterplan_completion_authorized",
    "distributed_execution_supported",
    "distributed_neural_training_supported",
    "completion_checkbox",
    "implementation_signed",
    "verification_signed",
    "may_self_close",
    "promotion_authority",
    "production_routing_authority",
    "grants_production_model_promotion",
    "grants_masterplan_completion",
    "creates_provider_transport",
    "creates_service",
    "new_service",
    "new_provider_transport",
    "new_runtime_root",
    "production_promotion",
    "masterplan_signoff",
}


class TrainingPipelineContractError(RuntimeError):
    """A declared pipeline drifts from its bounded canonical implementation."""


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise TrainingPipelineContractError("duplicate contract field: " + key)
        result[key] = value
    return result


def _read(root: Path, path: str) -> dict:
    try:
        value = json.loads((root / path).read_text(encoding="utf-8"), object_pairs_hook=_strict_object)
    except (OSError, ValueError) as exc:
        raise TrainingPipelineContractError("unreadable contract: " + path) from exc
    if not isinstance(value, dict):
        raise TrainingPipelineContractError("contract must contain an object: " + path)
    return value


def _authority(value, path):
    if isinstance(value, dict):
        for key, child in value.items():
            location = path + "." + key
            if key in FORBIDDEN_AUTHORITIES and child is not False:
                raise TrainingPipelineContractError("unsupported authority: " + location)
            _authority(child, location)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _authority(child, f"{path}[{index}]")


def _python(root: Path, path: str) -> ast.Module:
    try:
        return ast.parse((root / path).read_text(encoding="utf-8"), filename=path)
    except (OSError, ValueError, SyntaxError) as exc:
        raise TrainingPipelineContractError("unreadable executable surface: " + path) from exc


def validate(root: Path = ROOT, *, head: str | None = None) -> dict:
    root = Path(root).resolve()
    if head is not None:
        actual = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=False
        )
        if (
            len(head) != 40
            or any(char not in "0123456789abcdef" for char in head)
            or actual.returncode
            or actual.stdout.strip() != head
        ):
            raise TrainingPipelineContractError("exact head mismatch")
    assembly = _read(root, ASSEMBLY)
    if (
        assembly.get("schema_version") != "skeleton.ai.training_pipeline.v1"
        or assembly.get("scope") != "bounded_local_governed_model_development"
    ):
        raise TrainingPipelineContractError("pipeline scope drift")
    if assembly.get("status") != "implementation_candidate" or assembly.get("contracts") != list(CONTRACTS):
        raise TrainingPipelineContractError("pipeline contract inventory drift")
    for key in (
        "production_model_promotion_authorized",
        "masterplan_completion_authorized",
        "distributed_execution_supported",
    ):
        if assembly.get(key) is not False:
            raise TrainingPipelineContractError("unsupported pipeline authority: " + key)
    _authority(assembly, ASSEMBLY)
    construction = _read(root, "machine/ai_app_construction.json")
    providers = construction.get("runtime_model_providers")
    if not isinstance(providers, list):
        raise TrainingPipelineContractError("missing canonical provider declarations")
    local = [
        provider for provider in providers if isinstance(provider, dict) and provider.get("id") == "local"
    ]
    if len(local) != 1:
        raise TrainingPipelineContractError("local provider must have one canonical declaration")
    declaration = local[0]
    if (
        declaration.get("execution_owner") != "skeleton/provider_runtime.py"
        or declaration.get("credentials") != []
        or declaration.get("capabilities") != ["text-generation"]
        or not str(declaration.get("network_policy", "")).startswith("none;")
    ):
        raise TrainingPipelineContractError("local provider owner/credential/network/capability drift")
    for field in (
        "architecture_read_required",
        "construction_manual_read_required",
        "activation_receipt_required",
    ):
        if declaration.get(field) is not True:
            raise TrainingPipelineContractError(
                "local provider acknowledgement must remain mandatory: " + field
            )
    acceptance = (
        assembly.get("restart_acceptance"),
        assembly.get("operator_acceptance"),
        assembly.get("engine_acceptance"),
    )
    if any(not isinstance(path, str) or not path for path in acceptance):
        raise TrainingPipelineContractError("missing required executable acceptance path")
    tests = set(acceptance)
    for path, (schema, owner_field, owner, test_field) in CONTRACTS.items():
        value = _read(root, path)
        if (
            type(value.get("schema_version")) is not type(schema)
            or value.get("schema_version") != schema
            or value.get("status")
            not in {
                "implementation_candidate",
                "implemented_unpromoted",
            }
        ):
            raise TrainingPipelineContractError("contract schema/status drift: " + path)
        if owner_field and value.get(owner_field) != owner:
            raise TrainingPipelineContractError("canonical owner drift: " + path)
        if not owner_field:
            owners = value.get("canonical_owners")
            if not isinstance(owners, dict) or owner not in owners.values():
                raise TrainingPipelineContractError("canonical owner drift: " + path)
        _authority(value, path)
        if path == "machine/ai_local_provider_activation.json" and (
            value.get("provider_id") != "local"
            or value.get("network_policy") != "none"
            or value.get("credentials") != []
        ):
            raise TrainingPipelineContractError("local provider contract gains external authority")
        declared = value.get(test_field)
        if (
            not isinstance(declared, list)
            or not declared
            or any(not isinstance(test, str) for test in declared)
        ):
            raise TrainingPipelineContractError("missing executable tests: " + path)
        tests.update(declared)
    for path, classes in APIS.items():
        tree = _python(root, path)
        for class_name, methods in classes.items():
            nodes = tree.body
            if class_name is not None:
                cls = next(
                    (
                        node
                        for node in tree.body
                        if isinstance(node, ast.ClassDef) and node.name == class_name
                    ),
                    None,
                )
                if cls is None:
                    raise TrainingPipelineContractError("missing canonical class: " + str(class_name))
                nodes = cls.body
            available = {
                node.name for node in nodes if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            if not set(methods) <= available:
                raise TrainingPipelineContractError(
                    "canonical API drift: " + path + ": " + ", ".join(sorted(set(methods) - available))
                )
    for path in sorted(tests):
        if (
            not isinstance(path, str)
            or not path.startswith("skeleton/testing/")
            or ".." in Path(path).parts
            or not path.endswith(".py")
        ):
            raise TrainingPipelineContractError("test path leaves canonical testing owner")
        tree = _python(root, path)
        if not any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
            for node in ast.walk(tree)
        ):
            raise TrainingPipelineContractError("missing executable test: " + path)
    return {
        "status": "valid",
        "scope": assembly["scope"],
        "contract_count": len(CONTRACTS),
        "api_owner_count": len(APIS),
        "test_file_count": len(tests),
        "production_model_promotion_authorized": False,
        "masterplan_completion_authorized": False,
        "reported_head": head,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--head", help="Require the exact checked-out commit")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = validate(head=args.head)
    except TrainingPipelineContractError as exc:
        print("AI training pipeline: FAIL: " + str(exc), file=sys.stderr)
        return 1
    print(
        json.dumps(result, sort_keys=True, indent=2)
        if args.json
        else "AI training pipeline: OK (bounded local candidate)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
