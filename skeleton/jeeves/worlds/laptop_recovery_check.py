"""Read-only, bounded Jeeves laptop recovery qualification entry point.

This command reports source, review, compiled handoff and optional player-save
custody without implicitly approving, compiling, or overwriting any artifact.
It is intentionally not a model, native engine or device certification.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .laptop_flow import LaptopFlow
from .world_canon import CanonError, _id, canonical

MAX_REPORT_BYTES = 65536


def inspect_recovery(store: str | Path, world_id: str, slot: str | None = None,
                     expected_source_digest: str | None = None) -> dict:
    """Return a deterministic, fail-closed recovery result.

    A diagnostic's green state is evidence only for the observed source
    snapshot. Operators must still validate exact-head CI and real devices.
    """
    _id(world_id, "world_id")
    if slot is not None:
        _id(slot, "slot")
    if expected_source_digest is not None:
        if (len(expected_source_digest) != 64 or
                any(c not in "0123456789abcdef" for c in expected_source_digest)):
            raise CanonError("expected_source_digest_invalid")
    report = LaptopFlow(store).diagnose(world_id, slot)
    checks = report.get("checks", {})
    ready = (
        checks.get("source", {}).get("ok") is True
        and checks.get("review", {}).get("ok") is True
        and checks.get("builder", {}).get("ok") is True
        and checks.get("acceptance", {}).get("ok") is True
        and (slot is None or checks.get("session", {}).get("ok") is True)
    )
    lease_ok = (expected_source_digest is None or
                report.get("source_digest") == expected_source_digest)
    if expected_source_digest is not None:
        checks["source_lease"] = (
            {"ok": True} if lease_ok else
            {"ok": False, "error": "source_digest_mismatch"}
        )
    ready = ready and lease_ok
    return {
        "schema": "jeeves.world.laptop_recovery_check.v1",
        "world_id": world_id,
        "slot": slot,
        "source_handoff_verified": ready,
        "source_digest": report.get("source_digest"),
        "expected_source_digest": expected_source_digest,
        "next_action": ("restart_diagnostic_after_source_change" if
                        expected_source_digest is not None and
                        report.get("source_digest") != expected_source_digest
                        else report.get("next_action")),
        "checks": checks,
        "qualification": "read_only_source_diagnostic_not_model_engine_or_device_certified",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", required=True, help="Existing canonical world store")
    parser.add_argument("--world-id", required=True)
    parser.add_argument("--slot", help="Existing player save slot to validate")
    parser.add_argument("--expect-source-digest", help="Fail closed unless canonical source matches this SHA-256")
    args = parser.parse_args(argv)
    try:
        result = inspect_recovery(args.store, args.world_id, args.slot, args.expect_source_digest)
        payload = canonical(result)
        if len(payload) > MAX_REPORT_BYTES:
            raise CanonError("laptop_recovery_report_too_large")
        sys.stdout.buffer.write(payload + b"\n")
        return 0 if result["source_handoff_verified"] else 2
    except (CanonError, OSError, ValueError) as exc:
        code = exc.code if isinstance(exc, CanonError) else "laptop_recovery_unavailable"
        sys.stdout.write(json.dumps({
            "schema": "jeeves.world.laptop_recovery_check.v1",
            "source_handoff_verified": False,
            "error": code,
            "next_action": "inspect_canonical_custody_without_overwriting_artifacts",
        }, sort_keys=True) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
