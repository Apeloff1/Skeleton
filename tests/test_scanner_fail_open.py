"""Fail-closed regressions for the scanner fail-open inventory (#960 S016)."""

from __future__ import annotations

import ast
import json
from pathlib import Path

from scripts.check_scanner_fail_open import (
    CLASSES,
    CONFLICT_DOMAIN,
    DOCUMENT_FIELDS,
    FINDING_PREFIX,
    GATE_FAIL_CLASSES,
    OBSERVATION_FIELDS,
    SCENARIOS,
    SCHEMA_VERSION,
    SYMLINK_POLICIES,
    TASK_ID,
    classify_document,
    classify_observation,
    main,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check_scanner_fail_open.py"


def _observation(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "scanner": "fixture.zero-file",
        "scenario": "zero_file_success",
        "exit_code": 1,
        "files_expected": 0,
        "files_scanned": 0,
        "timed_out": False,
        "unreadable_subtree": False,
        "nested_symlink": False,
        "symlink_policy": "none",
        "malformed_source": False,
    }
    payload.update(overrides)
    return payload


def _doc(*observations: dict[str, object], **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "observations": list(observations) if observations else [_observation()],
    }
    payload.update(overrides)
    return payload


def test_task_identity_and_closed_classes() -> None:
    assert TASK_ID == "reserve-S016-scanner-fail-open"
    assert CONFLICT_DOMAIN == "security.readonly.scanner_fail_open"
    assert FINDING_PREFIX == "scanner-fail-open"
    assert SCHEMA_VERSION == 1
    assert CLASSES == ("fail_closed", "fail_open", "unknown")
    assert GATE_FAIL_CLASSES == frozenset({"fail_open", "unknown"})
    assert SCENARIOS == (
        "zero_file_success",
        "partial_traversal",
        "unreadable_subtree",
        "nested_symlink",
        "malformed_source",
        "timeout_fail_open",
    )
    assert SYMLINK_POLICIES == ("none", "error", "skip", "follow")
    assert DOCUMENT_FIELDS == {"schema_version", "observations"}
    assert "scanner" in OBSERVATION_FIELDS
    source = SCRIPT.read_text(encoding="utf-8")
    assert "TASK_KEY" not in source
    assert 'TASK_ID = "reserve-S016-scanner-fail-open"' in source


def test_distinct_from_s019_s020_s029_surfaces() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "reserve-S019" not in source
    assert "reserve-S020" not in source
    assert "reserve-S029" not in source
    assert "reachable_http" not in source
    assert "quadratic_nested_walk" not in source
    assert "git_subprocess_per_file" not in source
    for name in ("network", "subprocess", "model APIs", "CVSS", "severity"):
        assert name not in CLASSES
    assert "fail_closed" in CLASSES
    tree = ast.parse(source)
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module.split(".", 1)[0])
    assert "skeleton" not in imported
    assert "pydantic" not in imported
    assert "os" not in imported


def test_zero_file_success_exit_zero_is_fail_open() -> None:
    klass = classify_observation(_observation(exit_code=0, files_expected=4, files_scanned=0))
    assert klass == "fail_open"


def test_zero_file_success_nonzero_exit_is_fail_closed() -> None:
    klass = classify_observation(_observation(exit_code=2, files_expected=0, files_scanned=0))
    assert klass == "fail_closed"


def test_zero_file_success_with_scanned_files_is_unknown() -> None:
    klass = classify_observation(_observation(scenario="zero_file_success", files_scanned=1, files_expected=1))
    assert klass == "unknown"


def test_partial_traversal_success_is_fail_open() -> None:
    klass = classify_observation(
        _observation(
            scanner="fixture.partial",
            scenario="partial_traversal",
            exit_code=0,
            files_expected=10,
            files_scanned=3,
        )
    )
    assert klass == "fail_open"


def test_partial_traversal_nonzero_exit_is_fail_closed() -> None:
    klass = classify_observation(
        _observation(
            scanner="fixture.partial",
            scenario="partial_traversal",
            exit_code=1,
            files_expected=10,
            files_scanned=3,
        )
    )
    assert klass == "fail_closed"


def test_partial_traversal_complete_walk_is_unknown() -> None:
    klass = classify_observation(
        _observation(
            scenario="partial_traversal",
            files_expected=4,
            files_scanned=4,
            exit_code=1,
        )
    )
    assert klass == "unknown"


