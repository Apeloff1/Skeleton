#!/usr/bin/env python3
"""Validate immutable P1 regression cases and their EVID-04 risk identities."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from skeleton.contracts.risk_evidence import (
    RiskKind,
    RiskObligation,
    RiskSeverity,
    make_obligation_id,
)
from skeleton.eval.regression_corpus import (
    FailureClass,
    RegressionCase,
    RegressionCorpus,
    RegressionCorpusError,
    SafeOutcome,
)


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = Path("machine/p1_regression_corpus.json")
EXPECTED_TASK = "P1-LEARN-05"
EXPECTED_ACCOUNTABILITY = "ACC-P1-LEARN-05"
EXPECTED_POLICY = {
    "production_authority": False,
    "all_cases_promotion_blocking": True,
    "independent_evaluator_required": True,
    "side_effects_forbidden": True,
    "immutable_case_identity": True,
    "additive_history_only": True,
    "benchmark_qualification_required": True,
    "required_failure_classes": [
        "evidence_substitution",
        "reasoning_error",
        "side_effect_escape",
        "specification_gaming",
    ],
}


class RegressionCorpusValidationError(RuntimeError):
    pass


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RegressionCorpusValidationError(
            f"cannot read {path}"
        ) from exc


def _strict_keys(
    row: dict[str, Any],
    allowed: set[str],
    label: str,
) -> None:
    unknown = set(row) - allowed
    if unknown:
        raise RegressionCorpusValidationError(
            f"{label}: unknown fields {sorted(unknown)}"
        )


def _case(row: object) -> RegressionCase:
    if not isinstance(row, dict):
        raise RegressionCorpusValidationError(
            "case entries must be objects"
        )
    _strict_keys(
        row,
        {
            "case_id",
            "version",
            "failure_class",
            "description",
            "source_ref",
            "source_digest",
            "input_digest",
            "expected_outcome",
            "evaluator_id",
            "evaluator_digest",
            "tags",
            "risk",
        },
        str(row.get("case_id", "?")),
    )
    risk = row.get("risk")
    if not isinstance(risk, dict):
        raise RegressionCorpusValidationError(
            f"{row.get('case_id', '?')}: risk must be an object"
        )
    _strict_keys(
        risk,
        {
            "kind",
            "source_ref",
            "statement",
            "source_digest",
            "default_severity",
            "blocking_by_default",
            "required_evidence_modes",
        },
        f"{row.get('case_id', '?')}.risk",
    )
    kind = RiskKind(risk["kind"])
    severity = RiskSeverity(risk["default_severity"])
    if risk.get("blocking_by_default") is not True:
        raise RegressionCorpusValidationError(
            f"{row.get('case_id', '?')}: risk must be blocking"
        )
    modes = tuple(risk.get("required_evidence_modes", []))
    if "regression" not in modes:
        raise RegressionCorpusValidationError(
            f"{row.get('case_id', '?')}: risk requires regression evidence"
        )
    obligation = RiskObligation(
        obligation_id=make_obligation_id(
            kind,
            risk["source_ref"],
            risk["statement"],
        ),
        kind=kind,
        source_ref=risk["source_ref"],
        statement=risk["statement"],
        source_digest=risk["source_digest"],
        default_severity=severity,
        blocking_by_default=True,
        required_evidence_modes=modes,
    )
    return RegressionCase(
        case_id=row["case_id"],
        version=row["version"],
        failure_class=FailureClass(row["failure_class"]),
        description=row["description"],
        source_ref=row["source_ref"],
        source_digest=row["source_digest"],
        input_digest=row["input_digest"],
        expected_outcome=SafeOutcome(row["expected_outcome"]),
        evaluator_id=row["evaluator_id"],
        evaluator_digest=row["evaluator_digest"],
        risk_obligation_id=obligation.obligation_id,
        risk_obligation_digest=obligation.obligation_digest,
        tags=tuple(row.get("tags", [])),
        promotion_blocking=True,
    )


def load_corpus(
    root: Path = ROOT,
    *,
    registry_path: Path = REGISTRY_PATH,
) -> tuple[dict[str, Any], RegressionCorpus]:
    payload = _load(root / registry_path)
    if not isinstance(payload, dict):
        raise RegressionCorpusValidationError(
            "registry root must be an object"
        )
    _strict_keys(
        payload,
        {
            "schema_version",
            "corpus_id",
            "corpus_version",
            "task_id",
            "accountability_ref",
            "authority",
            "policy",
            "cases",
        },
        "registry",
    )
    if payload.get("schema_version") != 1:
        raise RegressionCorpusValidationError(
            "schema_version must equal 1"
        )
    if payload.get("task_id") != EXPECTED_TASK:
        raise RegressionCorpusValidationError("task_id drift")
    if payload.get("accountability_ref") != EXPECTED_ACCOUNTABILITY:
        raise RegressionCorpusValidationError(
            "accountability_ref drift"
        )
    if payload.get("authority") != str(REGISTRY_PATH):
        raise RegressionCorpusValidationError(
            "authority path drift"
        )
    if payload.get("policy") != EXPECTED_POLICY:
        raise RegressionCorpusValidationError(
            "regression policy drift"
        )
    rows = payload.get("cases")
    if not isinstance(rows, list) or not rows:
        raise RegressionCorpusValidationError(
            "cases must be a non-empty list"
        )
    cases = tuple(_case(row) for row in rows)
    corpus = RegressionCorpus(
        corpus_id=payload["corpus_id"],
        version=payload["corpus_version"],
        cases=cases,
    )
    required = set(EXPECTED_POLICY["required_failure_classes"])
    present = {item.failure_class.value for item in corpus.cases}
    missing = sorted(required - present)
    if missing:
        raise RegressionCorpusValidationError(
            "required failure classes missing: " + ",".join(missing)
        )
    return payload, corpus


def validate_repository(
    root: Path = ROOT,
    *,
    registry_path: Path = REGISTRY_PATH,
) -> dict[str, Any]:
    _, corpus = load_corpus(root, registry_path=registry_path)
    return {
        "schema_version": 1,
        "task_id": EXPECTED_TASK,
        "accountability_ref": EXPECTED_ACCOUNTABILITY,
        "corpus_id": corpus.corpus_id,
        "corpus_version": corpus.version,
        "case_count": len(corpus.cases),
        "corpus_digest": corpus.corpus_digest,
        "failure_classes": sorted(
            {item.failure_class.value for item in corpus.cases}
        ),
        "production_authority": False,
        "valid": True,
    }


def compare_corpora(
    root: Path,
    *,
    baseline_path: Path,
    candidate_path: Path = REGISTRY_PATH,
) -> dict[str, Any]:
    _, baseline = load_corpus(root, registry_path=baseline_path)
    _, candidate = load_corpus(root, registry_path=candidate_path)
    before = {
        (item.case_id, item.version): item
        for item in baseline.cases
    }
    after = {
        (item.case_id, item.version): item
        for item in candidate.cases
    }
    removed = sorted(set(before) - set(after))
    mutated = sorted(
        key
        for key in set(before) & set(after)
        if before[key].case_digest != after[key].case_digest
    )
    added = sorted(set(after) - set(before))
    return {
        "accepted": not removed and not mutated,
        "baseline_digest": baseline.corpus_digest,
        "candidate_digest": candidate.corpus_digest,
        "removed": [list(key) for key in removed],
        "mutated": [list(key) for key in mutated],
        "added": [list(key) for key in added],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=REGISTRY_PATH)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args(argv)
    try:
        payload: dict[str, Any] = {
            "corpus": validate_repository(
                ROOT,
                registry_path=args.registry,
            )
        }
        if args.baseline is not None:
            lineage = compare_corpora(
                ROOT,
                baseline_path=args.baseline,
                candidate_path=args.registry,
            )
            payload["lineage"] = lineage
            if lineage["accepted"] is not True:
                raise RegressionCorpusValidationError(
                    "candidate rewrites immutable regression history"
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
        RegressionCorpusValidationError,
        RegressionCorpusError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        print(f"P1 regression corpus: rejected: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
