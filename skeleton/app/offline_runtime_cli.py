"""Installed local source admission and multi-sample iteration planner.

Commands read operator-pinned model identities and real local observations;
they do not start models, change power controls or authorize execution in
another process. All output is structured and excludes local source paths.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time
from typing import Any, BinaryIO, Sequence, TextIO

from skeleton.app.offline_runtime_preflight import (
    MIB, RuntimePolicy, canonical, inspect_source, plan_preflight, sample_hardware,
)
from skeleton.app.offline_runtime_control import RuntimeAdmission, parse_work
from skeleton.app.offline_energy_hysteresis import HysteresisPolicy

MAX_INPUT = 1024 * 1024


def _pairs(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("duplicate work field")
        result[name] = value
    return result


def _constant(_: str) -> None:
    raise ValueError("nonfinite JSON constant")


def read_work(stream: BinaryIO) -> tuple:
    raw = stream.read(MAX_INPUT + 1)
    if len(raw) > MAX_INPUT:
        raise ValueError("work document too large")
    return parse_work(json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                                 parse_constant=_constant))


def main(argv: Sequence[str] | None = None, *, stdin: BinaryIO | None = None,
         stdout: TextIO | None = None, stderr: TextIO | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline model source and measured resource admission")
    parser.add_argument("command", choices=("preflight", "iteration-plan"))
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--plan-sha", required=True)
    parser.add_argument("--model-identity-sha", required=True)
    parser.add_argument("--backend", choices=("cpu", "cuda", "hybrid"), default="cpu")
    parser.add_argument("--source-budget-mib", type=int, default=131072)
    parser.add_argument("--max-inventory-entries", type=int, default=64)
    parser.add_argument("--skip-gguf-framing", action="store_true",
                        help="Explicit opaque-weight inspection; no GGUF framing qualification")
    parser.add_argument("--max-workers", type=int, default=8)
    parser.add_argument("--worker-mib", type=int, default=256)
    parser.add_argument("--host-reserve-mib", type=int, default=1024)
    parser.add_argument("--device-reserve-mib", type=int, default=512)
    parser.add_argument("--interactive-cpu-reserve", type=int, default=1)
    parser.add_argument("--token-budget", type=int, default=2048)
    parser.add_argument("--prefill-quantum", type=int, default=512)
    parser.add_argument("--sample-age-ms", type=int, default=5000)
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--interval-ms", type=int, default=200)
    parser.add_argument("--require-candidate", action="store_true",
                        help="Return 3 if no candidate is available; no execution is attempted")
    args = parser.parse_args(argv)
    incoming = stdin if stdin is not None else sys.stdin.buffer
    outgoing = stdout if stdout is not None else sys.stdout
    errors = stderr if stderr is not None else sys.stderr
    try:
        if not 1 <= args.samples <= 16 or not 0 <= args.interval_ms <= 1000:
            raise ValueError("sampling limits exceeded")
        policy = RuntimePolicy(
            backend=args.backend, maximum_source_bytes=args.source_budget_mib * MIB,
            maximum_inventory_entries=args.max_inventory_entries,
            verify_gguf_headers=not args.skip_gguf_framing,
            maximum_workers=args.max_workers, bytes_per_worker=args.worker_mib * MIB,
            host_reserve_bytes=args.host_reserve_mib * MIB,
            device_reserve_bytes=args.device_reserve_mib * MIB,
            interactive_cpu_reserve=args.interactive_cpu_reserve,
            maximum_tokens=args.token_budget, prefill_quantum=args.prefill_quantum,
            sample_age_ns=args.sample_age_ms * 1_000_000,
        )
        # Validate work before expensive inspection; no request text is accepted.
        work = read_work(incoming) if args.command == "iteration-plan" else ()
        source = inspect_source(args.store, plan_digest=args.plan_sha,
                                model_identity_digest=args.model_identity_sha, policy=policy)
        if args.command == "preflight":
            result = plan_preflight(source, sample_hardware(), policy, now_ns=time.monotonic_ns())
            ready = result["status"] == "candidate"
        else:
            controller = RuntimeAdmission(source, policy, hysteresis_policy=HysteresisPolicy(
                max_sample_age_ns=policy.sample_age_ns))
            history = []
            latest = None
            try:
                for index in range(args.samples):
                    if index:
                        time.sleep(args.interval_ms / 1000)
                    latest = controller.offer(sample_hardware(), work, now_ns=time.monotonic_ns())
                    admission = latest["admission"]
                    history.append({"sequence": admission["sequence"], "status": admission["status"],
                                    "worker_ceiling": admission["worker_ceiling"],
                                    "scheduled_tokens": admission["scheduled_tokens"],
                                    "admission_digest": admission["admission_digest"],
                                    "blockers": admission["blockers"]})
                assert latest is not None
                ready = latest["admission"]["status"] == "candidate"
                result = {"schema": "skeleton.offline.iteration-observation.v1",
                          "latest": latest, "history": history, "policy": asdict(policy),
                          "transferable_grant": False, "model_activation": "not_performed",
                          "native_qualified": False, "release_qualified": False}
            finally:
                # A printed receipt must not be interpreted as a live grant.
                controller.revoke()
        outgoing.write(canonical(result).decode("ascii") + "\n")
        return 3 if args.require_candidate and not ready else 0
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError, OSError) as exc:
        errors.write("offline runtime admission rejected: " + type(exc).__name__ + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
