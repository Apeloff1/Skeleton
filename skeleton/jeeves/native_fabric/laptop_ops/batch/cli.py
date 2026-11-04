"""Operator-only whole-stack source diagnostics and read-only laptop probes.

A successful observation does not start GGUF, approve weights, change
installer state, grant tools or certify the physical device. Every model
and local state path is excluded from public stdout and stderr.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from skeleton.jeeves.native_fabric.laptop_ops.contracts import (
    LaptopGateHold, canonical,
)
from skeleton.jeeves.native_fabric.laptop_ops.redaction import diagnostic
from skeleton.jeeves.native_fabric.laptop_ops.host_probes.summary import (
    observe_host,
)
from .catalog import manifest
from .limits import DEFAULT_BUNDLE_LIMITS
from .runner import evaluate_json


class _RedactedArguments(argparse.ArgumentParser):
    """Never echo secret task arguments in malformed flag diagnostics."""

    def error(self, message: str) -> None:
        raise LaptopGateHold("invalid bounded laptop diagnostic arguments")


def main(argv: list[str] | None = None) -> int:
    parser = _RedactedArguments(
        description="Read-only Jeeves native first-laptop source and host probes"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--json-stdin", action="store_true")
    mode.add_argument("--catalog", action="store_true")
    mode.add_argument("--host-observe", action="store_true")
    parser.add_argument("--model-file", type=Path)
    parser.add_argument("--state-directory", type=Path)
    parser.add_argument("--threads", type=int)
    parser.add_argument("--memory-reservation-bytes", type=int)
    parser.add_argument("--storage-reservation-bytes", type=int)
    try:
        args = parser.parse_args(argv)
        host_fields = (
            args.model_file,
            args.state_directory,
            args.threads,
            args.memory_reservation_bytes,
            args.storage_reservation_bytes,
        )
        if args.host_observe:
            if any(field is None for field in host_fields):
                raise LaptopGateHold("explicit native host observation scope required")
            snapshot = observe_host(
                model_file=args.model_file,
                state_directory=args.state_directory,
                threads=args.threads,
                reserved_memory_bytes=args.memory_reservation_bytes,
                reserved_storage_bytes=args.storage_reservation_bytes,
            )
            report = snapshot.to_record()
            accepted = report["structural_preconditions_observed"]
        else:
            if any(field is not None for field in host_fields):
                raise LaptopGateHold("host paths and budgets require host observation mode")
            if args.catalog:
                report = manifest()
                accepted = True
            else:
                raw = sys.stdin.buffer.read(
                    DEFAULT_BUNDLE_LIMITS.max_evidence_bytes + 1
                )
                report = evaluate_json(raw).to_record()
                accepted = report["accepted_source_only"]
        output = DEFAULT_BUNDLE_LIMITS.require_report(
            canonical(report, maximum=DEFAULT_BUNDLE_LIMITS.max_report_bytes)
        )
        sys.stdout.buffer.write(output + b"\n")
        return 0 if accepted else 2
    except (Exception, KeyboardInterrupt) as exc:
        # No model bytes, private paths, operator task, or exception text.
        sys.stderr.write(json.dumps(
            diagnostic(type(exc).__name__), sort_keys=True
        ) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
