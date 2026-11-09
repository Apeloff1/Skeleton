#!/usr/bin/env python3
"""Independent cost/admission closure verifier.

This verifier intentionally does not import the runtime admission, quota, or
pressure implementations. It verifies the machine contract, production
boundary bindings, durable-schema tokens, and canonical AI-tree mirror parity
from source bytes only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
CONSTRUCTION = Path("machine/ai_app_construction.json")

BOUNDARIES: dict[str, tuple[str, ...]] = {
    "skeleton/provider_runtime.py": (
        "AdmissionRuntime",
        "admission_runtime",
        "_admit_provider_request",
        "_release_provider_lease",
    ),
    "skeleton/skills/tool_runtime.py": (
        "AdmissionRuntime",
        "record_usage_event",
        "meter_tool_call",
        "admission_runtime",
    ),
    "skeleton/api/engine_service.py": (
        "AdmissionRuntime",
        "meter_execution_storage",
        "meter_storage",
        "max_storage_bytes",
    ),
    "skeleton/artifact_plane/usage.py": (
        "AdmissionRuntime",
        "meter_artifact",
        "meter_storage",
        "storage_bytes",
    ),
    "backend/core/conversations.py": (
        "admit_storage_write",
        "storage_bytes",
    ),
    "backend/core/engine_client.py": (
        "admit_storage_write",
        "storage_bytes",
    ),
    "skeleton/memory/writeback.py": (
        "AdmissionRuntime",
        "meter_storage",
        "storage_bytes",
    ),
    "skeleton/memory/projection.py": (
        "AdmissionRuntime",
        "admission_runtime",
        "storage_bytes",
    ),
    "skeleton/intelligence/admission_runtime.py": (
        "AdmissionRuntime",
        "telemetry_snapshot",
        "record_usage_event",
        "meter_storage_bytes",
        "meter_artifact_bytes",
        "SqliteSharedPressureLedger",
    ),
    "skeleton/intelligence/quota_sqlite.py": (
        "SqliteTenantQuotaLedger",
        "max_storage_bytes",
        "committed_storage_bytes",
        "estimate_storage_bytes",
        "actual_storage_bytes",
        "delta_storage_bytes",
        "BEGIN IMMEDIATE",
    ),
    "skeleton/intelligence/shared_pressure.py": (
        "SqliteSharedPressureLedger",
        "BEGIN IMMEDIATE",
        "max_concurrency",
        "max_queue_depth",
        "max_tenant_concurrency",
        "max_tenant_queue_depth",
    ),
}

MIRROR_PAIRS: tuple[tuple[str, str], ...] = (
    (
        "skeleton/skills/tool_runtime.py",
        "skeleton/ai/runtime/skills/tool_runtime.py",
    ),
    (
        "skeleton/api/engine_service.py",
        "skeleton/ai/runtime/api/engine_service.py",
    ),
    (
        "skeleton/artifact_plane/usage.py",
        "skeleton/ai/runtime/artifact_plane/usage.py",
    ),
    (
        "skeleton/memory/writeback.py",
        "skeleton/ai/runtime/memory/writeback.py",
    ),
    (
        "skeleton/memory/projection.py",
        "skeleton/ai/runtime/memory/projection.py",
    ),
    (
        "skeleton/intelligence/admission_runtime.py",
        "skeleton/ai/runtime/intelligence/admission_runtime.py",
    ),
    (
        "skeleton/intelligence/quota_sqlite.py",
        "skeleton/ai/runtime/intelligence/quota_sqlite.py",
    ),
    (
        "skeleton/intelligence/shared_pressure.py",
        "skeleton/ai/runtime/intelligence/shared_pressure.py",
    ),
)

REQUIRED_BUDGET_DIMENSIONS = {
    "input_tokens",
    "output_tokens",
    "provider_cost",
    "tool_cost",
    "artifact_bytes",
    "storage_bytes",
    "wall_seconds",
    "provider_concurrency",
    "tool_concurrency",
    "queue_slots",
}


class VerificationError(RuntimeError):
    """Independent cost/admission verification failed."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError(f"cannot read {path}") from exc
    if not isinstance(payload, dict):
        raise VerificationError(f"{path} must contain an object")
    return payload


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise VerificationError(f"cannot read source {path}") from exc


