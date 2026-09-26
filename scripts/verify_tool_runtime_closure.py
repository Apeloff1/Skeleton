#!/usr/bin/env python3
"""Independent tool-runtime closure verifier.

This verifier intentionally does not import the canonical tool runtime or its
primary boundary validator. It checks source ownership, manifest governance,
lineage, durable receipt fencing, admission/concurrency bindings, compatibility
delegation, forbidden privileged-body drift, AI-tree mirror parity, and the
declared dependency graph directly from repository files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]

BOUNDARIES: dict[str, tuple[str, ...]] = {
    "skeleton/skills/tool_contract.py": (
        "ToolAuthorityClass",
        "ToolRiskClass",
        "ToolSideEffectClass",
        "ToolIdempotencyMode",
        "ToolApprovalPolicy",
        "output_schema",
        "result_size_limit",
        "max_concurrency",
        "enabled",
        "execution_id",
        "turn_id",
        "call_id",
    ),
    "skeleton/skills/tool_runtime.py": (
        "AdmissionRuntime",
        "record_usage_event",
        "meter_tool_call",
        "asyncio.Semaphore",
        "receipt_store",
        "execution_id",
        "turn_id",
        "call_id",
    ),
    "skeleton/skills/tool_receipt_store.py": (
        "execution_id",
        "turn_id",
        "call_id",
        "idempotency",
        "CREATE TABLE",
        "ALTER TABLE",
    ),
    "skeleton/skills/tool_adapters/owners.py": (
        "AsyncSandboxCompileAdapter",
        "AsyncDatabaseQueryAdapter",
        "AsyncNetworkSearchAdapter",
        "AsyncArtifactPackageAdapter",
        "AsyncVaultQueryAdapter",
        "AsyncJeevesConsultAdapter",
    ),
    "backend/services/tool_registry.py": (
        "AsyncSandboxCompileAdapter",
        "AsyncDatabaseQueryAdapter",
        "AsyncNetworkSearchAdapter",
        "AsyncArtifactPackageAdapter",
        "AsyncVaultQueryAdapter",
        "AsyncJeevesConsultAdapter",
        "provider_tool_retired",
        "GovernanceRegistry",
        "result_size_limit",
        "max_concurrency",
        "execution_id",
        "turn_id",
        "call_id",
    ),
    "skeleton/intelligence/execution_runtime.py": (
        "execution_id",
        "turn_id",
        "call_id",
        "manifest.enabled",
        "input_schema",
        "tool_id",
    ),
}

FORBIDDEN_REGISTRY_TOKENS = (
    "import subprocess",
    "from subprocess",
    "DDGS(",
    "pymongo",
    "MongoClient(",
    "requests.",
    "httpx.",
    "urllib.request",
    "os.system",
    "Popen(",
)

MIRROR_PAIRS: tuple[tuple[str, str], ...] = (
    (
        "skeleton/skills/tool_contract.py",
        "skeleton/ai/runtime/skills/tool_contract.py",
    ),
    (
        "skeleton/skills/tool_runtime.py",
        "skeleton/ai/runtime/skills/tool_runtime.py",
    ),
    (
        "skeleton/skills/tool_receipt_store.py",
        "skeleton/ai/runtime/skills/tool_receipt_store.py",
    ),
    (
        "skeleton/skills/tool_adapters/owners.py",
        "skeleton/ai/runtime/skills/tool_adapters/owners.py",
    ),
    (
        "skeleton/intelligence/execution_runtime.py",
        "skeleton/ai/runtime/intelligence/execution_runtime.py",
    ),
)

EXPECTED_DEPENDENCIES = {
    "gap-governance-registry",
    "gap-cost-admission",
    "gap-provider-surface-convergence",
}


class VerificationError(RuntimeError):
    """Independent tool-runtime verification failed."""


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise VerificationError(f"cannot read {path}") from exc


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError(f"cannot read {path}") from exc
    if not isinstance(payload, dict):
        raise VerificationError(f"{path} must contain an object")
    return payload


def _verify_boundaries(root: Path, errors: list[str]) -> dict[str, str]:
    digests: dict[str, str] = {}
    for rel, tokens in BOUNDARIES.items():
        path = root / rel
        if not path.is_file():
            errors.append(f"tool-runtime boundary is missing: {rel}")
            continue
        source = _read_text(path)
        for token in tokens:
            if token not in source:
                errors.append(f"{rel} lost tool-runtime token: {token}")
        digests[rel] = hashlib.sha256(source.encode("utf-8")).hexdigest()

    registry = root / "backend/services/tool_registry.py"
    if registry.is_file():
        source = _read_text(registry)
        for token in FORBIDDEN_REGISTRY_TOKENS:
            if token in source:
                errors.append(
                    "backend tool registry regained privileged execution body: "
                    + token
                )
    return digests


def _verify_mirrors(root: Path, errors: list[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for source_rel, mirror_rel in MIRROR_PAIRS:
        source = root / source_rel
        mirror = root / mirror_rel
        if not source.is_file():
            errors.append(f"canonical mirror source is missing: {source_rel}")
            continue
        if not mirror.is_file():
            errors.append(f"canonical AI mirror is missing: {mirror_rel}")
            continue
        try:
            source_bytes = source.read_bytes()
            mirror_bytes = mirror.read_bytes()
        except OSError as exc:
            errors.append(
                f"cannot verify mirror pair {source_rel} -> {mirror_rel}: "
                + type(exc).__name__
            )
            continue
        source_digest = hashlib.sha256(source_bytes).hexdigest()
        mirror_digest = hashlib.sha256(mirror_bytes).hexdigest()
        rows.append(
            {
                "source": source_rel,
                "mirror": mirror_rel,
                "source_digest": source_digest,
                "mirror_digest": mirror_digest,
            }
        )
        if source_bytes != mirror_bytes:
            errors.append(
                f"canonical AI mirror drift: {source_rel} != {mirror_rel}"
            )
    return rows


def _verify_dependency_graph(root: Path, errors: list[str]) -> dict[str, Any]:
    handoff = _load_json(root / "machine/ai_implementation_handoff.json")
    entries = handoff.get("entries")
    if not isinstance(entries, list):
        errors.append("implementation handoff entries must be a list")
        return {}
    entry = next(
        (
            item
            for item in entries
            if isinstance(item, dict)
            and item.get("gap") == "gap-tool-runtime-convergence"
        ),
        None,
    )
    if entry is None:
        errors.append("tool-runtime handoff entry is missing")
        return {}
    dependencies = entry.get("depends_on")
    if not isinstance(dependencies, list):
        errors.append("tool-runtime depends_on must be a list")
        return entry
    actual = set(str(item) for item in dependencies)
    if actual != EXPECTED_DEPENDENCIES:
        errors.append(
            "tool-runtime dependency graph mismatch: "
            + ", ".join(sorted(actual))
        )
    closure_gate = str(entry.get("closure_gate") or "")
    for phrase in (
        "declared",
        "minimally projected",
        "policy-admitted",
        "idempotency-aware",
        "receipt-backed",
    ):
        if phrase not in closure_gate:
            errors.append(
                "tool-runtime closure gate lost invariant phrase: " + phrase
            )
    return entry


def verify_repository(root: Path = ROOT) -> dict[str, Any]:
    errors: list[str] = []
    boundary_digests = _verify_boundaries(root, errors)
    mirrors = _verify_mirrors(root, errors)
    handoff = _verify_dependency_graph(root, errors)

    handoff_digest = hashlib.sha256(
        json.dumps(
            handoff,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()

    return {
        "schema_version": 1,
        "verifier": "independent-tool-runtime-v1",
        "head_sha": os.environ.get("GITHUB_SHA", "").strip() or "unknown",
        "boundary_digests": boundary_digests,
        "mirror_pairs": mirrors,
        "dependency_graph": sorted(EXPECTED_DEPENDENCIES),
        "handoff_digest": handoff_digest,
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
        print(f"independent-tool-runtime: rejected: {exc}", file=sys.stderr)
        return 1

    if args.evidence_out is not None:
        args.evidence_out.parent.mkdir(parents=True, exist_ok=True)
        args.evidence_out.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.print_evidence:
        print(json.dumps(receipt, indent=2, sort_keys=True))

    if not receipt["valid"]:
        print("independent-tool-runtime: rejected", file=sys.stderr)
        for error in receipt["errors"]:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(
        "independent-tool-runtime: OK "
        f"(boundaries={len(receipt['boundary_digests'])}, "
        f"mirrors={len(receipt['mirror_pairs'])})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
