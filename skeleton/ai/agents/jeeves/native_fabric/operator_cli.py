"""Offline source-only Jeeves operator audit, with no model activation.

This command can audit exact-head workflow evidence, preflight a bounded
device reading, or reconcile an installer vs live model record. It does
not fetch GitHub itself, read arbitrary private paths, acquire credentials,
start native inference or claim hardware testing. Caller data remains
untrusted until strictly validated.
"""
from __future__ import annotations

import argparse
from dataclasses import fields
import json
import sys
from typing import Mapping, TypeVar, Type

from .contracts import (
    ContractHold, bounded_mapping, canonical_bytes, parse_json,
)
from .assurance import Gate, summarize_exact_head, REQUIRED_EXACT_HEAD
from .device import DeviceSnapshot, DevicePolicy, evaluate_device, safe_observation
from .model_inventory import ModelIdentity, reconcile_installed_model
from .health import HealthSignal, assess_health


class OperatorAuditHold(ContractHold):
    pass


def _typed(cls, record: object):
    if type(record) is not dict:
        raise OperatorAuditHold("typed object required")
    permitted = {f.name for f in fields(cls)}
    if not set(record) <= permitted:
        raise OperatorAuditHold("unknown operator audit fields")
    try:
        return cls(**record)
    except (ValueError, TypeError, OverflowError) as exc:
        raise OperatorAuditHold("invalid typed audit record") from exc


def audit_gate_report(input_: object) -> dict[str, object]:
    data = bounded_mapping(
        input_,
        fields={"head_sha", "required", "gates"},
        required={"head_sha", "gates"},
    )
    gates = data["gates"]
    if type(gates) is not list or len(gates) > 10000:
        raise OperatorAuditHold("unbounded workflow evidence")
    required = data.get("required", list(REQUIRED_EXACT_HEAD))
    if type(required) is not list:
        raise OperatorAuditHold("explicit required gate list")
    result = summarize_exact_head(
        data["head_sha"], tuple(_typed(Gate, x) for x in gates),
        required=tuple(required),
    )
    return result.to_record()


def audit_device_report(input_: object) -> dict[str, object]:
    data = bounded_mapping(
        input_,
        fields={"snapshot", "policy", "observed_at_ns"},
        required={"snapshot", "observed_at_ns"},
    )
    snapshot = _typed(DeviceSnapshot, data["snapshot"])
    policy = _typed(DevicePolicy, data.get("policy", {}))
    return evaluate_device(
        snapshot, policy, observed_at_ns=data["observed_at_ns"],
    )


def audit_model_report(input_: object) -> dict[str, object]:
    data = bounded_mapping(
        input_,
        fields={"installed", "active", "requested_context", "requested_output"},
        required={"installed", "requested_context", "requested_output"},
    )
    installed = _typed(ModelIdentity, data["installed"])
    active = (None if data.get("active") is None
              else _typed(ModelIdentity, data["active"]))
    return reconcile_installed_model(
        installed, active,
        requested_context=data["requested_context"],
        requested_output=data["requested_output"],
    )


def audit_telemetry_report(input_: object) -> dict[str, object]:
    data = bounded_mapping(
        input_,
        fields={"expected", "signals", "max_age_ms"},
        required={"expected", "signals"},
    )
    signals = data["signals"]
    expected = data["expected"]
    if type(signals) is not list or type(expected) is not list:
        raise OperatorAuditHold("bounded telemetry arrays required")
    assessment = assess_health(
        tuple(_typed(HealthSignal, item) for item in signals),
        expected_ids=tuple(expected),
        maximum_age_ms=data.get("max_age_ms", 15000),
    )
    return assessment.to_record()


_PROCESSORS = {
    "gates": audit_gate_report,
    "device": audit_device_report,
    "model": audit_model_report,
    "telemetry": audit_telemetry_report,
}


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline native Jeeves operational evidence auditing"
    )
    parser.add_argument(
        "--mode", required=True,
        choices=(*_PROCESSORS, "observe"),
    )
    parser.add_argument(
        "--json-stdin", action="store_true",
        help="Read a bounded UTF-8 JSON audit record via stdin",
    )
    args = parser.parse_args(argv)
    try:
        if args.mode == "observe":
            if args.json_stdin:
                raise OperatorAuditHold("portable observation does not take custom input")
            record = safe_observation().to_record()
        else:
            if not args.json_stdin:
                raise OperatorAuditHold("explicit bounded operator JSON stdin required")
            raw = sys.stdin.buffer.read(262145)
            data = parse_json(raw, max_bytes=262144)
            record = _PROCESSORS[args.mode](data)
        canonical_bytes(record, max_bytes=262144)
        sys.stdout.write(json.dumps(
            record, sort_keys=True, ensure_ascii=False,
            allow_nan=False, separators=(",", ":"),
        ) + "\n")
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        # Neither untrusted source bytes, operator prompts, private paths,
        # claims, nor model identity manifests are echoed on a failure.
        sys.stderr.write(json.dumps({
            "schema": "jeeves.fabric.operator_audit_error.v1",
            "status": "held",
            "error_class": type(exc).__name__,
            "real_native_execution_qualified": False,
            "release_certified": False,
        }, sort_keys=True) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(run())


__all__ = ["OperatorAuditHold", "audit_gate_report",
           "audit_device_report", "audit_model_report",
           "audit_telemetry_report", "run"]
