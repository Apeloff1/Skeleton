#!/usr/bin/env python3
"""Independent Stage-5 engine/application execution-boundary closure verifier."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
GAP_ID = "gap-engine-application-execution-boundary"
EXPECTED_DEPENDENCIES = {
    "gap-cognitive-execution-loop",
    "gap-state-authority-convergence",
    "gap-provider-surface-convergence",
}
COMPOSE = "docker-compose.yml"
WORKFLOW = ".github/workflows/engine-container-boundary.yml"

REQUIRED_BOUNDARIES: dict[str, tuple[str, ...]] = {
    "backend/core/engine_client.py": (
        "class EngineClientConfig",
        "SKL_ENGINE_SERVICE_TOKEN",
        "class EngineClient",
        "submission_digest",
    ),
    "skeleton/api/engine_routes.py": (
        '@router.post("/executions"',
        "_verified_service_principal",
        "EngineExecutionCommand.from_dict",
    ),
    "skeleton/api/engine_service.py": (
        "class EngineExecutionService",
        "submission_digest",
    ),
    "scripts/check_engine_container_boundary.py": (
        "expect_success_lineage",
        "container retry semantic digest drift",
        "container verification receipt is missing",
        "container terminal result event is not unique",
    ),
    "skeleton/testing/test_engine_process_isolation.py": (
        "test_backend_has_no_local_provider_runtime_activation",
        "test_production_topology_has_single_model_provider_execution_owner",
        "test_backend_compose_has_no_runtime_model_provider_credentials",
        "test_engine_transport_requires_authenticated_service_token",
    ),
    "backend/tests/test_engine_http_boundary.py": (
        "test_backend_client_crosses_authenticated_engine_boundary_idempotently",
        "test_http_golden_journey_preserves_provider_tool_verification_lineage",
        "test_http_cancel_fences_late_provider_result",
    ),
    "backend/tests/test_engine_live_process_boundary.py": (
        "test_engine_client_crosses_real_tcp_process_boundary",
        "test_engine_successful_lineage_crosses_real_tcp_process_boundary",
    ),
}


class VerificationError(RuntimeError):
    """Stage-5 closure verification could not be completed."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError(f"cannot read {path}") from exc
    if not isinstance(value, dict):
        raise VerificationError(f"{path} must contain an object")
    return value


def _entry(items: object, key: str, value: str) -> dict[str, Any] | None:
    if not isinstance(items, list):
        return None
    return next(
        (
            item
            for item in items
            if isinstance(item, dict) and item.get(key) == value
        ),
        None,
    )


def _service_block(source: str, service: str) -> str:
    lines = source.splitlines()
    marker = f"  {service}:"
    try:
        start = lines.index(marker)
    except ValueError:
        return ""
    body: list[str] = []
    for line in lines[start + 1 :]:
        stripped = line.lstrip(" ")
        indent = len(line) - len(stripped)
        if stripped and indent <= 2:
            break
        body.append(line)
    return "\n".join(body)


