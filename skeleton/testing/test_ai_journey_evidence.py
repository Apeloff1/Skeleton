from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from skeleton.release.ai_journey_evidence import (
    AIJourneyRequirement,
    MANDATORY_AI_JOURNEYS,
    collect_ai_journey_evidence,
)
from skeleton.release.evidence import EvidenceSchemaError


REQS = (
    AIJourneyRequirement(
        "journey-basic",
        "tests/test_basic.py::test_basic",
        lane="test",
    ),
    AIJourneyRequirement(
        "journey-fault",
        "tests/test_fault.py::test_fault",
        lane="eval",
    ),
)


def _pytest_report(
    *,
    basic: str = "passed",
    fault: str = "passed",
):
    return json.dumps(
        {
            "summary": {"passed": 2},
            "tests": [
                {
                    "nodeid": "tests/test_basic.py::test_basic",
                    "outcome": basic,
                },
                {
                    "nodeid": "tests/test_fault.py::test_fault",
                    "outcome": fault,
                },
            ],
        },
        sort_keys=True,
    ).encode("utf-8")


def test_pytest_json_emits_test_and_eval_evidence_bound_to_report_bytes() -> None:
    report = _pytest_report()
    bundle = collect_ai_journey_evidence(
        report_name="artifacts/ai-journeys.json",
        report_bytes=report,
        report_format="pytest-json",
        requirements=REQS,
    )

    digest = hashlib.sha256(report).hexdigest()
    assert [item.evidence_id for item in bundle.test_evidence] == [
        "journey-basic"
    ]
    assert [item.evidence_id for item in bundle.eval_evidence] == [
        "journey-fault"
    ]
    assert bundle.test_evidence[0].sha256 == digest
    assert bundle.eval_evidence[0].sha256 == digest
    assert bundle.release_kwargs() == {
        "test_evidence": bundle.test_evidence,
        "eval_evidence": bundle.eval_evidence,
    }


@pytest.mark.parametrize("outcome", ["failed", "skipped", "xfailed"])
def test_nonpassing_required_journey_fails_closed(outcome: str) -> None:
    with pytest.raises(
        EvidenceSchemaError,
        match="non-passing required AI journeys",
    ):
        collect_ai_journey_evidence(
            report_name="artifacts/ai-journeys.json",
            report_bytes=_pytest_report(fault=outcome),
            report_format="pytest-json",
            requirements=REQS,
        )


def test_missing_required_journey_fails_closed() -> None:
    report = json.dumps(
        {
            "tests": [
                {
                    "nodeid": "tests/test_basic.py::test_basic",
                    "outcome": "passed",
                }
            ]
        }
    ).encode("utf-8")
    with pytest.raises(
        EvidenceSchemaError,
        match="missing required AI journeys",
    ):
        collect_ai_journey_evidence(
            report_name="artifacts/ai-journeys.json",
            report_bytes=report,
            report_format="json",
            requirements=REQS,
        )


def test_conflicting_duplicate_outcomes_fail_closed() -> None:
    report = json.dumps(
        {
            "tests": [
                {
                    "nodeid": "tests/test_basic.py::test_basic",
                    "outcome": "passed",
                },
                {
                    "nodeid": "tests/test_basic.py::test_basic",
                    "outcome": "failed",
                },
                {
                    "nodeid": "tests/test_fault.py::test_fault",
                    "outcome": "passed",
                },
            ]
        }
    ).encode("utf-8")
    with pytest.raises(EvidenceSchemaError, match="conflicting outcomes"):
        collect_ai_journey_evidence(
            report_name="artifacts/ai-journeys.json",
            report_bytes=report,
            report_format="pytest-json",
            requirements=REQS,
        )


def test_junit_file_and_classname_identities_match_exact_required_nodes() -> None:
    report = b"""<?xml version="1.0" encoding="utf-8"?>
<testsuite tests="2" failures="0" errors="0" skipped="0">
  <testcase classname="tests.test_basic" file="tests/test_basic.py" name="test_basic"/>
  <testcase classname="tests.test_fault" file="tests/test_fault.py" name="test_fault"/>
</testsuite>
"""
    bundle = collect_ai_journey_evidence(
        report_name="artifacts/ai-journeys.xml",
        report_bytes=report,
        report_format="junit",
        requirements=REQS,
    )

    assert len(bundle.test_evidence) == 1
    assert len(bundle.eval_evidence) == 1
    assert "tests/test_basic.py::test_basic" in bundle.observed_cases
    assert "tests/test_fault.py::test_fault" in bundle.observed_cases


