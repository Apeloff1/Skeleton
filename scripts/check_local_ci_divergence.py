#!/usr/bin/env python3
"""Fail-closed audit of local-vs-GitHub CI command divergence (#967 S442).

Issue #967 (``reserve-S442-local-ci-divergence``) classifies fixture-driven
pairs of ``{local_command, ci_command, documented}``. Each pair is exactly
one of:

* matching — tokenized local and CI commands are identical
* intentional_divergence — commands differ and ``documented`` is true
* undocumented_divergence — commands differ and ``documented`` is false
* unknown — invalid, unreadable, or untokenizable input (always a gate failure)

Undocumented divergence and unknown fail closed. This checker never rewrites
GitHub workflows, never executes the compared commands, and does not own
S026 hidden-network build classification or S101 developer-setup inventory.
"""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path


TASK_ID = "reserve-S442-local-ci-divergence"
CONFLICT_DOMAIN = "build.readonly.ci_parity"
FINDING_PREFIX = "local-ci-divergence"
INVENTORY_VERSION = 1
SCHEMA_VERSION = 1
EVIDENCE_KIND = "structural"
REWRITE_WORKFLOWS = False
MUTATION_ACTIONS: tuple[str, ...] = ()

CLASS_MATCHING = "matching"
CLASS_INTENTIONAL = "intentional_divergence"
CLASS_UNDOCUMENTED = "undocumented_divergence"
CLASS_UNKNOWN = "unknown"
CLASSES: tuple[str, ...] = (
    CLASS_MATCHING,
    CLASS_INTENTIONAL,
    CLASS_UNDOCUMENTED,
    CLASS_UNKNOWN,
)
CLASS_SET = frozenset(CLASSES)
FAIL_CLOSED_CLASSES = frozenset({CLASS_UNDOCUMENTED, CLASS_UNKNOWN})

# S026 / S101 class names this inventory must not reuse.
S026_CLASSES = frozenset({"network-required", "offline", "network-unknown"})
S101_CLASSES = frozenset({"documented", "assumed", "drifting"})

PAIR_FIELDS = frozenset({"local_command", "ci_command", "documented"})
DOCUMENT_FIELDS = frozenset({"schema_version", "pairs"})

REPO_ROOT = Path(__file__).resolve().parents[1]


class LocalCiDivergenceError(RuntimeError):
    """Raised when the local/CI command audit cannot classify fail-closed."""


@dataclass(frozen=True, slots=True)
class ClassifiedPair:
    """One classified fixture pair."""

    index: int
    classification: str
    local_command: object
    ci_command: object
    documented: object
    local_tokens: tuple[str, ...]
    ci_tokens: tuple[str, ...]
    evidence: tuple[str, ...]
    finding: str

    def as_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "class": self.classification,
            "local_command": self.local_command,
            "ci_command": self.ci_command,
            "documented": self.documented,
            "local_tokens": list(self.local_tokens),
            "ci_tokens": list(self.ci_tokens),
            "evidence": list(self.evidence),
            "finding": self.finding,
        }


def finding(code: str, message: str) -> str:
    return f"{FINDING_PREFIX} {code}: {message}"


def tokenize_command(raw: object) -> tuple[str, ...] | None:
    """Split a shell command into argv tokens. Untokenizable input is unknown."""

    if not isinstance(raw, str):
        return None
    try:
        tokens = tuple(shlex.split(raw, posix=True))
    except ValueError:
        return None
    if not tokens:
        return None
    return tokens


def _unknown_pair(
    *,
    index: int,
    local_command: object,
    ci_command: object,
    documented: object,
    reason: str,
) -> ClassifiedPair:
    code = CLASS_UNKNOWN
    return ClassifiedPair(
        index=index,
        classification=code,
        local_command=local_command,
        ci_command=ci_command,
        documented=documented,
        local_tokens=(),
        ci_tokens=(),
        evidence=(reason,),
        finding=finding(code, f"pair[{index}] {reason}"),
    )


