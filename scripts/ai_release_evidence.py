#!/usr/bin/env python3
"""Collect fail-closed AI journey/fault evidence for the canonical release gate.

Only concrete test result artifacts are accepted. The collector supports JUnit
XML and pytest-json-report JSON, requires at least one executed test, rejects
failures/errors/skips, hashes the exact report bytes, and emits the existing
skeleton.release.evidence TestEvidence payload shape.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
import xml.etree.ElementTree as ET


_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_CANONICAL_PART_RE = re.compile(r"^[^/\\]+$")


class AIReleaseEvidenceError(ValueError):
    """AI result evidence is missing, ambiguous, or not passing."""


@dataclass(frozen=True, slots=True)
class ResultSummary:
    tests: int
    passed: int
    failed: int
    errors: int
    skipped: int

    def __post_init__(self) -> None:
        for name in ("tests", "passed", "failed", "errors", "skipped"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise AIReleaseEvidenceError(f"{name} must be a non-negative integer")
        if self.tests < self.passed + self.failed + self.errors + self.skipped:
            raise AIReleaseEvidenceError("test summary counts are inconsistent")

    @property
    def clean_pass(self) -> bool:
        return (
            self.tests > 0
            and self.failed == 0
            and self.errors == 0
            and self.skipped == 0
            and self.passed == self.tests
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_name(path: Path) -> str:
    name = path.as_posix()
    if path.is_absolute() or "\\" in name:
        raise AIReleaseEvidenceError(
            "evidence input names must be repository-relative POSIX paths"
        )
    parts = name.split("/")
    if any(
        not part
        or part in {".", ".."}
        or _CANONICAL_PART_RE.fullmatch(part) is None
        for part in parts
    ):
        raise AIReleaseEvidenceError("evidence input name is not canonical")
    return name


def _integer(value: object, field: str) -> int:
    if isinstance(value, bool):
        raise AIReleaseEvidenceError(f"{field} must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise AIReleaseEvidenceError(f"{field} must be an integer") from exc
    if parsed < 0:
        raise AIReleaseEvidenceError(f"{field} must be non-negative")
    return parsed


def _junit_summary(path: Path) -> ResultSummary:
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as exc:
        raise AIReleaseEvidenceError("JUnit evidence is not valid XML") from exc

    suites = []
    if root.tag == "testsuite":
        suites = [root]
    elif root.tag == "testsuites":
        suites = list(root.findall("testsuite"))
    else:
        raise AIReleaseEvidenceError(
            "JUnit evidence root must be testsuite or testsuites"
        )
    if not suites:
        raise AIReleaseEvidenceError("JUnit evidence contains no test suites")

    tests = failures = errors = skipped = 0
    for suite in suites:
        tests += _integer(suite.attrib.get("tests", 0), "junit.tests")
        failures += _integer(
            suite.attrib.get("failures", 0),
            "junit.failures",
        )
        errors += _integer(suite.attrib.get("errors", 0), "junit.errors")
        skipped += _integer(
            suite.attrib.get("skipped", suite.attrib.get("disabled", 0)),
            "junit.skipped",
        )
    passed = tests - failures - errors - skipped
    if passed < 0:
        raise AIReleaseEvidenceError("JUnit counts are inconsistent")
    return ResultSummary(
        tests=tests,
        passed=passed,
        failed=failures,
        errors=errors,
        skipped=skipped,
    )


def _pytest_json_summary(path: Path) -> ResultSummary:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AIReleaseEvidenceError(
            "pytest JSON evidence is not valid JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise AIReleaseEvidenceError("pytest JSON evidence must be an object")
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        raise AIReleaseEvidenceError(
            "pytest JSON evidence is missing summary"
        )

    passed = _integer(summary.get("passed", 0), "pytest.summary.passed")
    failed = _integer(summary.get("failed", 0), "pytest.summary.failed")
    errors = _integer(
        summary.get("error", summary.get("errors", 0)),
        "pytest.summary.errors",
    )
    skipped = _integer(summary.get("skipped", 0), "pytest.summary.skipped")
    explicit_total = summary.get("total")
    if explicit_total is None:
        tests = passed + failed + errors + skipped
    else:
        tests = _integer(explicit_total, "pytest.summary.total")
        if tests != passed + failed + errors + skipped:
            # Some pytest-json-report versions omit xfailed/xpassed from the
            # compact counters. If detailed tests are present, count their
            # terminal outcomes instead of guessing.
            detailed = payload.get("tests")
            if not isinstance(detailed, list):
                raise AIReleaseEvidenceError(
                    "pytest JSON summary is internally inconsistent"
                )
            outcomes = [
                item.get("outcome")
                for item in detailed
                if isinstance(item, dict)
            ]
            if len(outcomes) != tests or any(
                outcome not in {"passed", "failed", "skipped"}
                for outcome in outcomes
            ):
                raise AIReleaseEvidenceError(
                    "pytest JSON detailed outcomes are incomplete"
                )
            passed = sum(outcome == "passed" for outcome in outcomes)
            failed = sum(outcome == "failed" for outcome in outcomes)
            skipped = sum(outcome == "skipped" for outcome in outcomes)
            errors = 0
    return ResultSummary(
        tests=tests,
        passed=passed,
        failed=failed,
        errors=errors,
        skipped=skipped,
    )


def inspect_result(path: Path) -> ResultSummary:
    if not path.is_file():
        raise FileNotFoundError(path)
    lowered = path.name.lower()
    if lowered.endswith(".xml"):
        return _junit_summary(path)
    if lowered.endswith(".json"):
        return _pytest_json_summary(path)
    raise AIReleaseEvidenceError(
        "AI evidence must be JUnit .xml or pytest-json-report .json"
    )


def evidence_record(
    *,
    evidence_id: str,
    path: Path,
) -> dict[str, str]:
    token = str(evidence_id).strip()
    if not _TOKEN_RE.fullmatch(token):
        raise AIReleaseEvidenceError(
            "evidence_id must be a canonical release-evidence token"
        )
    summary = inspect_result(path)
    if not summary.clean_pass:
        raise AIReleaseEvidenceError(
            "AI evidence is not a clean pass: "
            f"tests={summary.tests} passed={summary.passed} "
            f"failed={summary.failed} errors={summary.errors} "
            f"skipped={summary.skipped}"
        )
    return {
        "evidence_id": token,
        "name": _canonical_name(path),
        "sha256": _sha256(path),
        "result": "pass",
    }


def _parse_record(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise AIReleaseEvidenceError(
            "record must use evidence_id=repository/relative/report.ext"
        )
    evidence_id, raw_path = value.split("=", 1)
    if not evidence_id.strip() or not raw_path.strip():
        raise AIReleaseEvidenceError(
            "record must include evidence_id and path"
        )
    return evidence_id.strip(), Path(raw_path.strip())


def _stage7_records(
    path: Path,
    *,
    lane: str,
    manifest: Path,
) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(path)
    lowered = path.name.lower()
    if lowered.endswith(".xml"):
        report_format = "junit"
    elif lowered.endswith(".json"):
        report_format = "pytest-json"
    else:
        raise AIReleaseEvidenceError(
            "Stage-7 report must be JUnit .xml or pytest-json-report .json"
        )

    try:
        from skeleton.release.ai_journey_evidence import (
            collect_ai_journey_evidence,
            requirements_from_manifest,
        )
        manifest_path = manifest
        manifest_payload = json.loads(
            manifest_path.read_text(encoding="utf-8")
        )
        requirements = requirements_from_manifest(manifest_payload)
        bundle = collect_ai_journey_evidence(
            report_name=_canonical_name(path),
            report_bytes=path.read_bytes(),
            report_format=report_format,
            requirements=requirements,
        )
    except Exception as exc:
        if isinstance(exc, (AIReleaseEvidenceError, FileNotFoundError)):
            raise
        raise AIReleaseEvidenceError(
            f"Stage-7 journey matrix failed: {exc}"
        ) from exc

    selected = (
        bundle.test_evidence
        if lane == "test"
        else bundle.eval_evidence
    )
    return [item.to_payload() for item in selected]


def collect(args: argparse.Namespace) -> int:
    if not args.record and args.stage7_report is None:
        raise AIReleaseEvidenceError(
            "at least one --record or --stage7-report is required"
        )
    if args.stage7_report is None and args.stage7_lane is not None:
        raise AIReleaseEvidenceError(
            "--stage7-lane requires --stage7-report"
        )
    if args.stage7_report is not None and args.stage7_lane is None:
        raise AIReleaseEvidenceError(
            "--stage7-report requires --stage7-lane"
        )

    records: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in args.record:
        evidence_id, path = _parse_record(raw)
        if evidence_id in seen:
            raise AIReleaseEvidenceError(
                f"duplicate evidence_id: {evidence_id}"
            )
        seen.add(evidence_id)
        records.append(
            evidence_record(
                evidence_id=evidence_id,
                path=path,
            )
        )

    if args.stage7_report is not None:
        for record in _stage7_records(
            Path(args.stage7_report),
            lane=str(args.stage7_lane),
            manifest=Path(args.stage7_manifest),
        ):
            evidence_id = record["evidence_id"]
            if evidence_id in seen:
                raise AIReleaseEvidenceError(
                    f"duplicate evidence_id: {evidence_id}"
                )
            seen.add(evidence_id)
            records.append(record)

    records.sort(key=lambda item: item["evidence_id"])
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(records, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--record",
        action="append",
        default=[],
        help="passing report as evidence_id=repository/relative/report.xml|json",
    )
    parser.add_argument(
        "--stage7-report",
        help="full AI runtime JUnit/pytest JSON report for mandatory Stage-7 matrix validation",
    )
    parser.add_argument(
        "--stage7-manifest",
        default="machine/ai_required_journeys.json",
        help="machine contract defining the mandatory Stage-7 AI journey matrix",
    )
    parser.add_argument(
        "--stage7-lane",
        choices=("test", "eval"),
        help="release evidence lane emitted from --stage7-report",
    )
    parser.add_argument("--output", required=True)
    parser.set_defaults(func=collect)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (AIReleaseEvidenceError, FileNotFoundError) as exc:
        parser.error(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
