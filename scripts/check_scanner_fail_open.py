#!/usr/bin/env python3
"""Fail-closed inventory of scanner fail-open behaviors (#960 S016).

Classifies fixture JSON observations for zero-file success, partial
traversal, unreadable subtree, nested symlink, malformed source, and
timeout fail-open. Closed classes: ``fail_closed``, ``fail_open``,
``unknown``. Unknown and fail_open fail the gate.

This module classifies fixture JSON only. It does not open, rewrite, or
weaken live scanners. Distinct from S019 capability inventory, S020
security-priority ranking, and S029 scan-performance shapes.
Finding prefix: ``scanner-fail-open``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Mapping, Sequence


SCHEMA_VERSION = 1
TASK_ID = "reserve-S016-scanner-fail-open"
CONFLICT_DOMAIN = "security.readonly.scanner_fail_open"
FINDING_PREFIX = "scanner-fail-open"
CLASSES: tuple[str, ...] = ("fail_closed", "fail_open", "unknown")
CLASS_SET = frozenset(CLASSES)
SCENARIOS: tuple[str, ...] = (
    "zero_file_success",
    "partial_traversal",
    "unreadable_subtree",
    "nested_symlink",
    "malformed_source",
    "timeout_fail_open",
)
SCENARIO_SET = frozenset(SCENARIOS)
SYMLINK_POLICIES: tuple[str, ...] = ("none", "error", "skip", "follow")
SYMLINK_POLICY_SET = frozenset(SYMLINK_POLICIES)
DOCUMENT_FIELDS = frozenset({"schema_version", "observations"})
OBSERVATION_FIELDS = frozenset(
    {
        "scanner",
        "scenario",
        "exit_code",
        "files_expected",
        "files_scanned",
        "timed_out",
        "unreadable_subtree",
        "nested_symlink",
        "symlink_policy",
        "malformed_source",
    }
)
GATE_FAIL_CLASSES = frozenset({"fail_open", "unknown"})


def _error(code: str, message: str) -> str:
    return f"{FINDING_PREFIX} {code}: {message}"


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_bool(value: object) -> bool:
    return isinstance(value, bool)


def _scenario_condition_holds(observation: Mapping[str, object], scenario: str) -> bool:
    files_expected = observation["files_expected"]
    files_scanned = observation["files_scanned"]
    assert _is_int(files_expected) and _is_int(files_scanned)
    if scenario == "zero_file_success":
        return files_scanned == 0
    if scenario == "partial_traversal":
        return files_scanned < files_expected
    if scenario == "unreadable_subtree":
        return observation["unreadable_subtree"] is True
    if scenario == "nested_symlink":
        return observation["nested_symlink"] is True
    if scenario == "malformed_source":
        return observation["malformed_source"] is True
    if scenario == "timeout_fail_open":
        return observation["timed_out"] is True
    return False


def classify_observation(observation: object) -> str:
    """Return exactly one closed class. Incomplete evidence is unknown."""

    if not isinstance(observation, Mapping):
        return "unknown"
    unknown_fields = set(observation) - OBSERVATION_FIELDS
    if unknown_fields:
        return "unknown"
    missing = OBSERVATION_FIELDS - set(observation)
    if missing:
        return "unknown"

    scanner = observation.get("scanner")
    if not isinstance(scanner, str) or not scanner.strip():
        return "unknown"

    scenario = observation.get("scenario")
    if not isinstance(scenario, str) or scenario not in SCENARIO_SET:
        return "unknown"

    exit_code = observation.get("exit_code")
    if not _is_int(exit_code):
        return "unknown"

    files_expected = observation.get("files_expected")
    files_scanned = observation.get("files_scanned")
    if not _is_int(files_expected) or files_expected < 0:
        return "unknown"
    if not _is_int(files_scanned) or files_scanned < 0:
        return "unknown"
    if files_scanned > files_expected:
        return "unknown"

    for flag in ("timed_out", "unreadable_subtree", "nested_symlink", "malformed_source"):
        if not _is_bool(observation.get(flag)):
            return "unknown"

    policy = observation.get("symlink_policy")
    if not isinstance(policy, str) or policy not in SYMLINK_POLICY_SET:
        return "unknown"
    nested = observation.get("nested_symlink")
    if nested is True and policy == "none":
        return "unknown"
    if nested is False and policy != "none":
        return "unknown"

    if not _scenario_condition_holds(observation, scenario):
        return "unknown"

    if exit_code == 0:
        return "fail_open"
    return "fail_closed"


def classify_document(document: object) -> tuple[list[dict[str, object]], list[str]]:
    """Classify every observation. Unknown and fail_open become gate errors."""

    errors: list[str] = []
    if not isinstance(document, Mapping):
        return [], [_error("unknown root_type", "document must be an object")]

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
    if not _is_int(version) or version != SCHEMA_VERSION:
        errors.append(
            _error(
                "unknown schema_version",
                f"schema_version must be exactly {SCHEMA_VERSION}",
            )
        )

    observations = document.get("observations")
    if not isinstance(observations, list):
        errors.append(_error("unknown observations_type", "observations must be a list"))
        return [], errors
    if not observations:
        errors.append(
            _error(
                "unknown empty_observations",
                "observations must be a non-empty list; zero-file inventory success is forbidden",
            )
        )
        return [], errors

    rows: list[dict[str, object]] = []
    for index, observation in enumerate(observations):
        klass = classify_observation(observation)
        scanner = observation.get("scanner") if isinstance(observation, Mapping) else index
        scenario = observation.get("scenario") if isinstance(observation, Mapping) else None
        rows.append(
            {
                "index": index,
                "scanner": scanner,
                "scenario": scenario,
                "class": klass,
            }
        )
        if klass in GATE_FAIL_CLASSES:
            errors.append(
                _error(
                    klass,
                    f"observations[{index}] scanner={scanner!r} scenario={scenario!r}",
                )
            )
    return rows, errors


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
    parser.add_argument(
        "path",
        type=Path,
        help="JSON fixture of scanner fail-open observations",
    )
    args = parser.parse_args(argv)
    rows, errors = classify_document(load_document(args.path))
    counts = {name: 0 for name in CLASSES}
    for row in rows:
        counts[str(row["class"])] += 1
    print(
        "Scanner fail-open inventory: "
        + ", ".join(f"{name}={counts[name]}" for name in CLASSES)
    )
    if errors:
        print("Scanner fail-open inventory failed:", file=sys.stderr)
        for item in errors:
            print(f"  {item}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
