from __future__ import annotations

import json
from pathlib import Path

from scripts.check_conflict_heatmap import (
    CLASSES,
    CONFLICT_DOMAIN,
    DOCUMENT_FIELDS,
    SCHEMA_VERSION,
    SURFACE_FIELDS,
    TASK_KEY,
    canonical_write_path,
    classify_heatmap,
    classify_surface,
    derive_conflict_cell,
    lookup_cell,
    main,
    parse_utc,
    squad_may_enter,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _surface(path: str = "skeleton/api/routes.py", pr=12, updated: str = "2026-09-18T09:00:00Z"):
    return {"path": path, "pr": pr, "updated": updated}


def _doc(**overrides):
    payload = {
        "schema_version": SCHEMA_VERSION,
        "as_of": "2026-09-18T10:00:00Z",
        "busy_window_seconds": 86400,
        "surfaces": [
            _surface(),
            _surface(path="docs/OBSERVABILITY.md", pr=None, updated="2026-08-01T00:00:00Z"),
        ],
    }
    payload.update(overrides)
    return payload


def test_closed_class_set_and_seed_identity() -> None:
    assert CLASSES == ("busy", "idle", "unknown")
    assert len(CLASSES) == len(set(CLASSES))
    assert TASK_KEY == "reserve-S495-conflict-heatmap"
    assert CONFLICT_DOMAIN == "ops.readonly.conflict_heatmap"
    assert DOCUMENT_FIELDS == {"schema_version", "as_of", "busy_window_seconds", "surfaces"}
    assert SURFACE_FIELDS == {"path", "pr", "updated"}
    source = (REPO_ROOT / "scripts" / "check_conflict_heatmap.py").read_text(encoding="utf-8")
    assert "conflict-heatmap" in source
    assert "retryable" not in source
    assert "authoritative_failure" not in source
    assert "saturation-metrics" not in source
    assert "morning-handoff" not in source
    assert "queue-report" not in source


def test_two_segment_path_derivation_matches_supervisor_cells() -> None:
    assert derive_conflict_cell("skeleton/api/routes.py") == "skeleton/api"
    assert derive_conflict_cell("scripts/quality-gates.sh") == "scripts/quality-gates.sh"
    assert derive_conflict_cell("README.md") == "README.md"


def test_recent_pr_is_busy_and_blocks_another_squad() -> None:
    report = classify_heatmap(_doc(surfaces=[_surface()]))
    assert report.errors == ()
    assert report.surfaces[0].classification == "busy"
    assert report.cells[0].key == "skeleton/api"
    assert report.cells[0].classification == "busy"
    assert report.cells[0].prs == (12,)
    assert squad_may_enter("busy") is False


def test_stale_or_unowned_writes_are_idle() -> None:
    stale = classify_heatmap(
        _doc(
            surfaces=[
                _surface(updated="2026-09-01T00:00:00Z"),
                _surface(path="core/shift_supervisor/squads.py", pr=None, updated="2026-09-18T09:30:00Z"),
            ]
        )
    )
    assert stale.errors == ()
    assert [row.classification for row in stale.surfaces] == ["idle", "idle"]
    assert {cell.classification for cell in stale.cells} == {"idle"}
    assert squad_may_enter("idle") is True


def test_unknown_rows_and_cells_fail_closed() -> None:
    report = classify_heatmap(
        _doc(
            surfaces=[
                {"path": "../secret", "pr": 1, "updated": "2026-09-18T09:00:00Z"},
                {"path": "skeleton/api/routes.py", "pr": "12", "updated": "2026-09-18T09:00:00Z"},
                {"path": "skeleton/api/x.py", "pr": 4, "updated": "yesterday"},
                {"path": "skeleton/api/y.py", "pr": True, "updated": "2026-09-18T09:00:00Z"},
                {"path": "/abs/path.py", "pr": 8, "updated": "2026-09-18T09:00:00Z"},
                {"path": "ok.py", "pr": 9, "updated": "2026-09-18T09:00:00Z", "owner": "night"},
            ]
        )
    )
    assert all(row.classification == "unknown" for row in report.surfaces)
    assert report.errors
    assert any("conflict-heatmap unknown path" in item for item in report.errors)
    assert any("conflict-heatmap unknown pr" in item for item in report.errors)
    assert any("conflict-heatmap unknown updated" in item for item in report.errors)
    assert any("conflict-heatmap unknown field" in item for item in report.errors)
    assert any("conflict-heatmap unknown cell" in item for item in report.errors)
    assert squad_may_enter("unknown") is False


def test_future_and_non_utc_stamps_fail_closed() -> None:
    future = classify_heatmap(_doc(surfaces=[_surface(updated="2026-09-18T11:00:00Z")]))
    assert future.surfaces[0].classification == "unknown"
    assert any("conflict-heatmap unknown future_write" in item for item in future.errors)

    naive = classify_heatmap(_doc(surfaces=[_surface(updated="2026-09-18T09:00:00")]))
    assert naive.surfaces[0].classification == "unknown"
    offset = classify_heatmap(_doc(surfaces=[_surface(updated="2026-09-18T09:00:00-05:00")]))
    assert offset.surfaces[0].classification == "unknown"
    assert parse_utc("2026-09-18T09:00:00+00:00") is not None
    assert parse_utc("nope") is None


def test_unknown_dominates_busy_on_the_same_cell() -> None:
    report = classify_heatmap(
        _doc(
            surfaces=[
                _surface(path="skeleton/api/a.py", pr=11),
                _surface(path="skeleton/api/b.py", pr=-3),
            ]
        )
    )
    cell = report.cells[0]
    assert cell.key == "skeleton/api"
    assert cell.classification == "unknown"
    assert any("conflict-heatmap unknown cell" in item for item in report.errors)
    assert lookup_cell(report, "skeleton/api/c.py") == "unknown"
    assert squad_may_enter(lookup_cell(report, "skeleton/api/c.py")) is False


def test_busy_sibling_makes_the_whole_cell_too_busy() -> None:
    report = classify_heatmap(
        _doc(
            surfaces=[
                _surface(path="backend/core/http_errors.py", pr=44, updated="2026-09-18T09:50:00Z"),
                _surface(path="backend/core/config.py", pr=None, updated="2026-09-01T00:00:00Z"),
            ]
        )
    )
    assert report.errors == ()
    assert report.cells[0].key == "backend/core"
    assert report.cells[0].classification == "busy"
    assert report.cells[0].prs == (44,)
    assert lookup_cell(report, "backend/core/auth.py") == "busy"
    assert squad_may_enter(lookup_cell(report, "backend/core/auth.py")) is False


def test_two_segment_files_do_not_share_a_parent_cell() -> None:
    report = classify_heatmap(
        _doc(
            surfaces=[
                _surface(path="scripts/check_foo.py", pr=44, updated="2026-09-18T09:50:00Z"),
                _surface(path="scripts/check_bar.py", pr=None, updated="2026-09-01T00:00:00Z"),
            ]
        )
    )
    assert report.errors == ()
    by_key = {cell.key: cell.classification for cell in report.cells}
    assert by_key == {
        "scripts/check_foo.py": "busy",
        "scripts/check_bar.py": "idle",
    }
    assert squad_may_enter(lookup_cell(report, "scripts/check_bar.py")) is True
    assert squad_may_enter(lookup_cell(report, "scripts/check_foo.py")) is False
    assert lookup_cell(report, "scripts/check_baz.py") == "unknown"


def test_unobserved_path_is_unknown_not_idle() -> None:
    report = classify_heatmap(_doc(surfaces=[_surface()]))
    assert lookup_cell(report, "docs/OBSERVABILITY.md") == "unknown"
    assert lookup_cell(report, "../escape") == "unknown"
    assert lookup_cell(report, ["not", "a", "path"]) == "unknown"
    assert canonical_write_path("backend/core/x.py") == "backend/core/x.py"
    assert canonical_write_path("backend//core/x.py") is None


def test_document_unknowns_fail_closed() -> None:
    errors = classify_heatmap(["not", "an", "object"]).errors
    assert errors == ("conflict-heatmap unknown root_type: conflict heatmap document must be an object",)

    missing = classify_heatmap({"schema_version": 1, "surfaces": []})
    assert any("conflict-heatmap missing_value field" in item for item in missing.errors)
    extra = classify_heatmap(_doc(severity="high"))
    assert any("conflict-heatmap unknown field" in item for item in extra.errors)
    version = classify_heatmap(_doc(schema_version=2))
    assert any("conflict-heatmap unknown schema_version" in item for item in version.errors)
    window = classify_heatmap(_doc(busy_window_seconds=True))
    assert any("conflict-heatmap unknown window" in item for item in window.errors)
    negative = classify_heatmap(_doc(busy_window_seconds=-1))
    assert any("conflict-heatmap unknown window" in item for item in negative.errors)


def test_empty_fixture_has_no_cells_and_no_violations() -> None:
    report = classify_heatmap(_doc(surfaces=[]))
    assert report.errors == ()
    assert report.cells == ()
    assert report.counts == {"busy": 0, "idle": 0, "unknown": 0}


def test_window_boundary_is_busy_and_one_second_past_is_idle() -> None:
    on_edge = classify_heatmap(
        _doc(
            as_of="2026-09-18T10:00:00Z",
            busy_window_seconds=3600,
            surfaces=[_surface(updated="2026-09-18T09:00:00Z")],
        )
    )
    assert on_edge.surfaces[0].classification == "busy"
    past = classify_heatmap(
        _doc(
            as_of="2026-09-18T10:00:00Z",
            busy_window_seconds=3600,
            surfaces=[_surface(updated="2026-09-18T08:59:59Z")],
        )
    )
    assert past.surfaces[0].classification == "idle"


def test_cli_accepts_idle_and_busy_fixture(tmp_path: Path, capsys) -> None:
    path = tmp_path / "heatmap.json"
    path.write_text(json.dumps(_doc()), encoding="utf-8")
    assert main([str(path)]) == 0
    out = capsys.readouterr().out
    assert "Conflict heatmap:" in out
    assert "busy=1" in out
    assert "idle=1" in out
    assert "unknown=0" in out
    assert "skeleton/api  busy" in out


def test_cli_rejects_unknown_surfaces(tmp_path: Path, capsys) -> None:
    path = tmp_path / "heatmap.json"
    path.write_text(json.dumps(_doc(surfaces=[{"path": "..", "pr": 1, "updated": "nope"}])), encoding="utf-8")
    assert main([str(path)]) == 1
    err = capsys.readouterr().err
    assert "Conflict heatmap failed:" in err
    assert "conflict-heatmap unknown" in err


def test_cli_rejects_unreadable_json(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not-json", encoding="utf-8")
    try:
        main([str(path)])
    except SystemExit as exc:
        assert "conflict-heatmap unreadable json" in str(exc)
    else:
        raise AssertionError("unreadable JSON must fail closed")


def test_single_surface_helper_unknown_on_non_object() -> None:
    row, errors = classify_surface(["x"], as_of=None, window_seconds=1, index=0)
    assert row.classification == "unknown"
    assert errors[0].startswith("conflict-heatmap unknown surface_type")


def test_not_wired_into_quality_gates() -> None:
    quality_gates = (REPO_ROOT / "scripts" / "quality-gates.sh").read_text(encoding="utf-8")
    assert "check_conflict_heatmap.py" not in quality_gates
    assert "test_conflict_heatmap.py" not in quality_gates
