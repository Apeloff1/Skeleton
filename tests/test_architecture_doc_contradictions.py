from __future__ import annotations

from pathlib import Path

from scripts.check_architecture_doc_contradictions import (
    CLAIM_KINDS,
    DISPOSITION_CLASSES,
    DOC_ALLOWLIST,
    ROW_STATUSES,
    classify_disposition,
    collect_claims,
    collect_violations,
    inventory_rows,
    main,
    normalize_repo_keys,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def _write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _docs(root: Path) -> None:
    for relative in DOC_ALLOWLIST:
        _write(root, relative, f"# {relative}\n")


def test_closed_class_sets_are_exclusive() -> None:
    assert len(CLAIM_KINDS) == len(set(CLAIM_KINDS))
    assert len(ROW_STATUSES) == len(set(ROW_STATUSES))
    assert len(DISPOSITION_CLASSES) == len(set(DISPOSITION_CLASSES))
    assert "unknown" in DISPOSITION_CLASSES
    assert "contradicting" in ROW_STATUSES


def test_disposition_unknown_without_evidence() -> None:
    assert classify_disposition("probably fine") == "unknown"
    assert classify_disposition("") == "missing"
    assert classify_disposition("CANONICAL") == "canonical"
    assert classify_disposition("Merged (see below), then archive") == "archive"
    assert classify_disposition("PROMOTE") == "promote"
    assert classify_disposition("Redundant — safe to delete") == "delete"
    assert classify_disposition("Keep as sibling; not in Python spine.") == "sibling"
    assert classify_disposition("Not GameForge. Leave.") == "inspect"


def test_repo_family_cells_split_into_keys() -> None:
    assert normalize_repo_keys("**Skeleton** (canonical)") == ("skeleton",)
    assert "tutolage" in normalize_repo_keys("Tutolage")
    keys = normalize_repo_keys("Interesting-22 / Ieresting-22")
    assert "interesting-22" in keys
    assert "ieresting-22" in keys


def test_missing_allowlisted_doc_fails_closed(tmp_path: Path) -> None:
    _write(tmp_path, "docs/ARCHITECTURE.md", "# arch\n")
    violations = collect_violations(tmp_path)
    assert any("doc-contradiction unreadable missing_doc" in item for item in violations)
    assert any("CANONICAL_MODULE_BOUNDARIES.md" in item for item in violations)


def test_unreadable_doc_fails_closed(tmp_path: Path) -> None:
    _docs(tmp_path)
    blocked = tmp_path / "docs" / "CONSOLIDATION.md"
    blocked.unlink()
    blocked.mkdir()
    violations = collect_violations(tmp_path)
    assert any("doc-contradiction unreadable" in item for item in violations)


def test_unknown_verdict_fails_closed(tmp_path: Path) -> None:
    _docs(tmp_path)
    _write(
        tmp_path,
        "docs/CONSOLIDATION.md",
        """# c
| Repo | Verdict |
| --- | --- |
| Mystery | vibes only |
""",
    )
    violations = collect_violations(tmp_path)
    assert any("doc-contradiction unknown" in item for item in violations)
    assert any("mystery" in item for item in violations)


def test_cross_doc_disposition_collision_is_contradicting(tmp_path: Path) -> None:
    _docs(tmp_path)
    _write(
        tmp_path,
        "docs/CONSOLIDATION.md",
        """# c
| Repo | Verdict |
| --- | --- |
| Tutolage | Merged, then archive |
""",
    )
    _write(
        tmp_path,
        "docs/CONSOLIDATION_MATRIX.md",
        """# m
| Repository family | Initial disposition |
| --- | --- |
| Tutolage | PROMOTE |
""",
    )
    claims, violations = collect_claims(tmp_path)
    assert violations == []
    rows = {row["key"]: row for row in inventory_rows(claims) if row["kind"] == "repo_disposition"}
    assert rows["tutolage"]["status"] == "contradicting"
    assert set(rows["tutolage"]["values"]) == {"archive", "promote"}
    assert collect_violations(tmp_path) == []


def test_matching_dispositions_are_consistent(tmp_path: Path) -> None:
    _docs(tmp_path)
    table = """# c
| Repo | Verdict |
| --- | --- |
| Skeleton | Canonical. Survives. |
"""
    _write(tmp_path, "docs/CONSOLIDATION.md", table)
    _write(
        tmp_path,
        "docs/CONSOLIDATION_MATRIX.md",
        """# m
| Repository family | Initial disposition |
| --- | --- |
| Skeleton | CANONICAL |
""",
    )
    claims, violations = collect_claims(tmp_path)
    assert violations == []
    rows = {row["key"]: row for row in inventory_rows(claims) if row["kind"] == "repo_disposition"}
    assert rows["skeleton"]["status"] == "consistent"
    assert rows["skeleton"]["values"] == ["canonical"]


def test_capability_owner_matrix_is_parsed(tmp_path: Path) -> None:
    _docs(tmp_path)
    _write(
        tmp_path,
        "docs/CANONICAL_MODULE_BOUNDARIES.md",
        """# b
| Capability | Canonical owner | Allowed responsibilities | Must not own |
| --- | --- | --- | --- |
| Kernel primitives | `skeleton/kernel/` | typed errors | HTTP |
""",
    )
    claims, violations = collect_claims(tmp_path)
    assert violations == []
    rows = {
        row["key"]: row
        for row in inventory_rows(claims)
        if row["kind"] == "capability_owner"
    }
    assert rows["kernel primitives"]["status"] == "consistent"
    assert any("skeleton/kernel/" in value for value in rows["kernel primitives"]["values"])


def test_current_repository_inventory_is_closed_and_reports_collisions() -> None:
    claims, read_errors = collect_claims(REPO_ROOT)
    assert read_errors == []
    rows = inventory_rows(claims)
    assert rows
    statuses = {row["status"] for row in rows}
    assert statuses <= set(ROW_STATUSES)
    assert "unknown" not in statuses
    assert "unreadable" not in statuses
    assert collect_violations(REPO_ROOT) == []
    repo_rows = [row for row in rows if row["kind"] == "repo_disposition"]
    assert any(row["status"] == "contradicting" for row in repo_rows)
    keys = {row["key"] for row in repo_rows}
    assert "tutolage" in keys
    assert "skeleton" in keys
    owners = [row for row in rows if row["kind"] == "capability_owner"]
    assert any(row["key"] == "kernel primitives" for row in owners)


def test_scanner_main_exits_zero_on_current_repo(capsys) -> None:
    assert main(["--root", str(REPO_ROOT)]) == 0
    captured = capsys.readouterr()
    assert "Architecture-doc contradiction inventory classified" in captured.out
    assert "doc-contradiction contradicting" in captured.out