def _verify_machine_contract(root: Path, errors: list[str]) -> dict[str, Any]:
    contract = _load_json(root / CONSTRUCTION)
    gaps = contract.get("gap_register")
    if not isinstance(gaps, list):
        errors.append("gap_register must be a list")
        return contract
    gap = next(
        (
            item
            for item in gaps
            if isinstance(item, dict)
            and item.get("id") == "gap-cost-admission"
        ),
        None,
    )
    if gap is None:
        errors.append("gap-cost-admission is missing from gap_register")
    elif gap.get("status") not in {"open", "closed"}:
        errors.append("gap-cost-admission has invalid status")

    blueprint = contract.get("cost_admission_blueprint")
    if not isinstance(blueprint, dict):
        errors.append("cost_admission_blueprint must be an object")
        return contract

    dimensions = blueprint.get("budget_dimensions")
    if not isinstance(dimensions, list):
        errors.append("cost admission budget_dimensions must be a list")
    else:
        missing = sorted(REQUIRED_BUDGET_DIMENSIONS - set(dimensions))
        if missing:
            errors.append(
                "cost admission blueprint missing budget dimensions: "
                + ", ".join(missing)
            )

    durable = blueprint.get("durable_quota")
    if not isinstance(durable, dict):
        errors.append("cost admission durable_quota must be an object")
    else:
        if durable.get("reference_backend") != "skeleton/intelligence/quota_sqlite.py":
            errors.append("durable quota reference backend is not canonical SQLite owner")
        invariants = durable.get("invariants")
        if not isinstance(invariants, list) or not invariants:
            errors.append("durable quota invariants are missing")

    pressure = blueprint.get("pressure")
    if not isinstance(pressure, dict):
        errors.append("cost admission pressure contract must be an object")
    else:
        distributed = str(pressure.get("distributed") or "").lower()
        if "shared" not in distributed or "durable" not in distributed:
            errors.append("distributed pressure contract is not shared/durable")

    evidence = blueprint.get("closure_evidence")
    if not isinstance(evidence, list):
        errors.append("cost admission closure_evidence must be a list")
    else:
        required_phrases = (
            "durable quota restart",
            "multi-worker reservation race",
            "actual usage reconciliation",
            "unknown-usage behavior",
            "no expensive provider/tool/storage path without admission receipt",
        )
        joined = "\n".join(str(item) for item in evidence).lower()
        for phrase in required_phrases:
            if phrase.lower() not in joined:
                errors.append(
                    "cost admission blueprint lost closure evidence phrase: "
                    + phrase
                )
    return contract


def _verify_boundaries(root: Path, errors: list[str]) -> dict[str, str]:
    digests: dict[str, str] = {}
    for rel, tokens in BOUNDARIES.items():
        path = root / rel
        if not path.is_file():
            errors.append(f"cost/admission boundary is missing: {rel}")
            continue
        source = _read_text(path)
        for token in tokens:
            if token not in source:
                errors.append(f"{rel} lost admission token: {token}")
        digests[rel] = hashlib.sha256(source.encode("utf-8")).hexdigest()
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


def verify_repository(root: Path = ROOT) -> dict[str, Any]:
    errors: list[str] = []
    contract = _verify_machine_contract(root, errors)
    boundary_digests = _verify_boundaries(root, errors)
    mirror_rows = _verify_mirrors(root, errors)

    blueprint = contract.get("cost_admission_blueprint")
    blueprint_digest = hashlib.sha256(
        json.dumps(
            blueprint if isinstance(blueprint, dict) else {},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()

    return {
        "schema_version": 1,
        "verifier": "independent-cost-admission-v1",
        "head_sha": os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
            or os.environ.get("GITHUB_SHA", "").strip()
            or "unknown",
        "blueprint_digest": blueprint_digest,
        "boundary_digests": boundary_digests,
        "mirror_pairs": mirror_rows,
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
        print(f"independent-cost-admission: rejected: {exc}", file=sys.stderr)
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
        print("independent-cost-admission: rejected", file=sys.stderr)
        for error in receipt["errors"]:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(
        "independent-cost-admission: OK "
        f"(boundaries={len(receipt['boundary_digests'])}, "
        f"mirrors={len(receipt['mirror_pairs'])})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
