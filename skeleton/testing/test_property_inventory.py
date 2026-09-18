"""Fail-closed classifier tests for the property-test inventory (#969 S081)."""

from __future__ import annotations

from pathlib import Path

import pytest

from skeleton.quality.property_inventory import (
    CONFLICT_DOMAIN,
    CoverageStatus,
    EXCLUDED_OWNERS,
    ISSUE,
    PropertyInventoryError,
    SCHEMA,
    SCHEMA_VERSION,
    SEED,
    SubsystemInvariant,
    TASK_KEY,
    classify_coverage,
    default_catalog,
    detect_property_evidence,
    evidence_covers,
    extract_explicit_covers,
    filename_is_property_suite,
    gaps,
    inventory_property_coverage,
    normalize_status,
    scan_property_evidence,
)


def _invariant(**overrides: object) -> SubsystemInvariant:
    values: dict[str, object] = {
        "invariant_id": "demo.bound",
        "subsystem": "demo",
        "statement": "Demo bound holds for all inputs.",
        "source_path": "skeleton/demo.py",
        "evidence_tokens": ("unique_demo_token_xyz",),
    }
    values.update(overrides)
    return SubsystemInvariant(**values)  # type: ignore[arg-type]


def _write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_schema_and_task_identity_are_stable() -> None:
    report = inventory_property_coverage()
    payload = report.to_payload()
    assert report.schema == SCHEMA == "quality.property_inventory.v1"
    assert report.schema_version == SCHEMA_VERSION == 1
    assert report.task_key == TASK_KEY == "reserve-S081-property-test-inventory"
    assert report.conflict_domain == CONFLICT_DOMAIN == "quality.readonly.property_inventory"
    assert payload["issue"] == ISSUE == "#969"
    assert payload["seed"] == SEED == 17
    assert set(payload) >= {
        "schema",
        "missing_invariant_ids",
        "rows",
        "evidence_paths",
        "covered_count",
        "missing_count",
        "excluded_count",
    }


def test_catalog_ids_are_unique_and_sorted() -> None:
    catalog = default_catalog()
    ids = [row.invariant_id for row in catalog]
    assert ids == sorted(ids)
    assert len(ids) == len(set(ids))
    assert catalog
    owner_issues = {row.owner_issue for row in catalog if row.owner_issue}
    assert owner_issues == set(EXCLUDED_OWNERS)


def test_duplicate_catalog_ids_fail_closed() -> None:
    row = _invariant()
    with pytest.raises(PropertyInventoryError, match="duplicate invariant_id"):
        inventory_property_coverage(catalog=(row, row), evidence=())


def test_empty_or_blank_tokens_fail_closed() -> None:
    with pytest.raises(PropertyInventoryError, match="evidence_tokens"):
        SubsystemInvariant(
            invariant_id="blank.tokens",
            subsystem="demo",
            statement="Blank tokens cannot prove coverage.",
            source_path="skeleton/demo.py",
            evidence_tokens=(),
        )
    with pytest.raises(PropertyInventoryError, match="non-empty strings"):
        SubsystemInvariant(
            invariant_id="whitespace.token",
            subsystem="demo",
            statement="Whitespace tokens cannot prove coverage.",
            source_path="skeleton/demo.py",
            evidence_tokens=("   ",),
        )


def test_probably_covered_and_unknown_labels_are_missing() -> None:
    assert normalize_status("probably_covered") is CoverageStatus.MISSING
    assert normalize_status("probably covered") is CoverageStatus.MISSING
    assert normalize_status("likely") is CoverageStatus.MISSING
    assert normalize_status("inferred") is CoverageStatus.MISSING
    assert normalize_status("ok") is CoverageStatus.MISSING
    assert normalize_status("pass") is CoverageStatus.MISSING
    assert normalize_status(None) is CoverageStatus.MISSING
    assert normalize_status("covered") is CoverageStatus.COVERED
    assert normalize_status("missing") is CoverageStatus.MISSING
    assert normalize_status("excluded") is CoverageStatus.EXCLUDED
    assert normalize_status(CoverageStatus.COVERED) is CoverageStatus.COVERED


