from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest

from skeleton.release.ai_journey_evidence import MANDATORY_AI_JOURNEYS


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ai_release_evidence.py"
SPEC = importlib.util.spec_from_file_location("ai_release_evidence", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
ai_release_evidence = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ai_release_evidence
SPEC.loader.exec_module(ai_release_evidence)


def _write_junit(
    path: Path,
    *,
    tests: int = 2,
    failures: int = 0,
    errors: int = 0,
    skipped: int = 0,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        (
            '<testsuite name="ai" '
            f'tests="{tests}" failures="{failures}" '
            f'errors="{errors}" skipped="{skipped}">'
            "</testsuite>"
        ),
        encoding="utf-8",
    )


def _write_pytest_json(
    path: Path,
    *,
    passed: int = 2,
    failed: int = 0,
    errors: int = 0,
    skipped: int = 0,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    total = passed + failed + errors + skipped
    path.write_text(
        json.dumps(
            {
                "summary": {
                    "passed": passed,
                    "failed": failed,
                    "error": errors,
                    "skipped": skipped,
                    "total": total,
                }
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _write_stage7_junit(
    path: Path,
    *,
    prefix: str = "",
    omit_nodeid: str | None = None,
    fail_nodeid: str | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cases: list[str] = []
    failures = 0
    for requirement in MANDATORY_AI_JOURNEYS:
        if requirement.nodeid == omit_nodeid:
            continue
        file_name, function_name = requirement.nodeid.split("::", 1)
        body = ""
        if requirement.nodeid == fail_nodeid:
            body = "<failure message=\"boom\"/>"
            failures += 1
        cases.append(
            f'<testcase file="{prefix}{file_name}" '
            f'name="{function_name}">{body}</testcase>'
        )
    path.write_text(
        (
            f'<testsuite name="stage7" tests="{len(cases)}" '
            f'failures="{failures}" errors="0" skipped="0">'
            + "".join(cases)
            + "</testsuite>"
        ),
        encoding="utf-8",
    )


def test_clean_junit_emits_hash_bound_canonical_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    report = Path("reports/ai-golden.xml")
    _write_junit(report)

    record = ai_release_evidence.evidence_record(
        evidence_id="ai-golden",
        path=report,
    )

    assert record == {
        "evidence_id": "ai-golden",
        "name": "reports/ai-golden.xml",
        "sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
        "result": "pass",
    }


def test_clean_pytest_json_emits_hash_bound_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    report = Path("reports/ai-faults.json")
    _write_pytest_json(report, passed=3)

    record = ai_release_evidence.evidence_record(
        evidence_id="ai-faults",
        path=report,
    )

    assert record["result"] == "pass"
    assert record["name"] == "reports/ai-faults.json"
    assert record["sha256"] == hashlib.sha256(report.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    ("kind", "kwargs", "reason"),
    [
        ("junit", {"tests": 0}, "not a clean pass"),
        ("junit", {"tests": 2, "failures": 1}, "not a clean pass"),
        ("junit", {"tests": 2, "errors": 1}, "not a clean pass"),
        ("junit", {"tests": 2, "skipped": 1}, "not a clean pass"),
        ("json", {"passed": 0}, "not a clean pass"),
        ("json", {"passed": 1, "failed": 1}, "not a clean pass"),
        ("json", {"passed": 1, "errors": 1}, "not a clean pass"),
        ("json", {"passed": 1, "skipped": 1}, "not a clean pass"),
    ],
)
def test_nonclean_result_artifacts_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    kwargs: dict[str, int],
    reason: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    report = Path(
        "reports/result.xml"
        if kind == "junit"
        else "reports/result.json"
    )
    if kind == "junit":
        _write_junit(report, **kwargs)
    else:
        _write_pytest_json(report, **kwargs)

    with pytest.raises(
        ai_release_evidence.AIReleaseEvidenceError,
        match=reason,
    ):
        ai_release_evidence.evidence_record(
            evidence_id="ai-result",
            path=report,
        )


def test_malformed_and_unknown_report_formats_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    malformed_xml = Path("reports/bad.xml")
    malformed_xml.parent.mkdir(parents=True, exist_ok=True)
    malformed_xml.write_text("<not-closed", encoding="utf-8")
    with pytest.raises(
        ai_release_evidence.AIReleaseEvidenceError,
        match="valid XML",
    ):
        ai_release_evidence.evidence_record(
            evidence_id="bad-xml",
            path=malformed_xml,
        )

    malformed_json = Path("reports/bad.json")
    malformed_json.write_text('{"summary":', encoding="utf-8")
    with pytest.raises(
        ai_release_evidence.AIReleaseEvidenceError,
        match="valid JSON",
    ):
        ai_release_evidence.evidence_record(
            evidence_id="bad-json",
            path=malformed_json,
        )

    text_report = Path("reports/raw.txt")
    text_report.write_text("PASS", encoding="utf-8")
    with pytest.raises(
        ai_release_evidence.AIReleaseEvidenceError,
        match="JUnit",
    ):
        ai_release_evidence.evidence_record(
            evidence_id="bad-format",
            path=text_report,
        )


def test_absolute_and_parent_paths_cannot_be_release_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    report = Path("report.xml")
    _write_junit(report)

    with pytest.raises(
        ai_release_evidence.AIReleaseEvidenceError,
        match="repository-relative",
    ):
        ai_release_evidence.evidence_record(
            evidence_id="absolute",
            path=report.resolve(),
        )

    outside = tmp_path.parent / "outside-ai-release-evidence.xml"
    _write_junit(outside)
    with pytest.raises(
        ai_release_evidence.AIReleaseEvidenceError,
        match="canonical",
    ):
        ai_release_evidence.evidence_record(
            evidence_id="parent",
            path=Path("..") / outside.name,
        )
    outside.unlink(missing_ok=True)


def test_collect_rejects_duplicate_evidence_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    first = Path("reports/first.xml")
    second = Path("reports/second.xml")
    _write_junit(first)
    _write_junit(second)

    args = ai_release_evidence.build_parser().parse_args(
        [
            "--record",
            "ai-golden=reports/first.xml",
            "--record",
            "ai-golden=reports/second.xml",
            "--output",
            "out.json",
        ]
    )

    with pytest.raises(
        ai_release_evidence.AIReleaseEvidenceError,
        match="duplicate evidence_id",
    ):
        ai_release_evidence.collect(args)


def test_collect_writes_sorted_release_gate_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    one = Path("reports/one.xml")
    two = Path("reports/two.json")
    _write_junit(one)
    _write_pytest_json(two)

    args = ai_release_evidence.build_parser().parse_args(
        [
            "--record",
            "z-faults=reports/two.json",
            "--record",
            "a-golden=reports/one.xml",
            "--output",
            "evidence/ai-tests.json",
        ]
    )
    assert ai_release_evidence.collect(args) == 0

    payload = json.loads(
        Path("evidence/ai-tests.json").read_text(encoding="utf-8")
    )
    assert [item["evidence_id"] for item in payload] == [
        "a-golden",
        "z-faults",
    ]
    assert all(item["result"] == "pass" for item in payload)



def test_stage7_matrix_mode_emits_only_selected_release_lane(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    release_report = Path("reports/release.xml")
    _write_junit(release_report)
    stage7_report = Path("reports/stage7.xml")
    _write_stage7_junit(stage7_report, prefix="source-a/")

    test_args = ai_release_evidence.build_parser().parse_args(
        [
            "--record",
            "release-tests=reports/release.xml",
            "--stage7-report",
            "reports/stage7.xml",
            "--stage7-lane",
            "test",
            "--output",
            "out/test-evidence.json",
        ]
    )
    assert ai_release_evidence.collect(test_args) == 0
    test_records = json.loads(
        Path("out/test-evidence.json").read_text(encoding="utf-8")
    )
    test_ids = {item["evidence_id"] for item in test_records}
    assert "release-tests" in test_ids
    assert {
        item.evidence_id
        for item in MANDATORY_AI_JOURNEYS
        if item.lane == "test"
    }.issubset(test_ids)
    assert not {
        item.evidence_id
        for item in MANDATORY_AI_JOURNEYS
        if item.lane == "eval"
    }.intersection(test_ids)

    eval_args = ai_release_evidence.build_parser().parse_args(
        [
            "--stage7-report",
            "reports/stage7.xml",
            "--stage7-lane",
            "eval",
            "--output",
            "out/eval-evidence.json",
        ]
    )
    assert ai_release_evidence.collect(eval_args) == 0
    eval_records = json.loads(
        Path("out/eval-evidence.json").read_text(encoding="utf-8")
    )
    assert {item["evidence_id"] for item in eval_records} == {
        item.evidence_id
        for item in MANDATORY_AI_JOURNEYS
        if item.lane == "eval"
    }


def test_stage7_matrix_mode_rejects_missing_required_journey(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    report = Path("reports/stage7.xml")
    omitted = MANDATORY_AI_JOURNEYS[0].nodeid
    _write_stage7_junit(report, omit_nodeid=omitted)
    args = ai_release_evidence.build_parser().parse_args(
        [
            "--stage7-report",
            "reports/stage7.xml",
            "--stage7-lane",
            "eval",
            "--output",
            "out.json",
        ]
    )

    with pytest.raises(
        ai_release_evidence.AIReleaseEvidenceError,
        match="missing required AI journeys",
    ):
        ai_release_evidence.collect(args)


def test_stage7_matrix_mode_rejects_named_journey_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    report = Path("reports/stage7.xml")
    failed = MANDATORY_AI_JOURNEYS[-1].nodeid
    _write_stage7_junit(report, fail_nodeid=failed)
    args = ai_release_evidence.build_parser().parse_args(
        [
            "--stage7-report",
            "reports/stage7.xml",
            "--stage7-lane",
            "eval",
            "--output",
            "out.json",
        ]
    )

    with pytest.raises(
        ai_release_evidence.AIReleaseEvidenceError,
        match="non-passing required AI journeys",
    ):
        ai_release_evidence.collect(args)
