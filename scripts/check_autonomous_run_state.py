#!/usr/bin/env python3
"""Versioned fail-closed Supervisor autonomous-run state machine (#967 S451).

Closed states: scheduled, queued, running, blocked, failed-closed,
validated, published, no-op. Illegal transitions, unknown states, and
extra fields fail closed.

This is the Supervisor *autonomous-run lifecycle*, not GitHub Actions
run-state classification (S002 / ``reserve-S002-run-state-classification``).
Finding prefix: ``autonomous-run-state``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Mapping, Sequence


SCHEMA_VERSION = 1
TASK_ID = "reserve-S451-autonomous-run-state"
CONFLICT_DOMAIN = "ops.spec.autonomous_run_state"
_FINDING_PREFIX = "autonomous-run-state"

STATES: tuple[str, ...] = (
    "scheduled",
    "queued",
    "running",
    "blocked",
    "failed-closed",
    "validated",
    "published",
    "no-op",
)
STATE_SET = frozenset(STATES)
INITIAL_STATE = "scheduled"
TERMINAL_STATES = frozenset({"failed-closed", "published", "no-op"})
LEGAL_TRANSITIONS: frozenset[tuple[str, str]] = frozenset(
    {
        ("scheduled", "queued"),
        ("scheduled", "blocked"),
        ("scheduled", "no-op"),
        ("scheduled", "failed-closed"),
        ("queued", "running"),
        ("queued", "blocked"),
        ("queued", "no-op"),
        ("queued", "failed-closed"),
        ("running", "blocked"),
        ("running", "validated"),
        ("running", "failed-closed"),
        ("running", "no-op"),
        ("blocked", "queued"),
        ("blocked", "running"),
        ("blocked", "failed-closed"),
        ("blocked", "no-op"),
        ("validated", "published"),
        ("validated", "failed-closed"),
    }
)
DOCUMENT_FIELDS = frozenset(
    {
        "schema_version",
        "run_id",
        "state",
        "history",
        "evidence_refs",
    }
)
TRANSITION_FIELDS = frozenset({"from", "to"})

# GitHub Actions classifier classes (S002). Not valid autonomous-run states.
ACTIONS_RUN_CLASSES = frozenset(
    {
        "retryable",
        "stale",
        "superseded",
        "authoritative_failure",
        "complete",
        "unknown",
    }
)


def _error(code: str, message: str) -> str:
    return f"{_FINDING_PREFIX} {code}: {message}"


def is_legal_transition(source: str, target: str) -> bool:
    """Return True only for an explicitly allowed closed-set edge."""

    return (source, target) in LEGAL_TRANSITIONS


def _check_evidence_refs(refs: object, errors: list[str], *, prefix: str = "evidence_refs") -> None:
    if not isinstance(refs, list) or not refs:
        errors.append(
            _error(
                "missing_value evidence_refs",
                f"{prefix} must be a non-empty list of non-empty strings",
            )
        )
        return
    for index, ref in enumerate(refs):
        if not isinstance(ref, str) or not ref.strip():
            errors.append(
                _error(
                    "unknown evidence_ref",
                    f"{prefix}[{index}] must be a non-empty string",
                )
            )


def _check_state_name(value: object, *, loc: str, errors: list[str]) -> str | None:
    if not isinstance(value, str) or not value.strip():
        errors.append(_error("unknown state", f"{loc} must be a non-empty closed-set state"))
        return None
    if value not in STATE_SET:
        errors.append(
            _error(
                "unknown state",
                f"{loc} has unknown state {value!r}; allowed: {', '.join(STATES)}",
            )
        )
        return None
    return value


def _check_transition(index: int, item: object, errors: list[str]) -> tuple[str, str] | None:
    loc = f"history[{index}]"
    if not isinstance(item, Mapping):
        errors.append(_error("unknown transition_type", f"{loc} must be an object"))
        return None
    extra = set(item) - TRANSITION_FIELDS
    if extra:
        errors.append(
            _error(
                "unknown field",
                f"{loc} has unknown fields: " + ", ".join(sorted(str(field) for field in extra)),
            )
        )
    missing = TRANSITION_FIELDS - set(item)
    if missing:
        errors.append(
            _error(
                "missing_value field",
                f"{loc} missing fields: " + ", ".join(sorted(missing)),
            )
        )
    source = _check_state_name(item.get("from"), loc=f"{loc}.from", errors=errors)
    target = _check_state_name(item.get("to"), loc=f"{loc}.to", errors=errors)
    if source is None or target is None:
        return None
    if not is_legal_transition(source, target):
        if source in TERMINAL_STATES:
            errors.append(
                _error(
                    "illegal transition",
                    f"{loc} {source} -> {target} leaves terminal state {source}",
                )
            )
        else:
            errors.append(
                _error(
                    "illegal transition",
                    f"{loc} {source} -> {target} is not allowed",
                )
            )
        return None
    return source, target


def validate_autonomous_run(document: object) -> list[str]:
    """Return fail-closed violations for one autonomous-run document."""

    errors: list[str] = []
    if not isinstance(document, Mapping):
        return [_error("unknown root_type", "autonomous-run document must be an object")]

    unknown = set(document) - DOCUMENT_FIELDS
    if unknown:
        errors.append(
            _error(
                "unknown field",
                "document has unknown fields: " + ", ".join(sorted(str(item) for item in unknown)),
            )
        )
    missing = DOCUMENT_FIELDS - set(document)
    if missing:
        errors.append(
            _error(
                "missing_value field",
                "document missing fields: " + ", ".join(sorted(missing)),
            )
        )

    version = document.get("schema_version")
    if not isinstance(version, int) or isinstance(version, bool) or version != SCHEMA_VERSION:
        errors.append(
            _error(
                "unknown schema_version",
                f"schema_version must be exactly {SCHEMA_VERSION}",
            )
        )

    run_id = document.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        errors.append(_error("missing_value run_id", "run_id must be a non-empty string"))

    current = None
    if "state" in document:
        current = _check_state_name(document.get("state"), loc="state", errors=errors)

    _check_evidence_refs(document.get("evidence_refs"), errors)

    history = document.get("history")
    if "history" not in document:
        return errors
    if not isinstance(history, list):
        errors.append(_error("unknown history_type", "history must be a list of transitions"))
        return errors

    parsed: list[tuple[str, str]] = []
    for index, item in enumerate(history):
        edge = _check_transition(index, item, errors)
        if edge is not None:
            parsed.append(edge)

    if len(parsed) != len(history):
        return errors

    if not parsed:
        if current is not None and current != INITIAL_STATE:
            errors.append(
                _error(
                    "illegal transition",
                    f"empty history is only valid when state is {INITIAL_STATE}, not {current}",
                )
            )
        return errors

    first_from = parsed[0][0]
    if first_from != INITIAL_STATE:
        errors.append(
            _error(
                "illegal transition",
                f"history[0].from must be {INITIAL_STATE}, not {first_from}",
            )
        )
    for index in range(1, len(parsed)):
        previous_to = parsed[index - 1][1]
        source = parsed[index][0]
        if source != previous_to:
            errors.append(
                _error(
                    "illegal transition",
                    f"history[{index}].from {source!r} does not continue from {previous_to!r}",
                )
            )
    last_to = parsed[-1][1]
    if current is not None and current != last_to:
        errors.append(
            _error(
                "illegal transition",
                f"state {current!r} does not match history[-1].to {last_to!r}",
            )
        )
    return errors


def load_document(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(_error("unreadable missing_doc", f"{path} is missing")) from exc
    except OSError as exc:
        raise SystemExit(
            _error("unreadable io_error", f"cannot read {path}: {type(exc).__name__}")
        ) from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(
            _error(
                "unreadable json",
                f"invalid JSON in {path} at line {exc.lineno}, column {exc.colno}",
            )
        ) from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="autonomous-run JSON document")
    args = parser.parse_args(argv)
    errors = validate_autonomous_run(load_document(args.path))
    if errors:
        print("Autonomous-run state schema validation failed:", file=sys.stderr)
        for item in errors:
            print(f"  {item}", file=sys.stderr)
        return 1
    print(f"Autonomous-run state schema v{SCHEMA_VERSION} accepted {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