def verify_repository(root: Path = ROOT) -> dict[str, Any]:
    errors: list[str] = []
    digests: dict[str, str] = {}

    for rel, tokens in REQUIRED_BOUNDARIES.items():
        path = root / rel
        if not path.is_file():
            errors.append(f"missing Stage-5 boundary: {rel}")
            continue
        source = path.read_text(encoding="utf-8")
        for token in tokens:
            if token not in source:
                errors.append(f"{rel} lost Stage-5 token: {token}")
        digests[rel] = hashlib.sha256(path.read_bytes()).hexdigest()

    construction = _load_json(root / "machine/ai_app_construction.json")
    handoff = _load_json(root / "machine/ai_implementation_handoff.json")
    closure = _load_json(root / "machine/ai_closure_evidence.json")

    gap = _entry(construction.get("gap_register"), "id", GAP_ID)
    hand = _entry(handoff.get("entries"), "gap", GAP_ID)
    evidence = _entry(closure.get("entries"), "gap", GAP_ID)
    blueprint = construction.get("engine_application_boundary_blueprint")

    if gap is None or gap.get("status") != "closed":
        errors.append("Stage-5 construction gap is not closed")
    if not isinstance(blueprint, dict) or blueprint.get("status") != "complete":
        errors.append("Stage-5 engine application boundary blueprint is not complete")

    if hand is None:
        errors.append("Stage-5 implementation handoff is missing")
    else:
        if hand.get("implementation_status") != "closed":
            errors.append("Stage-5 implementation handoff is not closed")
        if set(hand.get("depends_on") or []) != EXPECTED_DEPENDENCIES:
            errors.append("Stage-5 handoff dependency graph drift")
        if hand.get("remaining") not in ([], None):
            errors.append("Stage-5 handoff still has remaining work")

    dependency_states = {
        item.get("id"): item.get("status")
        for item in construction.get("gap_register", [])
        if isinstance(item, dict) and item.get("id") in EXPECTED_DEPENDENCIES
    }
    if set(dependency_states) != EXPECTED_DEPENDENCIES:
        errors.append("Stage-5 dependency inventory is incomplete")
    elif any(state != "closed" for state in dependency_states.values()):
        errors.append("Stage-5 has non-closed dependencies")

    if evidence is None:
        errors.append("Stage-5 closure evidence is missing")
    else:
        for field in ("gap_status", "implementation_state", "closure_decision"):
            if evidence.get(field) != "closed":
                errors.append(f"Stage-5 {field} is not closed")
        if evidence.get("outstanding_evidence") not in ([], None):
            errors.append("Stage-5 closure still has outstanding evidence")
        if evidence.get("blockers") not in ([], None):
            errors.append("Stage-5 closure still has blockers")
        present = evidence.get("evidence_present")
        if not isinstance(present, list) or len(present) < 10:
            errors.append("Stage-5 executable evidence inventory is incomplete")

    workflow_path = root / WORKFLOW
    if not workflow_path.is_file():
        errors.append("Engine Container Boundary workflow is missing")
    else:
        workflow = workflow_path.read_text(encoding="utf-8")
        required_workflow_tokens = (
            "github.event.pull_request.head.sha",
            "scripts/check_engine_container_boundary.py",
            "--expect-success-lineage",
            "docker compose -f docker-compose.yml up -d --build mongo skeleton",
            "Assert provider credentials are engine-only",
            "scripts/verify_engine_application_boundary_closure.py",
        )
        for token in required_workflow_tokens:
            if token not in workflow:
                errors.append(f"engine boundary workflow lost token: {token}")
        digests[WORKFLOW] = hashlib.sha256(workflow_path.read_bytes()).hexdigest()

    compose_path = root / COMPOSE
    if not compose_path.is_file():
        errors.append("canonical docker-compose.yml is missing")
    else:
        compose = compose_path.read_text(encoding="utf-8")
        engine = _service_block(compose, "skeleton")
        backend = _service_block(compose, "backend")
        if not engine or not backend:
            errors.append("canonical engine/backend service topology is incomplete")
        for credential in ("OPENAI_API_KEY", "EMERGENT_LLM_KEY"):
            if credential not in engine:
                errors.append(f"{credential} missing from Skeleton engine service")
            if credential in backend:
                errors.append(f"{credential} leaked into backend service")
        for service_name, block in (("skeleton", engine), ("backend", backend)):
            if "SKL_ENGINE_SERVICE_TOKEN" not in block:
                errors.append(
                    f"engine service token missing from {service_name} service"
                )
        digests[COMPOSE] = hashlib.sha256(compose_path.read_bytes()).hexdigest()

    return {
        "schema_version": 1,
        "verifier": "independent-engine-application-boundary-v1",
        "gap_id": GAP_ID,
        "head_sha": (
            os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
            or os.environ.get("GITHUB_SHA", "").strip()
            or "unknown"
        ),
        "dependency_graph": sorted(EXPECTED_DEPENDENCIES),
        "boundary_digests": digests,
        "errors": errors,
        "valid": not errors,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-out", type=Path)
    parser.add_argument("--print-evidence", action="store_true")
    args = parser.parse_args(argv)
    try:
        receipt = verify_repository(ROOT)
    except VerificationError as exc:
        print(f"engine-application-boundary: rejected: {exc}", file=sys.stderr)
        return 1
    if args.evidence_out:
        args.evidence_out.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.print_evidence:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    if not receipt["valid"]:
        print("engine-application-boundary: rejected", file=sys.stderr)
        for error in receipt["errors"]:
            print(f" - {error}", file=sys.stderr)
        return 1
    print(
        "engine-application-boundary: OK "
        f"(boundaries={len(receipt['boundary_digests'])})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
