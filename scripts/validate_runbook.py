#!/usr/bin/env python3
"""Validate a versioned operations runbook and optional drill receipts."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path

from skeleton.observability.runbooks import (
    Runbook,
    RunbookRegistry,
    RunbookStep,
    RunbookValidation,
    StepKind,
    ValidationStatus,
)


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def build_runbook(spec: dict) -> Runbook:
    steps = tuple(
        RunbookStep(
            step_id=item["step_id"],
            kind=StepKind(item["kind"]),
            instruction=item["instruction"],
            signal_ref=item.get("signal_ref"),
            command_ref=item.get("command_ref"),
            authority_ref=item.get("authority_ref"),
            rollback_step_id=item.get("rollback_step_id"),
            condition_ref=item.get("condition_ref"),
            next_step_ids=tuple(item.get("next_step_ids", ())),
        )
        for item in spec["steps"]
    )
    return Runbook(
        runbook_id=spec["runbook_id"],
        version=spec["version"],
        owner=spec["owner"],
        degraded_mode=spec["degraded_mode"],
        entry_step_id=spec["entry_step_id"],
        steps=steps,
    )


def build_validation(spec: dict) -> RunbookValidation:
    return RunbookValidation(
        validation_id=spec["validation_id"],
        runbook_id=spec["runbook_id"],
        runbook_version=spec["runbook_version"],
        runbook_digest=spec["runbook_digest"],
        drill_id=spec["drill_id"],
        validator_id=spec["validator_id"],
        status=ValidationStatus(spec["status"]),
        evidence_digest=spec["evidence_digest"],
        observed_at=_time(spec["observed_at"]),
        incident_ref=spec.get("incident_ref"),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("runbook", type=Path)
    parser.add_argument("--validation", type=Path, action="append", default=[])
    parser.add_argument("--require-passed-drill", action="store_true")
    args = parser.parse_args()

    runbook = build_runbook(
        json.loads(args.runbook.read_text(encoding="utf-8"))
    )
    registry = RunbookRegistry()
    registry.register(runbook)

    for path in args.validation:
        registry.record_validation(
            build_validation(json.loads(path.read_text(encoding="utf-8")))
        )

    validated = registry.validated(runbook.runbook_id, runbook.version)
    if args.require_passed_drill and not validated:
        raise SystemExit("exact runbook version lacks a passed drill")

    result = {
        "schema_version": 1,
        "runbook_id": runbook.runbook_id,
        "version": runbook.version,
        "runbook_digest": runbook.digest,
        "registry_digest": registry.digest,
        "validated": validated,
        "validation_digests": [
            item.digest
            for item in registry.validations_for(
                runbook.runbook_id,
                runbook.version,
            )
        ],
    }
    print(json.dumps(result, sort_keys=True, indent=2) + "\n", end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
