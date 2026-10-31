"""Offline operator CLI for bounded, fair local inference stream planning.

No prompt bytes, model weights, filesystem paths or provider credentials are
read from the command payload. The command emits admission *plans* only.
"""
from __future__ import annotations

import argparse
import json
import sys

from .fair_stream_queue import (
    FairStreamScheduler, MeasuredStreamBudget, StreamRequest,
)
from .iteration_scheduler import InferencePhase


INPUT_SCHEMA = "skeleton.ai.fair-stream-command.v1"
OUTPUT_SCHEMA = "skeleton.ai.fair-stream-command-receipt.v1"
MAX_INPUT_BYTES = 262_144


def _request(raw: object) -> StreamRequest:
    if type(raw) is not dict or set(raw) != {
        "request_id", "tenant_id", "phase", "remaining_tokens",
        "bytes_per_token", "priority",
    }:
        raise ValueError("invalid stream request fields")
    try:
        phase = InferencePhase(raw["phase"])
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid stream phase") from exc
    return StreamRequest(
        raw["request_id"], raw["tenant_id"], phase,
        raw["remaining_tokens"], raw["bytes_per_token"], raw["priority"],
    )


def _operator_budget(raw: object) -> MeasuredStreamBudget:
    if type(raw) is not dict or set(raw) != {
        "available_ram_bytes", "reserved_ram_bytes", "token_budget",
        "stream_slots", "pressure_ppm", "thermal_hold", "measurement",
    }:
        raise ValueError("invalid explicit budget fields")
    if raw["measurement"] == "os_probe":
        raise ValueError("operator payload cannot claim OS-measured provenance")
    return MeasuredStreamBudget(**raw)


# Retain pressure hysteresis across requests within the CLI process.
_LIVE_SAMPLER = None


def _live_budget(token_budget: int, storage_path: str):
    global _LIVE_SAMPLER
    from .fair_stream_live_budget import LiveStreamBudgetSampler
    if _LIVE_SAMPLER is None:
        _LIVE_SAMPLER = LiveStreamBudgetSampler()
    return _LIVE_SAMPLER.sample(token_budget=token_budget, storage_path=storage_path)


def _command(raw: object, *, live: bool, storage_path: str) -> dict[str, object]:
    if type(raw) is not dict or set(raw) != {
        "schema", "requests", "checkpoint", "acknowledgments",
        "cancellations", "envelope", "token_budget",
    }:
        raise ValueError("invalid fair-stream command fields")
    if raw["schema"] != INPUT_SCHEMA:
        raise ValueError("unsupported fair-stream command schema")
    requests = raw["requests"]
    acks = raw["acknowledgments"]
    cancellations = raw["cancellations"]
    if (type(requests) is not list or len(requests) > 4096
            or type(acks) is not list or len(acks) > 64
            or type(cancellations) is not list or len(cancellations) > 4096):
        raise ValueError("unbounded fair-stream command")
    checkpoint = raw["checkpoint"]
    if checkpoint is None:
        scheduler = FairStreamScheduler()
    else:
        scheduler = FairStreamScheduler.restore(checkpoint)
    # Recover uncertain leases before admitting any new work. The caller
    # supplies authoritative execution receipts; a hash alone is not proof.
    for ack in acks:
        if type(ack) is not dict or set(ack) != {"lease_id", "consumed_tokens"}:
            raise ValueError("invalid execution acknowledgment")
        scheduler.acknowledge(ack["lease_id"], consumed_tokens=ack["consumed_tokens"])
    for request_id in cancellations:
        scheduler.cancel(request_id)
    for item in requests:
        scheduler.submit(_request(item))
    if live:
        if raw["envelope"] is not None:
            raise ValueError("live probe cannot be combined with operator envelope")
        budget, live_evidence = _live_budget(raw["token_budget"], storage_path)
        thermal_measured = bool(live_evidence["thermal_trip_measured"])
    else:
        if raw["token_budget"] is not None:
            raise ValueError("operator mode requires token_budget inside envelope")
        budget = _operator_budget(raw["envelope"])
        thermal_measured = False
        live_evidence = None
    plan = scheduler.plan(budget)
    return {
        "schema": OUTPUT_SCHEMA,
        "measurement": budget.measurement,
        "thermal_trip_measured": thermal_measured,
        "live_evidence": live_evidence,
        "budget": {
            "available_ram_bytes": budget.available_ram_bytes,
            "reserved_ram_bytes": budget.reserved_ram_bytes,
            "token_budget": budget.token_budget,
            "stream_slots": budget.stream_slots,
            "pressure_ppm": budget.pressure_ppm,
            "thermal_hold": budget.thermal_hold,
            "effective_tokens": budget.effective_tokens,
            "effective_slots": budget.effective_slots,
        },
        "plan": {
            "schema": "skeleton.ai.fair-stream-plan.v1",
            "leases": [
                FairStreamScheduler._lease_dict(lease) for lease in plan.leases
            ],
            "deferred": list(plan.deferred),
            "available_tokens": plan.available_tokens,
            "available_ram_bytes": plan.available_ram_bytes,
            "checkpoint_digest": plan.checkpoint_digest,
            "digest": plan.digest,
        },
        "checkpoint": scheduler.checkpoint(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Plan bounded offline model token streams without executing a model"
    )
    parser.add_argument("--live", action="store_true", help="use current canonical OS resource probes")
    parser.add_argument("--storage-path", default=".", help="volume used for live resource probe")
    args = parser.parse_args(argv)
    try:
        payload = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(payload) > MAX_INPUT_BYTES:
            raise ValueError("fair-stream command exceeds input byte budget")
        raw = json.loads(payload.decode("utf-8", errors="strict"))
        receipt = _command(raw, live=args.live, storage_path=args.storage_path)
        print(json.dumps(receipt, sort_keys=True, separators=(",", ":"), allow_nan=False))
        return 0
    except (ValueError, TypeError, UnicodeError, OSError) as exc:
        print("fair-stream admission denied: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