def test_unreadable_subtree_skip_success_is_fail_open() -> None:
    klass = classify_observation(
        _observation(
            scanner="fixture.unreadable",
            scenario="unreadable_subtree",
            unreadable_subtree=True,
            exit_code=0,
            files_expected=8,
            files_scanned=5,
        )
    )
    assert klass == "fail_open"


def test_unreadable_subtree_error_is_fail_closed() -> None:
    klass = classify_observation(
        _observation(
            scanner="fixture.unreadable",
            scenario="unreadable_subtree",
            unreadable_subtree=True,
            exit_code=1,
            files_expected=8,
            files_scanned=5,
        )
    )
    assert klass == "fail_closed"


def test_nested_symlink_follow_or_skip_success_is_fail_open() -> None:
    follow = classify_observation(
        _observation(
            scanner="fixture.symlink",
            scenario="nested_symlink",
            nested_symlink=True,
            symlink_policy="follow",
            exit_code=0,
            files_expected=6,
            files_scanned=6,
        )
    )
    skip = classify_observation(
        _observation(
            scanner="fixture.symlink",
            scenario="nested_symlink",
            nested_symlink=True,
            symlink_policy="skip",
            exit_code=0,
            files_expected=6,
            files_scanned=4,
        )
    )
    assert follow == "fail_open"
    assert skip == "fail_open"


def test_nested_symlink_error_policy_nonzero_exit_is_fail_closed() -> None:
    klass = classify_observation(
        _observation(
            scanner="fixture.symlink",
            scenario="nested_symlink",
            nested_symlink=True,
            symlink_policy="error",
            exit_code=1,
            files_expected=6,
            files_scanned=2,
        )
    )
    assert klass == "fail_closed"


def test_nested_symlink_policy_mismatch_is_unknown() -> None:
    missing_policy = classify_observation(
        _observation(
            scenario="nested_symlink",
            nested_symlink=True,
            symlink_policy="none",
            exit_code=1,
        )
    )
    leftover_policy = classify_observation(
        _observation(
            scenario="zero_file_success",
            nested_symlink=False,
            symlink_policy="follow",
            exit_code=1,
        )
    )
    assert missing_policy == "unknown"
    assert leftover_policy == "unknown"


def test_malformed_source_skip_success_is_fail_open() -> None:
    klass = classify_observation(
        _observation(
            scanner="fixture.malformed",
            scenario="malformed_source",
            malformed_source=True,
            exit_code=0,
            files_expected=3,
            files_scanned=3,
        )
    )
    assert klass == "fail_open"


def test_malformed_source_nonzero_exit_is_fail_closed() -> None:
    klass = classify_observation(
        _observation(
            scanner="fixture.malformed",
            scenario="malformed_source",
            malformed_source=True,
            exit_code=3,
            files_expected=3,
            files_scanned=2,
        )
    )
    assert klass == "fail_closed"


def test_timeout_exit_zero_is_fail_open() -> None:
    klass = classify_observation(
        _observation(
            scanner="fixture.timeout",
            scenario="timeout_fail_open",
            timed_out=True,
            exit_code=0,
            files_expected=20,
            files_scanned=7,
        )
    )
    assert klass == "fail_open"


def test_timeout_nonzero_exit_is_fail_closed() -> None:
    klass = classify_observation(
        _observation(
            scanner="fixture.timeout",
            scenario="timeout_fail_open",
            timed_out=True,
            exit_code=124,
            files_expected=20,
            files_scanned=7,
        )
    )
    assert klass == "fail_closed"


def test_timeout_without_timeout_flag_is_unknown() -> None:
    klass = classify_observation(
        _observation(scenario="timeout_fail_open", timed_out=False, exit_code=1)
    )
    assert klass == "unknown"


def test_unknown_fields_types_and_root_fail_closed() -> None:
    assert classify_observation(["not", "an", "object"]) == "unknown"
    assert classify_observation(_observation(severity="high")) == "unknown"
    assert classify_observation(_observation(exit_code=True)) == "unknown"
    assert classify_observation(_observation(files_scanned=-1)) == "unknown"
    assert classify_observation(_observation(files_scanned=5, files_expected=2)) == "unknown"
    assert classify_observation(_observation(scanner="")) == "unknown"
    assert classify_observation(_observation(scenario="capability_inventory")) == "unknown"
    missing = _observation()
    del missing["exit_code"]
    assert classify_observation(missing) == "unknown"