def test_junit_skipped_case_is_not_release_evidence() -> None:
    report = b"""<testsuite tests="2">
  <testcase file="tests/test_basic.py" name="test_basic"/>
  <testcase file="tests/test_fault.py" name="test_fault"><skipped/></testcase>
</testsuite>"""
    with pytest.raises(
        EvidenceSchemaError,
        match="non-passing required AI journeys",
    ):
        collect_ai_journey_evidence(
            report_name="artifacts/ai-journeys.xml",
            report_bytes=report,
            report_format="xml",
            requirements=REQS,
        )


@pytest.mark.parametrize(
    "name",
    [
        "../journeys.xml",
        "/tmp/journeys.xml",
        "artifacts\\journeys.xml",
        "artifacts//journeys.xml",
        "artifacts/../journeys.xml",
    ],
)
def test_report_name_must_be_canonical_relative_path(name: str) -> None:
    with pytest.raises(EvidenceSchemaError, match="canonical relative path"):
        collect_ai_journey_evidence(
            report_name=name,
            report_bytes=_pytest_report(),
            report_format="pytest-json",
            requirements=REQS,
        )


def test_duplicate_requirement_identity_fails_closed() -> None:
    duplicate = (
        REQS[0],
        AIJourneyRequirement(
            "journey-basic",
            "tests/test_other.py::test_other",
            lane="eval",
        ),
    )
    with pytest.raises(EvidenceSchemaError, match="evidence ids must be unique"):
        collect_ai_journey_evidence(
            report_name="artifacts/ai-journeys.json",
            report_bytes=_pytest_report(),
            report_format="pytest-json",
            requirements=duplicate,
        )


def test_empty_or_planned_report_is_not_evidence() -> None:
    planned = json.dumps({"tests": []}).encode("utf-8")
    with pytest.raises(EvidenceSchemaError, match="contains no test cases"):
        collect_ai_journey_evidence(
            report_name="artifacts/ai-journeys.json",
            report_bytes=planned,
            report_format="pytest-json",
            requirements=REQS,
        )



def test_mandatory_journey_matrix_references_real_test_functions() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    missing: list[str] = []
    for requirement in MANDATORY_AI_JOURNEYS:
        path_text, function_name = requirement.nodeid.split("::", 1)
        path = repo_root / path_text
        if not path.is_file():
            missing.append(requirement.nodeid + ":missing-file")
            continue
        source = path.read_text(encoding="utf-8")
        if (
            f"def {function_name}(" not in source
            and f"async def {function_name}(" not in source
        ):
            missing.append(requirement.nodeid + ":missing-function")

    assert missing == []



def test_full_mandatory_matrix_emits_only_when_every_journey_passes() -> None:
    report = json.dumps(
        {
            "tests": [
                {
                    "nodeid": requirement.nodeid,
                    "outcome": "passed",
                }
                for requirement in MANDATORY_AI_JOURNEYS
            ]
        },
        sort_keys=True,
    ).encode("utf-8")

    bundle = collect_ai_journey_evidence(
        report_name="artifacts/ai-mandatory-journeys.json",
        report_bytes=report,
        report_format="pytest-json",
    )

    expected_test = sorted(
        requirement.evidence_id
        for requirement in MANDATORY_AI_JOURNEYS
        if requirement.lane == "test"
    )
    expected_eval = sorted(
        requirement.evidence_id
        for requirement in MANDATORY_AI_JOURNEYS
        if requirement.lane == "eval"
    )
    assert [item.evidence_id for item in bundle.test_evidence] == expected_test
    assert [item.evidence_id for item in bundle.eval_evidence] == expected_eval
    assert set(bundle.observed_cases) >= {
        requirement.nodeid
        for requirement in MANDATORY_AI_JOURNEYS
    }


def test_full_mandatory_matrix_fails_if_one_required_fault_is_missing() -> None:
    missing = MANDATORY_AI_JOURNEYS[-1]
    report = json.dumps(
        {
            "tests": [
                {
                    "nodeid": requirement.nodeid,
                    "outcome": "passed",
                }
                for requirement in MANDATORY_AI_JOURNEYS[:-1]
            ]
        },
        sort_keys=True,
    ).encode("utf-8")

    with pytest.raises(
        EvidenceSchemaError,
        match="missing required AI journeys",
    ) as exc:
        collect_ai_journey_evidence(
            report_name="artifacts/ai-mandatory-journeys.json",
            report_bytes=report,
            report_format="pytest-json",
        )

    assert missing.nodeid in str(exc.value)