def classify_pair(raw: object, *, index: int) -> ClassifiedPair:
    """Classify one ``{local_command, ci_command, documented}`` fixture row."""

    if not isinstance(raw, Mapping):
        return _unknown_pair(
            index=index,
            local_command=None,
            ci_command=None,
            documented=None,
            reason="pair must be an object",
        )

    extra = set(raw) - PAIR_FIELDS
    if extra:
        return _unknown_pair(
            index=index,
            local_command=raw.get("local_command"),
            ci_command=raw.get("ci_command"),
            documented=raw.get("documented"),
            reason="unknown fields: " + ", ".join(sorted(str(item) for item in extra)),
        )

    missing = PAIR_FIELDS - set(raw)
    if missing:
        return _unknown_pair(
            index=index,
            local_command=raw.get("local_command"),
            ci_command=raw.get("ci_command"),
            documented=raw.get("documented"),
            reason="missing fields: " + ", ".join(sorted(missing)),
        )

    documented = raw.get("documented")
    if not isinstance(documented, bool):
        return _unknown_pair(
            index=index,
            local_command=raw.get("local_command"),
            ci_command=raw.get("ci_command"),
            documented=documented,
            reason="documented must be a boolean",
        )

    local_command = raw.get("local_command")
    ci_command = raw.get("ci_command")
    local_tokens = tokenize_command(local_command)
    ci_tokens = tokenize_command(ci_command)
    if local_tokens is None or ci_tokens is None:
        reasons: list[str] = []
        if local_tokens is None:
            reasons.append("local_command is not a tokenizable non-empty string")
        if ci_tokens is None:
            reasons.append("ci_command is not a tokenizable non-empty string")
        return _unknown_pair(
            index=index,
            local_command=local_command,
            ci_command=ci_command,
            documented=documented,
            reason="; ".join(reasons),
        )

    if local_tokens == ci_tokens:
        classification = CLASS_MATCHING
        evidence = ("commands_match",)
    elif documented:
        classification = CLASS_INTENTIONAL
        evidence = ("commands_differ", "documented_true")
    else:
        classification = CLASS_UNDOCUMENTED
        evidence = ("commands_differ", "documented_false")

    if classification not in CLASS_SET:
        return _unknown_pair(
            index=index,
            local_command=local_command,
            ci_command=ci_command,
            documented=documented,
            reason="classification escaped the closed class set",
        )

    message = (
        f"pair[{index}] local={local_command!r} ci={ci_command!r} "
        f"documented={str(documented).lower()}"
    )
    return ClassifiedPair(
        index=index,
        classification=classification,
        local_command=local_command,
        ci_command=ci_command,
        documented=documented,
        local_tokens=local_tokens,
        ci_tokens=ci_tokens,
        evidence=evidence,
        finding=finding(classification, message),
    )


def classify_pairs(pairs: object) -> tuple[ClassifiedPair, ...]:
    """Classify a fixture list of command pairs. Non-lists fail as unknown."""

    if not isinstance(pairs, list):
        return (
            _unknown_pair(
                index=0,
                local_command=None,
                ci_command=None,
                documented=None,
                reason="pairs must be a list",
            ),
        )
    return tuple(classify_pair(item, index=index) for index, item in enumerate(pairs))


def classify_document(document: object) -> tuple[tuple[ClassifiedPair, ...], tuple[str, ...]]:
    """Classify a fixture document. Schema errors become unknown findings."""

    if not isinstance(document, Mapping):
        row = _unknown_pair(
            index=0,
            local_command=None,
            ci_command=None,
            documented=None,
            reason="document must be an object",
        )
        return (row,), (row.finding,)

    extra = set(document) - DOCUMENT_FIELDS
    missing = DOCUMENT_FIELDS - set(document)
    errors: list[str] = []
    if extra:
        errors.append(
            finding(CLASS_UNKNOWN, "unknown fields: " + ", ".join(sorted(str(item) for item in extra)))
        )
    if missing:
        errors.append(
            finding(CLASS_UNKNOWN, "missing fields: " + ", ".join(sorted(missing)))
        )
    if document.get("schema_version") != SCHEMA_VERSION:
        errors.append(
            finding(CLASS_UNKNOWN, f"schema_version must be exactly {SCHEMA_VERSION}")
        )

    rows = classify_pairs(document.get("pairs"))
    if not rows:
        empty = _unknown_pair(
            index=0,
            local_command=None,
            ci_command=None,
            documented=None,
            reason="zero pairs classified",
        )
        rows = (empty,)

    findings = tuple(errors) + tuple(row.finding for row in rows if row.classification in FAIL_CLOSED_CLASSES)
    return rows, findings


