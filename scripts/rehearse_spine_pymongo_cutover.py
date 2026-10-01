#!/usr/bin/env python3
"""Bind live PyMongo qualification to a non-activating cutover rehearsal."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from skeleton.frontier.operation_stream_store import SQLiteOperationEventStore
from skeleton.persistence.consistency_fence import SQLiteConsistencyFence
from skeleton.persistence.mongo_fence import MongoConsistencyFence
from skeleton.persistence.operation_runtime import DurableOperationRuntime
from skeleton.persistence.operation_store import SQLiteOperationStore
from skeleton.persistence.spine_apply import SpineApplyGate
from skeleton.persistence.spine_cutover import SpineCutover
from skeleton.persistence.spine_cutover_rehearsal import SpineCutoverRehearsal
from skeleton.persistence.spine_cutover_rehearsal_verify import (
    SpineCutoverRehearsalVerify,
)
from skeleton.persistence.spine_dispatch_guard import SpineDispatchGuard
from skeleton.persistence.spine_drift import SpineDrift
from skeleton.persistence.spine_lag import SpineLag
from skeleton.persistence.spine_runtime_selection import SpineRuntimeSelection
from skeleton.persistence.spine_runtime_selection_verify import (
    SpineRuntimeSelectionVerify,
)


class _Reasoner:
    def reason(self, **kwargs: Any) -> dict[str, Any]:
        return {"answer": "cutover-rehearsal", "confidence": 1.0}


def rehearse(qualification: dict[str, Any]) -> dict[str, Any]:
    operations = SQLiteOperationStore(":memory:")
    stream = SQLiteOperationEventStore(":memory:")
    runtime = DurableOperationRuntime(_Reasoner(), operations, stream)
    sqlite_fence = SQLiteConsistencyFence(":memory:")
    mongo_fence = MongoConsistencyFence()

    try:
        guard = SpineDispatchGuard()
        before = guard.snapshot(runtime)
        dispatcher = guard.compare(before, runtime)

        candidate = SpineRuntimeSelection().candidate(
            qualification=qualification,
            dispatch_guard=dispatcher,
        )
        candidate_verified = SpineRuntimeSelectionVerify().verify(candidate)

        cutover = SpineCutover(
            SpineLag(operations),
            SpineDrift(sqlite_fence, mongo_fence),
            SpineApplyGate(),
        ).card(
            tenant_id="p2-cutover-rehearsal",
            operation_id="p2-cutover-rehearsal",
        )

        rehearsal = SpineCutoverRehearsal().rehearse(
            candidate=candidate,
            selection_verify=candidate_verified,
            cutover=cutover,
            chain={"match": True},
        )
        rehearsal_verified = SpineCutoverRehearsalVerify().verify(rehearsal)

        if runtime.dispatcher_running:
            raise RuntimeError("runtime dispatcher started during cutover rehearsal")

        return {
            "schema_version": 1,
            "kind": "spine_pymongo_async_cutover_rehearsal",
            "law": "live-qualification-does-not-authorize-runtime-cutover",
            "qualification_digest": qualification["digest"],
            "candidate_digest": candidate["digest"],
            "rehearsal_digest": rehearsal["digest"],
            "driver_distribution": qualification["driver_distribution"],
            "driver_version": qualification["driver_version"],
            "candidate_verified": candidate_verified["verified"],
            "rehearsal_verified": rehearsal_verified["verified"],
            "cutover_preconditions_green": rehearsal["preconditions_green"],
            "switch_refused": rehearsal["switch_refused"],
            "switch_reason": rehearsal["switch_reason"],
            "dispatcher_identity_stable": dispatcher["same"],
            "dispatcher_running": runtime.dispatcher_running,
            "runtime_driver_selected": False,
            "selection_authorized": False,
            "runtime_activated": False,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
    finally:
        sqlite_fence.close()
        runtime.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qualification", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        qualification = json.loads(args.qualification.read_text(encoding="utf-8"))
        report = rehearse(qualification)
    except Exception as exc:
        print(json.dumps({"verified": False, "error": str(exc)}, sort_keys=True))
        return 2

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