def test_all_fail_closed_fixture_passes_gate() -> None:
    rows, errors = classify_document(
        _doc(
            _observation(scanner="a", scenario="zero_file_success", exit_code=1),
            _observation(
                scanner="b",
                scenario="partial_traversal",
                files_expected=4,
                files_scanned=1,
                exit_code=2,
            ),
            _observation(
                scanner="c",
                scenario="unreadable_subtree",
                unreadable_subtree=True,
                files_expected=4,
                files_scanned=1,
                exit_code=1,
            ),
            _observation(
                scanner="d",
                scenario="nested_symlink",
                nested_symlink=True,
                symlink_policy="error",
                files_expected=4,
                files_scanned=1,
                exit_code=1,
            ),
            _observation(
                scanner="e",
                scenario="malformed_source",
                malformed_source=True,
                files_expected=2,
                files_scanned=1,
                exit_code=1,
            ),
            _observation(
                scanner="f",
                scenario="timeout_fail_open",
                timed_out=True,
                files_expected=9,
                files_scanned=2,
                exit_code=124,
            ),
        )
    )
    assert errors == []
    assert [row["class"] for row in rows] == ["fail_closed"] * 6


def test_fail_open_and_unknown_rows_fail_the_gate() -> None:
    rows, errors = classify_document(
        _doc(
            _observation(scanner="open", exit_code=0),
            _observation(scanner="mystery", scenario="not-a-scenario", exit_code=1),
        )
    )
    assert rows[0]["class"] == "fail_open"
    assert rows[1]["class"] == "unknown"
    assert any(item.startswith("scanner-fail-open fail_open:") for item in errors)
    assert any(item.startswith("scanner-fail-open unknown:") for item in errors)


def test_empty_observations_and_unknown_document_fields_fail_closed() -> None:
    empty_rows, empty_errors = classify_document(_doc(observations=[]))
    assert empty_rows == []
    assert any("scanner-fail-open unknown empty_observations" in item for item in empty_errors)
    extra_rows, extra_errors = classify_document(_doc(timing_ms=12))
    assert extra_rows
    assert any("scanner-fail-open unknown field" in item for item in extra_errors)
    assert any("timing_ms" in item for item in extra_errors)
    root_errors = classify_document(["nope"])[1]
    assert root_errors == ["scanner-fail-open unknown root_type: document must be an object"]
    version_errors = classify_document(_doc(schema_version=2))[1]
    assert any("scanner-fail-open unknown schema_version" in item for item in version_errors)


def test_cli_accepts_all_fail_closed_fixture(tmp_path: Path, capsys) -> None:
    path = tmp_path / "scanner-fail-open.json"
    path.write_text(json.dumps(_doc(_observation(exit_code=1))), encoding="utf-8")
    assert main([str(path)]) == 0
    assert "fail_closed=1" in capsys.readouterr().out


def test_cli_rejects_fail_open_fixture(tmp_path: Path, capsys) -> None:
    path = tmp_path / "scanner-fail-open.json"
    path.write_text(json.dumps(_doc(_observation(exit_code=0))), encoding="utf-8")
    assert main([str(path)]) == 1
    captured = capsys.readouterr()
    assert "Scanner fail-open inventory failed:" in captured.err
    assert "scanner-fail-open fail_open:" in captured.err


def test_cli_rejects_unreadable_json(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not-json", encoding="utf-8")
    try:
        main([str(path)])
    except SystemExit as exc:
        assert "scanner-fail-open unreadable json" in str(exc)
    else:
        raise AssertionError("unreadable JSON must fail closed")


def test_classifier_does_not_read_live_scanners(tmp_path: Path, monkeypatch) -> None:
    live = REPO_ROOT / "scripts" / "check_repository_python_sast.py"
    assert live.is_file()
    original = Path.read_text

    def guarded(self: Path, *args: object, **kwargs: object) -> str:
        resolved = self.resolve()
        if resolved == live.resolve():
            raise AssertionError("classifier must not open live scanners")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded)
    observation = _observation(
        scanner=str(live),
        scenario="malformed_source",
        malformed_source=True,
        exit_code=1,
        files_expected=2,
        files_scanned=1,
    )
    assert classify_observation(observation) == "fail_closed"
    fixture = tmp_path / "only-fixture.json"
    fixture.write_text(json.dumps(_doc(observation)), encoding="utf-8")
    assert main([str(fixture)]) == 0


def test_not_wired_into_quality_gates() -> None:
    quality_gates = (REPO_ROOT / "scripts" / "quality-gates.sh").read_text(encoding="utf-8")
    assert "check_scanner_fail_open.py" not in quality_gates
    assert "test_scanner_fail_open.py" not in quality_gates
