#!/usr/bin/env python3
"""Validate P1 failure knowledge against immutable LEARN-05 regressions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from scripts.check_p1_regression_corpus import load_corpus
from skeleton.contracts.canonical import EvidenceRef
from skeleton.eval.failure_knowledge import (
    FailureDisposition,
    FailureKnowledgeLedger,
    FailureKnowledgeRecord,
    FailureSourceKind,
)


ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = Path("machine/p1_failure_knowledge.json")
REGRESSION_PATH = Path("machine/p1_regression_corpus.json")
EXPECTED_TASK = "P1-LEARN-06"
EXPECTED_ACCOUNTABILITY = "ACC-P1-LEARN-06"
EXPECTED_POLICY = {
    "production_authority": False,
    "direct_self_modify": False,
    "immutable_record_identity": True,
    "additive_history_only": True,
    "required_source_kinds": [
        "counterexample",
        "failed_experiment",
        "incident",
        "rejected_design",
    ],
}


class FailureKnowledgeValidationError(RuntimeError):
    pass


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FailureKnowledgeValidationError(
            f"cannot read {path}"
        ) from exc


def _strict_keys(
    row: dict[str, Any],
    allowed: set[str],
    label: str,
) -> None:
    unknown = set(row) - allowed
    if unknown:
        raise FailureKnowledgeValidationError(
            f"{label}: unknown fields {sorted(unknown)}"
        )


def _evidence(rows: object, label: str) -> tuple[EvidenceRef, ...]:
    if not isinstance(rows, list) or not rows:
        raise FailureKnowledgeValidationError(
            f"{label}: evidence_refs must be non-empty"
        )
    result = []
    for row in rows:
        if not isinstance(row, dict):
            raise FailureKnowledgeValidationError(
                f"{label}: evidence entry must be object"
            )
        _strict_keys(
            row,
            {"source", "digest", "category"},
            f"{label}.evidence",
        )
        result.append(
            EvidenceRef(
                source=row["source"],
                digest=row["digest"],
                category=row["category"],
            )
        )
    return tuple(result)


def load_ledger(
    root: Path = ROOT,
    *,
    ledger_path: Path = LEDGER_PATH,
    regression_path: Path = REGRESSION_PATH,
) -> tuple[dict[str, Any], FailureKnowledgeLedger]:
    payload = _load(root / ledger_path)
    if not isinstance(payload, dict):
        raise FailureKnowledgeValidationError(
            "ledger root must be an object"
        )
    _strict_keys(
        payload,
        {
            "schema_version",
            "ledger_id",
            "ledger_version",
            "task_id",
            "accountability_ref",
            "authority",
            "regression_authority",
            "policy",
            "records",
        },
        "ledger",
    )
    if payload.get("schema_version") != 1:
        raise FailureKnowledgeValidationError(
            "schema_version must equal 1"
        )
    if payload.get("task_id") != EXPECTED_TASK:
        raise FailureKnowledgeValidationError("task_id drift")
    if payload.get("accountability_ref") != EXPECTED_ACCOUNTABILITY:
        raise FailureKnowledgeValidationError(
            "accountability_ref drift"
        )
    if payload.get("authority") != str(LEDGER_PATH):
        raise FailureKnowledgeValidationError("authority path drift")
    if payload.get("regression_authority") != str(REGRESSION_PATH):
        raise FailureKnowledgeValidationError(
            "regression authority drift"
        )
    if payload.get("policy") != EXPECTED_POLICY:
        raise FailureKnowledgeValidationError(
            "failure knowledge policy drift"
        )

    _, corpus = load_corpus(
        root,
        registry_path=regression_path,
    )
    cases = {
        (case.case_id, case.version): case
        for case in corpus.cases
    }
    raw_records = payload.get("records")
    if not isinstance(raw_records, list) or not raw_records:
        raise FailureKnowledgeValidationError(
            "records must be a non-empty list"
        )

    records = []
    for raw in raw_records:
        if not isinstance(raw, dict):
            raise FailureKnowledgeValidationError(
                "record entries must be objects"
            )
        _strict_keys(
            raw,
            {
                "record_id",
                "version",
                "sequence",
                "source_kind",
                "source_ref",
                "source_digest",
                "failure_fingerprint",
                "summary",
                "root_cause_digest",
                "disposition",
                "regression_case_id",
                "regression_case_version",
                "evidence_refs",
            },
            str(raw.get("record_id", "?")),
        )
        if raw.get("disposition") != "regression_covered":
            raise FailureKnowledgeValidationError(
                f"{raw.get('record_id', '?')}: canonical seed ledger "
                "must be regression-covered"
            )
        key = (
            raw.get("regression_case_id"),
            raw.get("regression_case_version"),
        )
        case = cases.get(key)
        if case is None:
            raise FailureKnowledgeValidationError(
                f"{raw.get('record_id', '?')}: unknown regression case {key}"
            )
        records.append(
            FailureKnowledgeRecord(
                record_id=raw["record_id"],
                version=raw["version"],
                sequence=raw["sequence"],
                source_kind=FailureSourceKind(raw["source_kind"]),
                source_ref=raw["source_ref"],
                source_digest=raw["source_digest"],
                failure_class=case.failure_class,
                failure_fingerprint=raw["failure_fingerprint"],
                summary=raw["summary"],
                root_cause_digest=raw["root_cause_digest"],
                risk_obligation_id=case.risk_obligation_id,
                risk_obligation_digest=case.risk_obligation_digest,
                disposition=FailureDisposition.REGRESSION_COVERED,
                evidence_refs=_evidence(
                    raw["evidence_refs"],
                    raw["record_id"],
                ),
                regression_case_id=case.case_id,
                regression_case_version=case.version,
                regression_case_digest=case.case_digest,
            )
        )

    ledger = FailureKnowledgeLedger(
        ledger_id=payload["ledger_id"],
        version=payload["ledger_version"],
        records=tuple(records),
    )
    required = set(EXPECTED_POLICY["required_source_kinds"])
    present = {record.source_kind.value for record in ledger.records}
    missing = sorted(required - present)
    if missing:
        raise FailureKnowledgeValidationError(
            "required source kinds missing: " + ",".join(missing)
        )
    return payload, ledger


def validate_repository(
    root: Path = ROOT,
    *,
    ledger_path: Path = LEDGER_PATH,
    regression_path: Path = REGRESSION_PATH,
) -> dict[str, Any]:
    _, ledger = load_ledger(
        root,
        ledger_path=ledger_path,
        regression_path=regression_path,
    )
    return {
        "schema_version": 1,
        "task_id": EXPECTED_TASK,
        "accountability_ref": EXPECTED_ACCOUNTABILITY,
        "ledger_id": ledger.ledger_id,
        "ledger_version": ledger.version,
        "record_count": len(ledger.records),
        "ledger_digest": ledger.ledger_digest,
        "source_kinds": sorted(
            {item.source_kind.value for item in ledger.records}
        ),
        "production_authority": False,
        "direct_self_modify": False,
        "valid": True,
    }


def compare_ledgers(
    root: Path,
    *,
    baseline_path: Path,
    candidate_path: Path = LEDGER_PATH,
    regression_path: Path = REGRESSION_PATH,
) -> dict[str, Any]:
    _, baseline = load_ledger(
        root,
        ledger_path=baseline_path,
        regression_path=regression_path,
    )
    _, candidate = load_ledger(
        root,
        ledger_path=candidate_path,
        regression_path=regression_path,
    )
    before = {
        (record.record_id, record.version): record
        for record in baseline.records
    }
    after = {
        (record.record_id, record.version): record
        for record in candidate.records
    }
    removed = sorted(set(before) - set(after))
    mutated = sorted(
        key
        for key in set(before) & set(after)
        if before[key].record_digest != after[key].record_digest
    )
    added = sorted(set(after) - set(before))
    return {
        "accepted": not removed and not mutated,
        "baseline_digest": baseline.ledger_digest,
        "candidate_digest": candidate.ledger_digest,
        "removed": [list(key) for key in removed],
        "mutated": [list(key) for key in mutated],
        "added": [list(key) for key in added],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=LEDGER_PATH)
    parser.add_argument(
        "--regressions",
        type=Path,
        default=REGRESSION_PATH,
    )
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args(argv)
    try:
        payload: dict[str, Any] = {
            "failure_knowledge": validate_repository(
                ROOT,
                ledger_path=args.ledger,
                regression_path=args.regressions,
            )
        }
        if args.baseline is not None:
            lineage = compare_ledgers(
                ROOT,
                baseline_path=args.baseline,
                candidate_path=args.ledger,
                regression_path=args.regressions,
            )
            payload["lineage"] = lineage
            if lineage["accepted"] is not True:
                raise FailureKnowledgeValidationError(
                    "candidate rewrites immutable failure history"
                )
        if args.out is not None:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        if args.print_summary:
            print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    except (
        FailureKnowledgeValidationError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        print(
            f"P1 failure knowledge: rejected: {exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