def count_class(rows: Sequence[ClassifiedPair], name: str) -> int:
    return sum(1 for row in rows if row.classification == name)


def is_closed(rows: Sequence[ClassifiedPair], findings: Sequence[str] = ()) -> bool:
    if findings:
        return False
    if not rows:
        return False
    return all(row.classification not in FAIL_CLOSED_CLASSES for row in rows)


def report_from_rows(
    rows: Sequence[ClassifiedPair],
    findings: Sequence[str] = (),
) -> dict[str, object]:
    return {
        "task_id": TASK_ID,
        "conflict_domain": CONFLICT_DOMAIN,
        "finding_prefix": FINDING_PREFIX,
        "inventory_version": INVENTORY_VERSION,
        "schema_version": SCHEMA_VERSION,
        "evidence_kind": EVIDENCE_KIND,
        "rewrite_workflows": REWRITE_WORKFLOWS,
        "mutations": list(MUTATION_ACTIONS),
        "classifications": list(CLASSES),
        "closed": is_closed(rows, findings),
        "pair_count": len(rows),
        "matching_count": count_class(rows, CLASS_MATCHING),
        "intentional_divergence_count": count_class(rows, CLASS_INTENTIONAL),
        "undocumented_divergence_count": count_class(rows, CLASS_UNDOCUMENTED),
        "unknown_count": count_class(rows, CLASS_UNKNOWN),
        "findings": list(findings),
        "records": [row.as_dict() for row in rows],
    }


def load_document(path: Path) -> object:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise LocalCiDivergenceError(finding(CLASS_UNKNOWN, f"fixture missing: {path}")) from exc
    except UnicodeError as exc:
        raise LocalCiDivergenceError(
            finding(CLASS_UNKNOWN, f"unreadable fixture {path.as_posix()}: {exc}")
        ) from exc
    except OSError as exc:
        raise LocalCiDivergenceError(
            finding(
                CLASS_UNKNOWN,
                f"unreadable fixture {path.as_posix()}: {exc.strerror or exc}",
            )
        ) from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise LocalCiDivergenceError(
            finding(
                CLASS_UNKNOWN,
                f"invalid JSON in {path.as_posix()} at line {exc.lineno}, column {exc.colno}",
            )
        ) from exc


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        help="JSON fixture with schema_version and pairs (required; live workflows are never rewritten)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the classification report as JSON",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.path is None:
        print(
            finding(CLASS_UNKNOWN, "fixture path is required; refusing to scan or rewrite workflows"),
            file=sys.stderr,
        )
        return 1
    try:
        document = load_document(args.path)
        rows, findings = classify_document(document)
        report = report_from_rows(rows, findings)
    except LocalCiDivergenceError as exc:
        print(f"{FINDING_PREFIX}: {exc}", file=sys.stderr)
        return 1

    counts = {name: count_class(rows, name) for name in CLASSES}
    print(
        f"{FINDING_PREFIX}: "
        + ", ".join(f"{name}={counts[name]}" for name in CLASSES)
        + f" closed={str(report['closed']).lower()} task_id={TASK_ID}"
    )
    if args.json:
        print(json.dumps(report, sort_keys=True, indent=2, separators=(",", ": ")))
    if findings:
        print(f"{FINDING_PREFIX} failed:", file=sys.stderr)
        for item in findings:
            print(f"  {item}", file=sys.stderr)
        return 1
    if REWRITE_WORKFLOWS or MUTATION_ACTIONS:
        print(finding(CLASS_UNKNOWN, "workflow mutation is forbidden"), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