def test_example_based_test_is_not_property_evidence() -> None:
    text = (
        "def test_contradictory_hypotheses_fail_closed():\n"
        "    unique_demo_token_xyz = True\n"
        "    assert unique_demo_token_xyz\n"
    )
    evidence = detect_property_evidence("skeleton/testing/test_learning_evidence.py", text)
    assert evidence is None
    row = classify_coverage(_invariant(), ())
    assert row.status is CoverageStatus.MISSING
    assert row.reason == "missing property-test evidence"


def test_token_match_without_property_detector_is_missing(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "skeleton/testing/test_demo.py",
        "def test_example():\n    unique_demo_token_xyz = 1\n    assert unique_demo_token_xyz\n",
    )
    report = inventory_property_coverage(
        repo_root=tmp_path,
        catalog=(_invariant(),),
    )
    assert report.evidence == ()
    assert report.rows[0].status is CoverageStatus.MISSING


def test_properties_filename_with_tokens_is_covered(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "skeleton/testing/test_demo_properties.py",
        "def test_generated_corpus():\n    unique_demo_token_xyz = True\n    assert unique_demo_token_xyz\n",
    )
    report = inventory_property_coverage(
        repo_root=tmp_path,
        catalog=(_invariant(),),
    )
    assert report.rows[0].status is CoverageStatus.COVERED
    assert report.rows[0].evidence_paths == ("skeleton/testing/test_demo_properties.py",)


def test_hypothesis_import_is_property_evidence(tmp_path: Path) -> None:
    # Split the import so this test file itself does not become hypothesis evidence.
    source = "from hypothes" + "is import given\n@giv" + "en()\ndef test_bound():\n    unique_demo_token_xyz = 1\n"
    _write(tmp_path, "tests/test_bound.py", source)
    evidence = scan_property_evidence(tmp_path)
    assert len(evidence) == 1
    assert "hypothesis" in evidence[0].detector
    row = classify_coverage(_invariant(), evidence)
    assert row.status is CoverageStatus.COVERED


def test_explicit_marker_binds_only_listed_invariants() -> None:
    text = (
        "PROPERTY_INVARIANTS = ('demo.bound',)\n"
        "# property-coverage: demo.bound\n"
        "def test_generated():\n    pass\n"
    )
    evidence = detect_property_evidence("tests/test_marked.py", text)
    assert evidence is not None
    assert extract_explicit_covers(text) == ("demo.bound",)
    bound = _invariant()
    sibling = _invariant(
        invariant_id="demo.other",
        evidence_tokens=("demo.bound",),
    )
    assert evidence_covers(bound, evidence) is True
    assert evidence_covers(sibling, evidence) is False
    assert classify_coverage(sibling, (evidence,)).status is CoverageStatus.MISSING


def test_property_file_without_tokens_does_not_cover_sibling() -> None:
    evidence = detect_property_evidence(
        "backend/tests/test_security_middleware_properties.py",
        "def test_generated_request_id_corpus_is_always_bounded_and_header_safe():\n    pass\n",
    )
    assert evidence is not None
    sibling = _invariant(
        invariant_id="security.forwarded_for.parser_fail_safe",
        subsystem="security",
        evidence_tokens=("test_generated_forwarded_chains_fail_safely_without_parser_crashes",),
    )
    assert classify_coverage(sibling, (evidence,)).status is CoverageStatus.MISSING


def test_duplicate_evidence_paths_are_deduped() -> None:
    evidence = detect_property_evidence(
        "skeleton/testing/test_demo_properties.py",
        "unique_demo_token_xyz\n",
    )
    assert evidence is not None
    row = classify_coverage(_invariant(), (evidence, evidence))
    assert row.evidence_paths == ("skeleton/testing/test_demo_properties.py",)
    assert row.status is CoverageStatus.COVERED


def test_unreadable_or_missing_files_are_not_evidence(tmp_path: Path) -> None:
    missing = tmp_path / "skeleton" / "testing" / "test_ghost_properties.py"
    assert detect_property_evidence(missing, None) is None
    empty = detect_property_evidence("skeleton/testing/test_demo_properties.py", "")
    # Filename still fires, but empty haystack cannot satisfy tokens.
    assert empty is not None
    assert classify_coverage(_invariant(), (empty,)).status is CoverageStatus.MISSING

    binary_root = tmp_path / "binary"
    binary = binary_root / "skeleton" / "testing" / "test_binary_properties.py"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"\xff\xfe unique_demo_token_xyz")
    scanned = inventory_property_coverage(
        repo_root=binary_root,
        catalog=(_invariant(),),
    )
    assert scanned.evidence == ()
    assert scanned.rows[0].status is CoverageStatus.MISSING

    report = inventory_property_coverage(
        repo_root=tmp_path / "does-not-exist",
        catalog=(_invariant(),),
        evidence=(),
    )
    assert report.rows[0].status is CoverageStatus.MISSING


