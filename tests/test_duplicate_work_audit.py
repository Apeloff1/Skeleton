"""Fail-closed regressions for the duplicate-work PR-cluster audit (#969 S009)."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.check_duplicate_work_audit import (
    AUTO_CLOSE,
    CLASSES,
    CONFLICT_DOMAIN,
    DEFAULT_FIXTURE,
    MUTATION_ACTIONS,
    TASK_ID,
    basename_overlap_is_not_a_cluster,
    classify_document,
    classify_prs,
    main,
    parse_pr,
    parse_title_refs,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check_duplicate_work_audit.py"


def _pr(
    number: int,
    title: str,
    head: str,
    files: list[str],
    state: str = "open",
) -> dict[str, object]:
    return {
        "number": number,
        "title": title,
        "head": head,
        "files": files,
        "state": state,
    }


def _classes(rows: list) -> dict[int, str]:
    return {int(row.number): row.classification for row in rows}


def test_task_identity_is_stable_and_distinct_from_s097() -> None:
    assert TASK_ID == "reserve-S009-duplicate-work-audit"
    assert CONFLICT_DOMAIN == "repo.readonly.duplicate_work"
    assert TASK_ID != "reserve-S097-legacy-duplicate-inventory"
    assert CONFLICT_DOMAIN != "consolidation.readonly.duplicate_inventory"
    assert CLASSES == ("unique", "duplicate", "superseded", "unknown")
    assert len(CLASSES) == len(set(CLASSES))
    assert "canonical" not in CLASSES
    assert "overlapping" not in CLASSES
    assert AUTO_CLOSE is False
    assert MUTATION_ACTIONS == ()


def test_unique_identity_is_not_clustered() -> None:
    rows, errors = classify_prs(
        [
            _pr(1, "Queue schema", "cursor/queue", ["scripts/a.py"]),
            _pr(2, "Run state", "cursor/runs", ["scripts/b.py"]),
        ]
    )
    assert errors == []
    assert _classes(rows) == {1: "unique", 2: "unique"}


def test_same_head_is_explicit_duplicate_cluster() -> None:
    rows, errors = classify_prs(
        [
            _pr(11, "First take", "cursor/same-head", ["scripts/a.py"]),
            _pr(12, "Retry", "cursor/same-head", ["scripts/a.py", "tests/t.py"]),
        ]
    )
    assert errors == []
    assert _classes(rows) == {11: "unique", 12: "duplicate"}
    assert rows[0].cluster_id == rows[1].cluster_id == "cluster:11"
    assert any(item.startswith("same_head:") for item in rows[1].evidence)


def test_same_title_and_files_is_explicit_duplicate_cluster() -> None:
    files = ["scripts/check_hot_path_inventory.py", "tests/test_hot_path_inventory.py"]
    rows, errors = classify_prs(
        [
            _pr(21, "Fail-closed hot-path evidence inventory", "cursor/hot-a", files),
            _pr(22, "Fail-closed hot-path evidence inventory", "cursor/hot-b", files),
        ]
    )
    assert errors == []
    assert _classes(rows) == {21: "unique", 22: "duplicate"}
    assert any(item.startswith("same_title_and_files:") for item in rows[1].evidence)


def test_basename_overlap_alone_is_not_a_cluster() -> None:
    left = ["scripts/check_architecture_boundaries.py"]
    right = ["backend/scripts/check_architecture_boundaries.py"]
    assert basename_overlap_is_not_a_cluster(left, right)
    rows, errors = classify_prs(
        [
            _pr(31, "Architecture boundary gate", "cursor/arch-scripts", left),
            _pr(32, "Backend architecture boundary scanner", "cursor/arch-backend", right),
        ]
    )
    assert errors == []
    assert _classes(rows) == {31: "unique", 32: "unique"}
    assert rows[0].cluster_id != rows[1].cluster_id


def test_partial_file_overlap_without_title_or_head_is_unique() -> None:
    rows, errors = classify_prs(
        [
            _pr(
                41,
                "Capability inventory",
                "cursor/capability",
                ["scripts/check_capability_inventory.py", "tests/test_capability.py"],
            ),
            _pr(
                42,
                "Security priority inventory",
                "cursor/security",
                ["scripts/check_capability_inventory.py", "scripts/check_security.py"],
            ),
        ]
    )
    assert errors == []
    assert _classes(rows) == {41: "unique", 42: "unique"}


def test_identical_files_without_title_or_head_match_are_unique() -> None:
    files = ["scripts/shared.py", "tests/test_shared.py"]
    rows, errors = classify_prs(
        [
            _pr(51, "Morning summary schema", "cursor/morning-a", files),
            _pr(52, "Morning handoff skeleton", "cursor/morning-b", files),
        ]
    )
    assert errors == []
    assert _classes(rows) == {51: "unique", 52: "unique"}


def test_title_only_similarity_is_not_a_cluster() -> None:
    rows, errors = classify_prs(
        [
            _pr(61, "Fail-closed inventory", "cursor/one", ["scripts/a.py"]),
            _pr(62, "Fail-closed inventory extra", "cursor/two", ["scripts/b.py"]),
        ]
    )
    assert errors == []
    assert _classes(rows) == {61: "unique", 62: "unique"}


def test_explicit_supersedes_title_ref() -> None:
    rows, errors = classify_prs(
        [
            _pr(71, "Seed 05 first pass", "cursor/first", ["scripts/a.py"], "closed"),
            _pr(
                72,
                "supersedes #71 Seed 05 second pass",
                "cursor/second",
                ["scripts/a.py", "tests/t.py"],
            ),
        ]
    )
    assert errors == []
    assert _classes(rows) == {71: "superseded", 72: "unique"}
    assert any("title_ref:supersede:72->71" in item for item in rows[0].evidence)


def test_duplicate_of_title_ref() -> None:
    rows, errors = classify_prs(
        [
            _pr(81, "Original work", "cursor/orig", ["scripts/a.py"]),
            _pr(82, "duplicate of #81 retry", "cursor/retry", ["tests/t.py"]),
        ]
    )
    assert errors == []
    assert _classes(rows) == {81: "unique", 82: "duplicate"}


def test_merged_member_supersedes_later_open_in_same_identity() -> None:
    files = ["scripts/check_scan_performance_inventory.py"]
    rows, errors = classify_prs(
        [
            _pr(91, "Scan performance audit", "cursor/scan-a", files, "merged"),
            _pr(92, "Scan performance audit", "cursor/scan-b", files, "open"),
        ]
    )
    assert errors == []
    assert _classes(rows) == {91: "unique", 92: "superseded"}


def test_unresolvable_title_ref_is_unknown_fail_closed() -> None:
    rows, errors = classify_prs(
        [_pr(100, "supersedes #9999 missing target", "cursor/x", ["scripts/a.py"])]
    )
    assert rows[0].classification == "unknown"
    assert any("duplicate-work unknown unclassified" in item for item in errors)
    assert any("9999" in item for item in errors)


def test_unknown_state_fails_closed() -> None:
    parsed = parse_pr(_pr(5, "Hello", "cursor/x", ["a.py"], "draft"), index=0)
    assert parsed.parse_error
    rows, errors = classify_prs([_pr(5, "Hello", "cursor/x", ["a.py"], "draft")])
    assert rows[0].classification == "unknown"
    assert errors


def test_unknown_fields_and_missing_fields_fail_closed() -> None:
    extra, extra_errors = classify_prs(
        [{**_pr(6, "Hello", "cursor/x", ["a.py"]), "notes": "nope"}]
    )
    assert extra[0].classification == "unknown"
    assert extra_errors
    missing, missing_errors = classify_prs([{"number": 7, "title": "Hello"}])
    assert missing[0].classification == "unknown"
    assert missing_errors


def test_non_object_row_and_repeat_number_fail_closed() -> None:
    rows, errors = classify_prs(
        [
            ["not", "an", "object"],
            _pr(8, "Hello", "cursor/x", ["a.py"]),
            _pr(8, "Hello again", "cursor/y", ["b.py"]),
        ]
    )
    classes = [row.classification for row in rows]
    assert classes[0] == "unknown"
    assert classes[2] == "unknown"
    assert any("repeats" in item for item in errors)


def test_title_refs_require_keyword_not_bare_issue_number() -> None:
    assert parse_title_refs("Seed 05 (#501) follow-up") == ()
    assert parse_title_refs("supersedes #501 Seed 05") == (("supersede", 501),)
    assert parse_title_refs("replaces #12 and duplicate of #13") == (
        ("replace", 12),
        ("duplicate", 13),
    )


def test_document_unknown_rows_are_violations() -> None:
    rows, errors = classify_document(
        {"schema_version": 1, "prs": [{"status": "open"}]}
    )
    assert rows[0].classification == "unknown"
    assert any("duplicate-work unknown unclassified" in item for item in errors)


def test_valid_document_classifies_without_violations() -> None:
    rows, errors = classify_document(
        {
            "schema_version": 1,
            "prs": [
                _pr(1, "Queue schema", "cursor/queue", ["scripts/a.py"]),
                _pr(2, "Retry", "cursor/queue", ["scripts/a.py"]),
                _pr(3, "Landed", "cursor/scan-a", ["scripts/s.py"], "merged"),
                _pr(4, "Landed", "cursor/scan-b", ["scripts/s.py"]),
            ],
        }
    )
    assert errors == []
    assert _classes(rows) == {1: "unique", 2: "duplicate", 3: "unique", 4: "superseded"}


def test_default_fixture_is_closed() -> None:
    document = json.loads(DEFAULT_FIXTURE.read_text(encoding="utf-8"))
    rows, errors = classify_document(document)
    assert errors == []
    classes = _classes(rows)
    assert classes[101] == "unique"
    assert classes[202] == "duplicate"
    assert classes[302] == "duplicate"
    assert classes[401] == "unique"
    assert classes[402] == "unique"
    assert classes[501] == "superseded"
    assert classes[602] == "superseded"
    assert "unknown" not in set(classes.values())
    assert any(row.classification == "duplicate" for row in rows)
    assert any(row.classification == "superseded" for row in rows)


def test_cli_accepts_shipped_fixture(capsys) -> None:
    assert main([]) == 0
    output = capsys.readouterr().out
    assert "unique=" in output
    assert "duplicate=" in output
    assert "superseded=" in output
    assert "unknown=0" in output
    assert "auto_close=false" in output
    assert TASK_ID in output


def test_cli_accepts_valid_fixture(tmp_path: Path, capsys) -> None:
    path = tmp_path / "prs.json"
    path.write_text(
        json.dumps({"schema_version": 1, "prs": [_pr(1, "Only", "cursor/only", ["a.py"])]}),
        encoding="utf-8",
    )
    assert main([str(path)]) == 0
    assert "unique=1" in capsys.readouterr().out


def test_cli_rejects_unknown_prs(tmp_path: Path) -> None:
    path = tmp_path / "prs.json"
    path.write_text(
        json.dumps({"schema_version": 1, "prs": [_pr(1, "Nope", "cursor/x", ["a.py"], "mystery")]}),
        encoding="utf-8",
    )
    assert main([str(path)]) == 1


def test_cli_json_report_keeps_auto_close_false(tmp_path: Path, capsys) -> None:
    path = tmp_path / "prs.json"
    path.write_text(
        json.dumps({"schema_version": 1, "prs": [_pr(1, "Only", "cursor/only", ["a.py"])]}),
        encoding="utf-8",
    )
    assert main([str(path), "--json"]) == 0
    stdout = capsys.readouterr().out
    payload = json.loads(stdout[stdout.index("{") :])
    assert payload["auto_close"] is False
    assert payload["mutations"] == []
    assert payload["task_key"] == TASK_ID
    assert payload["conflict_domain"] == CONFLICT_DOMAIN
    assert payload["unknown_count"] == 0


def test_checker_does_not_auto_close_or_mutate() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    lowered = source.lower()
    assert "gh pr close" not in lowered
    assert "gh api" not in lowered
    assert "subprocess" not in source
    assert "urllib" not in source
    assert "never closes" in lowered
    assert "auto_close = false" in lowered
    assert TASK_ID in source
    assert "reserve-S097-legacy-duplicate-inventory" in source
