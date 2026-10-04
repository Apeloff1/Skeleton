#!/usr/bin/env python3
"""Independent terminal masterplan completion verifier.

The verifier is intentionally data-only: it does not import the implementation
under test. It proves that the canonical construction ledger contains the full
known gap inventory with no open gap, that every existing implementation
handoff/closure record agrees with the closed state, and that bound blueprints
are complete.
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

EXPECTED_GAPS = {
    "gap-conversation-state-authority",
    "gap-tool-runtime-convergence",
    "gap-context-compiler-convergence",
    "gap-verification-evidence-contract",
    "gap-provider-interaction-protocol",
    "gap-engine-application-execution-boundary",
    "gap-cognitive-execution-loop",
    "gap-streaming-protocol",
    "gap-governance-registry",
    "gap-feedback-promotion",
    "gap-memory-durable-authority",
    "gap-state-authority-convergence",
    "gap-cost-admission",
    "gap-provider-redundancy",
    "gap-e2e-golden-journeys",
    "gap-release-slo-loop",
    "gap-provider-surface-convergence",
}

P1_GAPS = {
    "gap-feedback-promotion",
    "gap-provider-redundancy",
    "gap-release-slo-loop",
}
P0_GAPS = EXPECTED_GAPS - P1_GAPS

REQUIRED_BLUEPRINTS = {
    "cognitive_runtime_blueprint": "gap-cognitive-execution-loop",
    "conversation_runtime_contract": "gap-conversation-state-authority",
    "tool_runtime_blueprint": "gap-tool-runtime-convergence",
    "context_compiler_blueprint": "gap-context-compiler-convergence",
    "verification_runtime_blueprint": "gap-verification-evidence-contract",
    "provider_interaction_protocol": "gap-provider-interaction-protocol",
    "engine_application_boundary_blueprint": "gap-engine-application-execution-boundary",
    "realtime_delivery_blueprint": "gap-streaming-protocol",
    "golden_journey_blueprint": "gap-e2e-golden-journeys",
    "memory_runtime_blueprint": "gap-memory-durable-authority",
    "state_authority_blueprint": "gap-state-authority-convergence",
    "governance_runtime_blueprint": "gap-governance-registry",
    "cost_admission_blueprint": "gap-cost-admission",
    "provider_surface_convergence_blueprint": "gap-provider-surface-convergence",
    "provider_redundancy_blueprint": "gap-provider-redundancy",
}

TERMINAL_BLUEPRINT_STATUSES = {"closed", "complete"}


class VerificationError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError(f"cannot read {path}") from exc
    if not isinstance(value, dict):
        raise VerificationError(f"{path} must contain an object")
    return value


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def verify_repository(root: Path = ROOT) -> dict[str, Any]:
    errors: list[str] = []

    construction = _load(root / "machine/ai_app_construction.json")
    handoff = _load(root / "machine/ai_implementation_handoff.json")
    closure = _load(root / "machine/ai_closure_evidence.json")

    gaps = construction.get("gap_register")
    if not isinstance(gaps, list):
        raise VerificationError("gap_register must be a list")

    gap_rows = {
        str(item.get("id")): item
        for item in gaps
        if isinstance(item, dict) and item.get("id")
    }
    actual = set(gap_rows)
    if actual != EXPECTED_GAPS:
        errors.append(
            "canonical gap inventory mismatch: missing="
            + ",".join(sorted(EXPECTED_GAPS - actual))
            + " unexpected="
            + ",".join(sorted(actual - EXPECTED_GAPS))
        )

    open_gaps = sorted(
        gap_id
        for gap_id, item in gap_rows.items()
        if item.get("status") != "closed"
    )
    if open_gaps:
        errors.append("open masterplan gaps remain: " + ", ".join(open_gaps))

    for gap_id, item in sorted(gap_rows.items()):
        outstanding = item.get("outstanding_evidence")
        if isinstance(outstanding, list) and outstanding:
            errors.append(f"{gap_id} still has outstanding construction evidence")

        if item.get("status") == "closed":
            verification_state = item.get("verification_state")
            if (
                verification_state is not None
                and verification_state != "closed"
            ):
                errors.append(
                    f"{gap_id} is closed but verification_state is "
                    f"{verification_state!r}"
                )

            progress = item.get("progress")
            if isinstance(progress, dict):
                progress_state = progress.get("state")
                if progress_state is not None and progress_state != "closed":
                    errors.append(
                        f"{gap_id} is closed but progress.state is "
                        f"{progress_state!r}"
                    )
                remaining = progress.get("remaining")
                if isinstance(remaining, list) and remaining:
                    errors.append(
                        f"{gap_id} is closed but progress.remaining is non-empty"
                    )

    handoff_entries = handoff.get("entries")
    if not isinstance(handoff_entries, list):
        errors.append("implementation handoff entries must be a list")
        handoff_entries = []
    handoff_by_gap = {
        str(item.get("gap")): item
        for item in handoff_entries
        if isinstance(item, dict) and item.get("gap")
    }
    missing_handoffs = sorted(P0_GAPS - set(handoff_by_gap))
    if missing_handoffs:
        errors.append(
            "P0 implementation handoffs missing: " + ", ".join(missing_handoffs)
        )
    for gap_id, entry in sorted(handoff_by_gap.items()):
        if gap_id not in EXPECTED_GAPS:
            continue
        if entry.get("implementation_status") != "closed":
            errors.append(f"{gap_id} handoff is not closed")
        remaining = entry.get("remaining")
        if isinstance(remaining, list) and remaining:
            errors.append(f"{gap_id} handoff still has remaining work")
        blockers = entry.get("blockers")
        if isinstance(blockers, list) and blockers:
            errors.append(f"{gap_id} handoff still has blockers")

    closure_entries = closure.get("entries")
    if not isinstance(closure_entries, list):
        errors.append("closure evidence entries must be a list")
        closure_entries = []
    closure_by_gap = {
        str(item.get("gap")): item
        for item in closure_entries
        if isinstance(item, dict) and item.get("gap")
    }
    missing_closure = sorted(P0_GAPS - set(closure_by_gap))
    if missing_closure:
        errors.append(
            "P0 closure evidence records missing: " + ", ".join(missing_closure)
        )
    for gap_id, entry in sorted(closure_by_gap.items()):
        if gap_id not in EXPECTED_GAPS:
            continue
        if entry.get("gap_status") != "closed":
            errors.append(f"{gap_id} closure gap_status is not closed")
        if entry.get("implementation_state") != "complete":
            errors.append(f"{gap_id} implementation_state is not complete")
        if entry.get("closure_decision") != "closed":
            errors.append(f"{gap_id} closure_decision is not closed")
        for field in ("outstanding_evidence", "blockers"):
            value = entry.get(field)
            if isinstance(value, list) and value:
                errors.append(f"{gap_id} closure still has {field}")

    blueprint_rows: dict[str, dict[str, Any]] = {}
    for name, expected_gap in REQUIRED_BLUEPRINTS.items():
        value = construction.get(name)
        if not isinstance(value, dict):
            errors.append(f"required blueprint is missing: {name}")
            continue
        blueprint_rows[name] = value
        if value.get("gap") != expected_gap:
            errors.append(
                f"{name} gap binding drift: expected {expected_gap}, "
                f"got {value.get('gap')!r}"
            )
        if value.get("status") not in TERMINAL_BLUEPRINT_STATUSES:
            errors.append(
                f"{name} for {expected_gap} has non-terminal status "
                f"{value.get('status')!r}"
            )

    priority_counts: dict[str, int] = {}
    for item in gap_rows.values():
        key = str(item.get("priority") or "unknown")
        priority_counts[key] = priority_counts.get(key, 0) + 1

    return {
        "schema_version": 1,
        "verifier": "independent-masterplan-completion-v1",
        "head_sha": os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
        or os.environ.get("GITHUB_SHA", "").strip()
        or "unknown",
        "expected_gap_count": len(EXPECTED_GAPS),
        "actual_gap_count": len(gap_rows),
        "open_gaps": open_gaps,
        "priority_counts": priority_counts,
        "handoff_gap_count": len(
            set(handoff_by_gap).intersection(EXPECTED_GAPS)
        ),
        "closure_gap_count": len(
            set(closure_by_gap).intersection(EXPECTED_GAPS)
        ),
        "blueprint_count": len(blueprint_rows),
        "construction_digest": _digest(construction),
        "handoff_digest": _digest(handoff),
        "closure_digest": _digest(closure),
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
        print(f"masterplan-completion: rejected: {exc}", file=sys.stderr)
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
        print("masterplan-completion: rejected", file=sys.stderr)
        for error in receipt["errors"]:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(
        "masterplan-completion: OK "
        f"(gaps={receipt['actual_gap_count']}, "
        f"blueprints={receipt['blueprint_count']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