def test_inventory_classifier_file_is_never_property_evidence() -> None:
    assert filename_is_property_suite("skeleton/testing/test_property_inventory.py") is False
    planted = detect_property_evidence(
        "skeleton/testing/test_property_inventory.py",
        "from hypothesis import given\nPROPERTY_INVARIANTS = ('demo.bound',)\nunique_demo_token_xyz\n",
    )
    assert planted is None


def test_excluded_owners_are_not_gaps_even_with_tokens() -> None:
    invariant = _invariant(
        invariant_id="quality.replay.tape_integrity",
        subsystem="quality.replay",
        owner_issue="#1030",
        evidence_tokens=("ReplayTape",),
    )
    evidence = detect_property_evidence(
        "skeleton/testing/test_replay_properties.py",
        "ReplayTape\n",
    )
    assert evidence is not None
    row = classify_coverage(invariant, (evidence,))
    assert row.status is CoverageStatus.EXCLUDED
    assert row.evidence_paths == ()
    report = inventory_property_coverage(catalog=(invariant, _invariant()), evidence=(evidence,))
    missing = gaps(report)
    assert [item.invariant.invariant_id for item in missing] == ["demo.bound"]
    assert all(item.status is CoverageStatus.MISSING for item in missing)


def test_excluded_issue_set_matches_seed_boundaries() -> None:
    assert set(EXCLUDED_OWNERS) == {"#1030", "#1039", "#1149"}
    assert "replay quality" in EXCLUDED_OWNERS["#1030"]
    assert "concept-to-release" in EXCLUDED_OWNERS["#1039"]
    assert "mechanics replay" in EXCLUDED_OWNERS["#1149"]


def test_missing_repo_directory_fails_scan() -> None:
    with pytest.raises(PropertyInventoryError, match="not a directory"):
        scan_property_evidence(Path("/tmp/skeleton-property-inventory-missing-root"))


def test_live_repo_inventory_is_fail_closed_and_deduped() -> None:
    report = inventory_property_coverage()
    payload = report.to_payload()
    by_id = {row.invariant.invariant_id: row for row in report.rows}

    assert payload["row_count"] == len(default_catalog())
    security_covered = [
        "security.request_id.bounded_header_safe",
        "security.request_id.duplicate_rejected",
        "security.forwarded_for.parser_fail_safe",
        "security.content_length.bounded_telemetry",
        "security.route_prefix.exact_or_child",
        "security.size_limit.content_length_match",
    ]
    for invariant_id in security_covered:
        row = by_id[invariant_id]
        assert row.status is CoverageStatus.COVERED
        assert row.evidence_paths == ("backend/tests/test_security_middleware_properties.py",)

    missing_ids = {row.invariant.invariant_id for row in gaps(report)}
    assert "swarm.lease_ownership_consistent" in missing_ids
    assert "vault.shamir.threshold_secrecy" in missing_ids
    assert "learning.evidence.contradiction_fail_closed" in missing_ids
    assert "hmac.seal.expiry_rejected" in missing_ids
    assert "game.mechanics.resource_bounds_finite" in missing_ids

    for owner_id, owner_issue in (
        ("quality.replay.tape_integrity", "#1030"),
        ("eval.concept_to_release.missing_unscored", "#1039"),
        ("game.mechanics.replay.deterministic_digests", "#1149"),
    ):
        row = by_id[owner_id]
        assert row.status is CoverageStatus.EXCLUDED
        assert row.invariant.owner_issue == owner_issue
        assert owner_id not in missing_ids

    assert "probably" not in str(payload).lower()
    statuses = {row.status for row in report.rows}
    assert statuses <= {CoverageStatus.COVERED, CoverageStatus.MISSING, CoverageStatus.EXCLUDED}
    evidence_paths = [item.path for item in report.evidence]
    assert evidence_paths == sorted(set(evidence_paths))
    assert "skeleton/testing/test_property_inventory.py" not in evidence_paths
    assert payload["missing_count"] == len(missing_ids)
    assert payload["excluded_count"] == 3
    assert payload["covered_count"] >= 6
