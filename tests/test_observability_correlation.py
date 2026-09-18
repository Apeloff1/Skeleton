"""Fail-closed regressions for the observability correlation audit (#969 S085)."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.check_observability_correlation import (
    CLASSES,
    CONFLICT_DOMAIN,
    DOCUMENT_FIELDS,
    HOP_FIELDS,
    PATH_CLASSES,
    SCHEMA_VERSION,
    TASK_ID,
    canonical_correlation_id,
    classify_correlation,
    classify_hop,
    main,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check_observability_correlation.py"
CORRELATED_ID = "run-9e904bb3-s085"


def _hop(path_class: str, surface: str, correlation_id: str | None = CORRELATED_ID) -> dict[str, object]:
    return {
        "path_class": path_class,
        "surface": surface,
        "correlation_id": correlation_id,
    }


def _complete_hops(correlation_id: str | None = CORRELATED_ID) -> list[dict[str, object]]:
    return [
        _hop("api", "skeleton/api/routes.py", correlation_id),
        _hop("runtime", "core/shift_supervisor/shift_manager.py", correlation_id),
        _hop("agent", "skeleton/automation/night_shift.py", correlation_id),
        _hop("tool", "scripts/quality-gates.sh", correlation_id),
        _hop("storage", "backend/core/content_store.py", correlation_id),
        _hop("evidence", "docs/OBSERVABILITY.md", correlation_id),
    ]


def _doc(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "correlation_id": CORRELATED_ID,
        "hops": _complete_hops(),
    }
    payload.update(overrides)
    return payload


def test_task_identity_and_closed_classes() -> None:
    assert TASK_ID == "reserve-S085-correlation-audit"
    assert CONFLICT_DOMAIN == "observability.readonly.correlation"
    assert SCHEMA_VERSION == 1
    assert CLASSES == ("correlated", "gap", "unknown")
    assert PATH_CLASSES == ("api", "runtime", "agent", "tool", "storage", "evidence")
    assert DOCUMENT_FIELDS == {"schema_version", "correlation_id", "hops"}
    assert HOP_FIELDS == {"path_class", "surface", "correlation_id"}
    source = SCRIPT.read_text(encoding="utf-8")
    assert "TASK_KEY" not in source
    assert 'TASK_ID = "reserve-S085-correlation-audit"' in source


def test_full_coverage_correlated_document_is_accepted() -> None:
    report = classify_correlation(_doc())
    assert report.errors == ()
    assert report.counts == {"correlated": 6, "gap": 0, "unknown": 0}
    assert {hop.path_class for hop in report.hops} == set(PATH_CLASSES)


def test_missing_hop_id_is_gap_not_correlated() -> None:
    hops = _complete_hops()
    hops[0]["correlation_id"] = None
    report = classify_correlation(_doc(hops=hops))
    assert report.hops[0].classification == "gap"
    assert all(hop.classification == "correlated" for hop in report.hops[1:])
    assert any("observability-correlation gap hop" in item for item in report.errors)
    assert report.hops[0].classification != "correlated"


def test_mismatched_hop_id_is_gap() -> None:
    hops = _complete_hops()
    hops[3]["correlation_id"] = "other-correlation-zzzz"
    report = classify_correlation(_doc(hops=hops))
    assert report.hops[3].classification == "gap"
    assert any("observability-correlation gap hop" in item for item in report.errors)


def test_unknown_path_class_fails_closed() -> None:
    hops = _complete_hops()
    hops[1]["path_class"] = "logs"
    report = classify_correlation(_doc(hops=hops))
    assert report.hops[1].classification == "unknown"
    assert any("observability-correlation unknown path_class" in item for item in report.errors)
    assert "correlated" not in {report.hops[1].classification}


def test_unknown_fields_and_missing_fields_fail_closed() -> None:
    extra = classify_correlation(_doc(severity="high"))
    assert any("observability-correlation unknown field" in item for item in extra.errors)
    missing = classify_correlation({"schema_version": 1, "hops": _complete_hops()})
    assert any("observability-correlation missing_value field" in item for item in missing.errors)
    hop_extra = _complete_hops()
    hop_extra[0]["owner"] = "night"
    extra_hop = classify_correlation(_doc(hops=hop_extra))
    assert extra_hop.hops[0].classification == "unknown"
    assert any("observability-correlation unknown field" in item for item in extra_hop.errors)


def test_malformed_correlation_ids_fail_closed() -> None:
    assert canonical_correlation_id("short") is None
    assert canonical_correlation_id("run-9e904bb3-s085") == "run-9e904bb3-s085"
    assert canonical_correlation_id(12) is None
    report = classify_correlation(_doc(correlation_id="nope"))
    assert any("observability-correlation unknown correlation_id" in item for item in report.errors)
    hops = _complete_hops()
    hops[2]["correlation_id"] = "???"
    hop_report = classify_correlation(_doc(hops=hops))
    assert hop_report.hops[2].classification == "unknown"


def test_incomplete_path_coverage_fails_closed() -> None:
    hops = _complete_hops()[:-1]
    report = classify_correlation(_doc(hops=hops))
    assert any("observability-correlation unknown path_class_coverage" in item for item in report.errors)
    assert "evidence" in " ".join(report.errors)


def test_duplicate_path_class_fails_closed() -> None:
    hops = _complete_hops()
    hops[5] = _hop("api", "skeleton/api/health.py")
    report = classify_correlation(_doc(hops=hops))
    assert any("observability-correlation unknown duplicate_path_class" in item for item in report.errors)


def test_non_object_root_and_hop_fail_closed() -> None:
    root = classify_correlation(["not", "an", "object"])
    assert root.errors == (
        "observability-correlation unknown root_type: correlation document must be an object",
    )
    hop, errors = classify_hop(["x"], document_id=CORRELATED_ID, index=0)
    assert hop.classification == "unknown"
    assert errors[0].startswith("observability-correlation unknown hop_type")


def test_bad_surface_is_unknown() -> None:
    hops = _complete_hops()
    hops[0]["surface"] = "../secret"
    report = classify_correlation(_doc(hops=hops))
    assert report.hops[0].classification == "unknown"
    assert any("observability-correlation unknown surface" in item for item in report.errors)


def test_wrong_schema_version_fails_closed() -> None:
    report = classify_correlation(_doc(schema_version=2))
    assert any("observability-correlation unknown schema_version" in item for item in report.errors)


def test_empty_hops_fail_closed() -> None:
    report = classify_correlation(_doc(hops=[]))
    assert any("observability-correlation unknown hops_empty" in item for item in report.errors)


def test_cli_accepts_correlated_fixture(tmp_path: Path, capsys) -> None:
    path = tmp_path / "ok.json"
    path.write_text(json.dumps(_doc()), encoding="utf-8")
    assert main([str(path)]) == 0
    out = capsys.readouterr().out
    assert "Observability correlation: correlated=6, gap=0, unknown=0" in out


def test_cli_rejects_unknown_path_class(tmp_path: Path, capsys) -> None:
    hops = _complete_hops()
    hops[0]["path_class"] = "guessed_vibe"
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(_doc(hops=hops)), encoding="utf-8")
    assert main([str(path)]) == 1
    err = capsys.readouterr().err
    assert "Observability correlation failed:" in err
    assert "observability-correlation unknown path_class" in err


def test_cli_rejects_unreadable_json(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not-json", encoding="utf-8")
    try:
        main([str(path)])
    except SystemExit as exc:
        assert "observability-correlation unreadable json" in str(exc)
    else:
        raise AssertionError("unreadable JSON must fail closed")


def test_not_wired_into_quality_gates() -> None:
    quality_gates = (REPO_ROOT / "scripts" / "quality-gates.sh").read_text(encoding="utf-8")
    assert "check_observability_correlation.py" not in quality_gates
    assert "test_observability_correlation.py" not in quality_gates
