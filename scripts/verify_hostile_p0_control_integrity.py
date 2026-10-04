#!/usr/bin/env python3
"""Verify the machine binding for the hostile P0 G013-G016 tranche."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = Path("machine/hostile_p0_control_integrity.json")
EXPECTED_GAPS = ("G013", "G014", "G015", "G016")
SCHEMA = "skeleton.ai.hostile_p0_control_integrity.v1"


class ControlIntegrityContractError(RuntimeError):
    pass


def _load(root: Path, relative: Path) -> dict[str, Any]:
    path = root / relative
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ControlIntegrityContractError(f"missing required file: {relative}") from exc
    except json.JSONDecodeError as exc:
        raise ControlIntegrityContractError(
            f"invalid JSON in {relative}: line {exc.lineno} column {exc.colno}: {exc.msg}"
        ) from exc
    if not isinstance(value, dict):
        raise ControlIntegrityContractError(f"{relative} must contain an object")
    return value


def _repo_path(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ControlIntegrityContractError(f"{field} must be a canonical repository path")
    pure = PurePosixPath(value)
    if pure.is_absolute() or pure.as_posix() != value or any(
        part in {"", ".", ".."} for part in pure.parts
    ):
        raise ControlIntegrityContractError(f"{field} is not a canonical repository path")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    contract = _load(root, CONTRACT)
    if contract.get("schema_version") != SCHEMA:
        raise ControlIntegrityContractError("control-integrity contract schema drift")
    if contract.get("status") != "implementation":
        raise ControlIntegrityContractError("contract status must remain implementation")

    closure = contract.get("closure_policy")
    if not isinstance(closure, dict):
        raise ControlIntegrityContractError("closure_policy must be an object")
    if closure.get("implementation_is_not_closure") is not True:
        raise ControlIntegrityContractError("implementation must not imply closure")
    if closure.get("forbid_self_signing") is not True:
        raise ControlIntegrityContractError("self-signing must remain forbidden")
    required = closure.get("required_before_disposition_promotion")
    if not isinstance(required, list) or len(required) < 3 or not all(
        isinstance(item, str) and item.strip() for item in required
    ):
        raise ControlIntegrityContractError("closure evidence policy is incomplete")

    authority = contract.get("authority")
    if not isinstance(authority, dict):
        raise ControlIntegrityContractError("authority must be an object")
    expected_authority = {
        "hostile_gap_disposition": "machine/ai_hostile_gap_disposition.json",
        "master_plan": "machine/ai_master_plan.json",
        "workflow": ".github/workflows/hostile-p0-control-integrity.yml",
        "verifier": "scripts/verify_hostile_p0_control_integrity.py",
    }
    if authority != expected_authority:
        raise ControlIntegrityContractError("authority path drift")
    for field, relative in expected_authority.items():
        path = _repo_path(relative, f"authority.{field}")
        if not (root / path).is_file():
            raise ControlIntegrityContractError(f"authority path does not exist: {path}")

    hostile = _load(root, Path(expected_authority["hostile_gap_disposition"]))
    raw_gaps = hostile.get("gaps")
    if not isinstance(raw_gaps, list):
        raise ControlIntegrityContractError("hostile gap disposition has no gaps list")
    gaps: dict[str, dict[str, Any]] = {}
    for raw in raw_gaps:
        if not isinstance(raw, dict) or not isinstance(raw.get("id"), str):
            raise ControlIntegrityContractError("hostile gap record is malformed")
        gap_id = raw["id"]
        if gap_id in gaps:
            raise ControlIntegrityContractError(f"duplicate hostile gap id: {gap_id}")
        gaps[gap_id] = raw

    bindings = contract.get("gap_bindings")
    if not isinstance(bindings, list):
        raise ControlIntegrityContractError("gap_bindings must be a list")
    bound_ids: list[str] = []
    mirror_digests: dict[str, str] = {}
    for binding in bindings:
        if not isinstance(binding, dict):
            raise ControlIntegrityContractError("gap binding must be an object")
        if set(binding) != {
            "gap_id", "title", "canonical_path", "ai_mirror_path", "test_path"
        }:
            raise ControlIntegrityContractError("gap binding schema drift")
        gap_id = binding.get("gap_id")
        if not isinstance(gap_id, str):
            raise ControlIntegrityContractError("gap_id must be text")
        bound_ids.append(gap_id)
        source = gaps.get(gap_id)
        if source is None:
            raise ControlIntegrityContractError(f"unknown hostile gap binding: {gap_id}")
        if source.get("severity") != "P0":
            raise ControlIntegrityContractError(f"{gap_id} is no longer P0")
        if binding.get("title") != source.get("title"):
            raise ControlIntegrityContractError(f"{gap_id} title drift")
        if source.get("status") == "superseded":
            raise ControlIntegrityContractError(f"{gap_id} was superseded; contract must reconcile")

        canonical = _repo_path(binding.get("canonical_path"), f"{gap_id}.canonical_path")
        mirror = _repo_path(binding.get("ai_mirror_path"), f"{gap_id}.ai_mirror_path")
        test = _repo_path(binding.get("test_path"), f"{gap_id}.test_path")
        for relative in (canonical, mirror, test):
            if not (root / relative).is_file():
                raise ControlIntegrityContractError(f"{gap_id} required path missing: {relative}")
        canonical_digest = _sha256(root / canonical)
        mirror_digest = _sha256(root / mirror)
        if canonical_digest != mirror_digest:
            raise ControlIntegrityContractError(f"{gap_id} canonical/AI mirror drift")
        mirror_digests[gap_id] = canonical_digest

    if tuple(bound_ids) != EXPECTED_GAPS:
        raise ControlIntegrityContractError(
            f"gap binding order/scope drift: expected {EXPECTED_GAPS}, got {tuple(bound_ids)}"
        )
    if len(set(bound_ids)) != len(bound_ids):
        raise ControlIntegrityContractError("duplicate gap binding")

    return {
        "status": "valid",
        "schema_version": SCHEMA,
        "gap_ids": list(EXPECTED_GAPS),
        "gap_count": len(EXPECTED_GAPS),
        "mirror_sha256": mirror_digests,
        "implementation_is_not_closure": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = validate(Path(args.repo_root))
    except ControlIntegrityContractError as exc:
        print(f"hostile P0 control integrity: FAIL: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(f"hostile P0 control integrity: OK ({result['gap_count']} gaps)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
