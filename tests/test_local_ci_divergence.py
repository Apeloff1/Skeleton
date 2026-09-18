"""Fail-closed regressions for local-vs-GitHub CI command divergence (#967 S442)."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path
from unittest import mock

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_local_ci_divergence.py"
SPEC = importlib.util.spec_from_file_location("check_local_ci_divergence", SCRIPT)
assert SPEC and SPEC.loader
audit = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = audit
SPEC.loader.exec_module(audit)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _pair(local: object, ci: object, documented: object) -> dict[str, object]:
    return {
        "local_command": local,
        "ci_command": ci,
        "documented": documented,
    }


def _document(pairs: list[object], *, schema_version: int = 1) -> dict[str, object]:
    return {"schema_version": schema_version, "pairs": pairs}


def _classes(rows: tuple[object, ...]) -> list[str]:
    return [row.classification for row in rows]


def test_task_identity_is_stable_and_never_uses_task_key() -> None:
    assert audit.TASK_ID == "reserve-S442-local-ci-divergence"
    assert audit.CONFLICT_DOMAIN == "build.readonly.ci_parity"
    assert audit.FINDING_PREFIX == "local-ci-divergence"
    assert "TASK_KEY" not in vars(audit)
    assert audit.CLASSES == (
        "matching",
        "intentional_divergence",
        "undocumented_divergence",
        "unknown",
    )


def test_distinct_from_s026_hidden_network_and_s101_developer_setup() -> None:
    assert audit.TASK_ID != "reserve-S026-build-network-audit"
    assert audit.TASK_ID != "reserve-S101-developer-setup-audit"
    assert audit.CONFLICT_DOMAIN != "build.readonly.network_dependencies"
    assert audit.CONFLICT_DOMAIN != "dx.readonly.setup_audit"
    assert not (audit.S026_CLASSES & audit.CLASS_SET)
    assert not (audit.S101_CLASSES & audit.CLASS_SET)
    source = SCRIPT.read_text(encoding="utf-8")
    assert "network-required" not in audit.CLASS_SET
    assert "REWRITE_WORKFLOWS = False" in source
    assert "check_hidden" not in source
    assert "check_developer_setup" not in source


def test_identical_commands_are_matching() -> None:
    row = audit.classify_pair(
        _pair("python -m pytest tests/test_foo.py", "python -m pytest tests/test_foo.py", False),
        index=0,
    )
    assert row.classification == "matching"
    assert row.evidence == ("commands_match",)
    assert row.finding.startswith("local-ci-divergence matching:")
    assert row.classification not in audit.FAIL_CLOSED_CLASSES


def test_quoted_and_whitespace_equivalent_commands_match() -> None:
    row = audit.classify_pair(
        _pair(
            "python  -m   pytest 'tests/test_foo.py'",
            'python -m pytest "tests/test_foo.py"',
            False,
        ),
        index=3,
    )
    assert row.classification == "matching"
    assert row.local_tokens == ("python", "-m", "pytest", "tests/test_foo.py")
    assert row.ci_tokens == row.local_tokens


def test_matching_even_when_documented_true() -> None:
    row = audit.classify_pair(
        _pair("ruff check .", "ruff check .", True),
        index=0,
    )
    assert row.classification == "matching"


def test_documented_flag_difference_is_intentional() -> None:
    row = audit.classify_pair(
        _pair(
            "python -m ruff check . --output-format=github",
            "ruff check . --output-format=github",
            True,
        ),
        index=1,
    )
    assert row.classification == "intentional_divergence"
    assert "documented_true" in row.evidence
    assert row.finding.startswith("local-ci-divergence intentional_divergence:")
    assert row.classification not in audit.FAIL_CLOSED_CLASSES


def test_undocumented_flag_difference_fails_closed() -> None:
    row = audit.classify_pair(
        _pair("python -m pytest tests/test_foo.py", "python -m pytest -q tests/test_foo.py", False),
        index=2,
    )
    assert row.classification == "undocumented_divergence"
    assert "documented_false" in row.evidence
    assert row.finding.startswith("local-ci-divergence undocumented_divergence:")
    assert row.classification in audit.FAIL_CLOSED_CLASSES


def test_env_prefix_and_python_vs_python3_are_divergences() -> None:
    env_row = audit.classify_pair(
        _pair(
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --noconftest tests/a.py",
            "python -m pytest -q --noconftest tests/a.py",
            False,
        ),
        index=0,
    )
    py_row = audit.classify_pair(
        _pair("python scripts/check_x.py", "python3 scripts/check_x.py", False),
        index=1,
    )
    assert env_row.classification == "undocumented_divergence"
    assert py_row.classification == "undocumented_divergence"


def test_missing_fields_and_unknown_fields_are_unknown() -> None:
    missing = audit.classify_pair({"local_command": "pytest", "ci_command": "pytest"}, index=0)
    extra = audit.classify_pair(
        {
            "local_command": "pytest",
            "ci_command": "pytest",
            "documented": True,
            "network": "offline",
        },
        index=1,
    )
    assert missing.classification == "unknown"
    assert "missing fields: documented" in missing.finding
    assert extra.classification == "unknown"
    assert "unknown fields: network" in extra.finding
    assert missing.finding.startswith("local-ci-divergence unknown:")


def test_non_boolean_documented_and_empty_commands_are_unknown() -> None:
    not_bool = audit.classify_pair(
        _pair("pytest", "pytest", "intentional because CI uses -q"),
        index=0,
    )
    empty = audit.classify_pair(_pair("   ", "", False), index=1)
    nulls = audit.classify_pair(_pair(None, None, False), index=2)
    assert _classes((not_bool, empty, nulls)) == ["unknown", "unknown", "unknown"]
    assert "documented must be a boolean" in not_bool.finding
    assert "local_command is not a tokenizable non-empty string" in empty.finding


def test_unclosed_quotes_and_non_object_rows_are_unknown() -> None:
    quoted = audit.classify_pair(_pair('pytest "unterminated', "pytest foo", False), index=0)
    scalar = audit.classify_pair("python -m pytest", index=1)
    assert quoted.classification == "unknown"
    assert scalar.classification == "unknown"
    assert "pair must be an object" in scalar.finding


def test_empty_pair_list_and_non_list_pairs_fail_closed() -> None:
    empty_rows, empty_findings = audit.classify_document(_document([]))
    bad_rows = audit.classify_pairs({"local_command": "pytest"})
    assert empty_rows[0].classification == "unknown"
    assert any("zero pairs classified" in item for item in empty_findings)
    assert not audit.is_closed(empty_rows, empty_findings)
    assert bad_rows[0].classification == "unknown"
    assert "pairs must be a list" in bad_rows[0].finding


def test_closed_fixture_of_matching_and_intentional_pairs() -> None:
    document = _document(
        [
            _pair("python -m pytest tests/a.py", "python -m pytest tests/a.py", False),
            _pair("python -m ruff check .", "ruff check .", True),
        ]
    )
    rows, findings = audit.classify_document(document)
    assert _classes(rows) == ["matching", "intentional_divergence"]
    assert findings == ()
    assert audit.is_closed(rows, findings)
    report = audit.report_from_rows(rows, findings)
    assert report["task_id"] == audit.TASK_ID
    assert "task_key" not in report
    assert report["closed"] is True
    assert report["rewrite_workflows"] is False
    assert report["mutations"] == []


def test_mixed_batch_fails_closed_on_undocumented_or_unknown() -> None:
    document = _document(
        [
            _pair("pytest tests/a.py", "pytest tests/a.py", False),
            _pair("pytest tests/a.py", "pytest -q tests/a.py", False),
            {"local_command": "pytest"},
        ]
    )
    rows, findings = audit.classify_document(document)
    assert "matching" in _classes(rows)
    assert "undocumented_divergence" in _classes(rows)
    assert "unknown" in _classes(rows)
    assert not audit.is_closed(rows, findings)
    assert any(item.startswith("local-ci-divergence undocumented_divergence:") for item in findings)
    assert any(item.startswith("local-ci-divergence unknown:") for item in findings)


def test_unknown_document_schema_fails_closed() -> None:
    document = {
        "schema_version": 2,
        "pairs": [_pair("pytest", "pytest", True)],
        "rewrite": True,
    }
    rows, findings = audit.classify_document(document)
    assert not audit.is_closed(rows, findings)
    joined = " ".join(findings)
    assert "schema_version must be exactly 1" in joined
    assert "unknown fields: rewrite" in joined
    scalar_rows, scalar_findings = audit.classify_document(["not", "an", "object"])
    assert scalar_rows[0].classification == "unknown"
    assert not audit.is_closed(scalar_rows, scalar_findings)


def test_json_report_is_stable_and_uses_task_id() -> None:
    rows, findings = audit.classify_document(
        _document([_pair("make test", "make test", False)])
    )
    payload = audit.report_from_rows(rows, findings)
    encoded = json.dumps(payload, sort_keys=True)
    assert encoded == json.dumps(json.loads(encoded), sort_keys=True)
    assert payload["task_id"] == "reserve-S442-local-ci-divergence"
    assert payload["conflict_domain"] == "build.readonly.ci_parity"
    assert payload["finding_prefix"] == "local-ci-divergence"
    assert "task_key" not in encoded
    for record in payload["records"]:
        assert record["class"] in audit.CLASS_SET
        assert record["finding"].startswith("local-ci-divergence ")


def test_cli_accepts_closed_fixture(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "pairs.json"
    path.write_text(
        json.dumps(
            _document(
                [
                    _pair("python -m pytest tests/a.py", "python -m pytest tests/a.py", False),
                    _pair("yarn --cwd frontend lint:ci", "yarn --cwd frontend lint --max-warnings=0", True),
                ]
            )
        ),
        encoding="utf-8",
    )
    assert audit.main([str(path), "--json"]) == 0
    out = capsys.readouterr().out
    assert "task_id=reserve-S442-local-ci-divergence" in out
    report = json.loads(out[out.index("{") :])
    assert report["closed"] is True
    assert report["task_id"] == audit.TASK_ID
    assert "task_key" not in report


def test_cli_rejects_undocumented_and_missing_fixture(tmp_path: Path) -> None:
    path = tmp_path / "open.json"
    path.write_text(
        json.dumps(_document([_pair("pytest tests/a.py", "pytest -q tests/a.py", False)])),
        encoding="utf-8",
    )
    with mock.patch("sys.stderr", new=io.StringIO()) as stderr:
        assert audit.main([str(path)]) == 1
        assert "local-ci-divergence undocumented_divergence:" in stderr.getvalue()
    with mock.patch("sys.stderr", new=io.StringIO()) as stderr:
        assert audit.main([str(tmp_path / "missing.json")]) == 1
        assert "local-ci-divergence unknown:" in stderr.getvalue()
        assert "fixture missing" in stderr.getvalue()


def test_unreadable_and_invalid_json_fixtures_fail_closed(tmp_path: Path) -> None:
    binary = tmp_path / "binary.json"
    binary.write_bytes(b"\xff\xfe not utf-8 \x80")
    with pytest.raises(audit.LocalCiDivergenceError) as unread:
        audit.load_document(binary)
    assert "local-ci-divergence unknown:" in str(unread.value)

    invalid = tmp_path / "invalid.json"
    invalid.write_text("{not json", encoding="utf-8")
    with pytest.raises(audit.LocalCiDivergenceError) as bad_json:
        audit.load_document(invalid)
    assert "invalid JSON" in str(bad_json.value)

    with mock.patch("sys.stderr", new=io.StringIO()) as stderr:
        assert audit.main([]) == 1
        assert "fixture path is required" in stderr.getvalue()
        assert "rewrite" in stderr.getvalue()


def test_does_not_rewrite_workflows_or_scan_s026_s101_surfaces() -> None:
    assert audit.REWRITE_WORKFLOWS is False
    assert audit.MUTATION_ACTIONS == ()
    source = SCRIPT.read_text(encoding="utf-8")
    assert ".github/workflows" not in source
    assert "quality-gates.sh" not in source
    assert "README.md" not in source
    assert "AGENTS.md" not in source
    workflow = REPO_ROOT / ".github" / "workflows" / "backend-quality.yml"
    assert workflow.is_file()
    # The audit must not mutate workflow text; the live file remains untouched.
    before = workflow.read_bytes()
    rows, findings = audit.classify_document(
        _document([_pair("python scripts/check_x.py", "python scripts/check_x.py", False)])
    )
    assert audit.is_closed(rows, findings)
    assert workflow.read_bytes() == before


def test_tokenize_command_rejects_non_strings() -> None:
    assert audit.tokenize_command("pytest -q tests/a.py") == ("pytest", "-q", "tests/a.py")
    assert audit.tokenize_command("") is None
    assert audit.tokenize_command(True) is None
    assert audit.tokenize_command(["pytest"]) is None
