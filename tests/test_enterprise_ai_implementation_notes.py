from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_enterprise_ai_implementation_notes",
    ROOT / "scripts" / "check_enterprise_ai_implementation_notes.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _fixture(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    index = _load(ROOT / "machine/enterprise_ai_implementation_notes_index.json")
    paths = {
        "machine/ai_master_plan.json",
        "machine/enterprise_ai_superiority.json",
        "machine/enterprise_ai_implementation_notes_index.json",
    }
    paths.update(row["path"] for row in index["dossier_files"])
    paths.update(row["human_path"] for row in index["dossier_files"])
    paths.add(index["authority"]["human_index"])
    for relative in sorted(paths):
        source = ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return root


def _first_dossier_file(root: Path) -> tuple[Path, dict]:
    index = _load(root / "machine/enterprise_ai_implementation_notes_index.json")
    path = root / index["dossier_files"][0]["path"]
    return path, _load(path)


def test_canonical_construction_requires_enterprise_gates() -> None:
    construction = _load(ROOT / "machine/ai_app_construction.json")
    gates = {
        row["id"]: row
        for row in construction["acceptance_gates"]
    }

    assert gates["enterprise-ai-superiority"] == {
        "id": "enterprise-ai-superiority",
        "kind": "static",
        "command": "python scripts/check_enterprise_ai_superiority.py --json",
        "required": True,
    }
    assert gates["enterprise-ai-implementation-notes"] == {
        "id": "enterprise-ai-implementation-notes",
        "kind": "static",
        "command": "python scripts/check_enterprise_ai_implementation_notes.py --json",
        "required": True,
    }


def test_current_october_2026_implementation_dossiers_are_complete() -> None:
    result = MODULE.validate(ROOT)

    assert result["status"] == "valid"
    assert result["standard_version"] == "2026.10"
    assert result["volume_count"] == 421
    assert result["dossier_count"] == 421
    assert result["depth_pass_count"] == 11
    assert result["required_level_count"] == 14
    assert result["required_section_count"] == 6
    assert result["deep_level_contract_count"] == 421 * 14
    assert result["deep_section_instance_count"] == 421 * 14 * 6
    assert result["all_421_volumes_have_deep_implementation_notes"] is True


def test_every_dossier_has_all_14_deep_levels() -> None:
    index = _load(ROOT / "machine/enterprise_ai_implementation_notes_index.json")
    expected = [f"L{index:02d}" for index in range(14)]
    seen: set[str] = set()

    for file_entry in index["dossier_files"]:
        payload = _load(ROOT / file_entry["path"])
        for dossier in payload["dossiers"]:
            assert dossier["volume_ref"] not in seen
            seen.add(dossier["volume_ref"])
            levels = dossier["implementation_levels"]
            assert [row["id"] for row in levels] == expected
            for level in levels:
                assert len(level["implementation_notes"]) >= 2
                assert len(level["acceptance"]) >= 2
                assert sum(map(len, level["implementation_notes"])) >= 120
                assert sum(map(len, level["acceptance"])) >= 80
                for section in (
                    "design_invariants",
                    "failure_modes",
                    "telemetry_and_slos",
                    "required_evidence",
                ):
                    assert len(level[section]) >= 2
                    assert sum(map(len, level[section])) >= 80

    assert seen == {f"VOL-{index:03d}" for index in range(421)}


def test_dossiers_bind_actual_masterplan_implementation_context() -> None:
    index = _load(ROOT / "machine/enterprise_ai_implementation_notes_index.json")
    master = _load(ROOT / "machine/ai_master_plan.json")
    volumes = {row["key"]: row for row in master["volumes"]}

    for file_entry in index["dossier_files"]:
        payload = _load(ROOT / file_entry["path"])
        for dossier in payload["dossiers"]:
            volume = volumes[dossier["volume_ref"]]
            summary = dossier["implementation_summary"]
            assert summary["requirements"] == volume.get("requirements", [])[:4]
            assert summary["capabilities"] == volume.get("capabilities", [])[:4]
            assert summary["contracts"] == volume.get("contracts", [])[:6]
            assert summary["canonical_paths"] == volume.get(
                "implementation_paths", []
            )[:8]
            assert summary["risks"] == volume.get("risks", [])[:4]
            assert summary["gaps"] == volume.get("gaps", [])[:4]
            assert summary["tests"] == volume.get("tests", [])[:8]
            assert summary["evaluations"] == volume.get("evaluations", [])[:6]
            assert summary["existing_evidence"] == volume.get("evidence", [])[:8]


def test_rejects_missing_volume_dossier(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    path, payload = _first_dossier_file(root)
    payload["dossiers"].pop()
    payload["volume_count"] = len(payload["dossiers"])
    _write(path, payload)

    with pytest.raises(
        MODULE.ImplementationNotesError,
        match="dossier coverage mismatch",
    ):
        MODULE.validate(root)


def test_rejects_duplicate_volume_dossier(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    path, payload = _first_dossier_file(root)
    payload["dossiers"][1]["volume_ref"] = payload["dossiers"][0]["volume_ref"]
    _write(path, payload)

    with pytest.raises(
        MODULE.ImplementationNotesError,
        match="duplicate dossier volume",
    ):
        MODULE.validate(root)


def test_rejects_shallow_implementation_level(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    path, payload = _first_dossier_file(root)
    level = payload["dossiers"][0]["implementation_levels"][4]
    level["implementation_notes"] = ["short", "also short"]
    _write(path, payload)

    with pytest.raises(
        MODULE.ImplementationNotesError,
        match="implementation notes are too shallow",
    ):
        MODULE.validate(root)


def test_rejects_missing_deep_level_section(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    path, payload = _first_dossier_file(root)
    payload["dossiers"][0]["implementation_levels"][7].pop(
        "telemetry_and_slos"
    )
    _write(path, payload)

    with pytest.raises(
        MODULE.ImplementationNotesError,
        match="telemetry_and_slos",
    ):
        MODULE.validate(root)


def test_rejects_missing_level_semantics(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    path, payload = _first_dossier_file(root)
    level = payload["dossiers"][0]["implementation_levels"][3]
    level["implementation_notes"] = [
        "A deliberately generic admission note with enough length to pass the "
        "surface depth check but without the required protected-work concepts.",
        "Another deliberately generic sentence about starting work safely and "
        "consistently while avoiding every required identity-related keyword.",
    ]
    level["acceptance"] = [
        "Generic acceptance text confirms deterministic behavior without "
        "describing the protected admission envelope or its required fields.",
        "Generic negative behavior remains safe and bounded in this fixture.",
    ]
    level["design_invariants"] = [
        "Generic invariant one is intentionally verbose but semantically empty "
        "for the admission layer under test.",
        "Generic invariant two likewise avoids the mandatory admission concepts.",
    ]
    level["failure_modes"] = [
        "Generic failure behavior is deterministic and bounded for this fixture.",
        "Generic failure behavior produces no side effect in this fixture.",
    ]
    level["telemetry_and_slos"] = [
        "generic_admission_metric_one remains observable at qualification",
        "generic_admission_metric_two remains observable at qualification",
    ]
    level["required_evidence"] = [
        "generic deterministic admission evidence bundle",
        "generic exact-head admission verifier receipt",
    ]
    _write(path, payload)

    with pytest.raises(
        MODULE.ImplementationNotesError,
        match="missing semantic concept",
    ):
        MODULE.validate(root)


def test_rejects_placeholder_implementation_text(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    path, payload = _first_dossier_file(root)
    payload["dossiers"][0]["implementation_levels"][1][
        "implementation_notes"
    ][0] = "TODO: fill later with architecture details"
    _write(path, payload)

    with pytest.raises(
        MODULE.ImplementationNotesError,
        match="placeholder text",
    ):
        MODULE.validate(root)


def test_rejects_enterprise_grade_drift(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    path, payload = _first_dossier_file(root)
    payload["dossiers"][0]["enterprise_grade_state"] = "superior"
    _write(path, payload)

    with pytest.raises(
        MODULE.ImplementationNotesError,
        match="enterprise grade state drift",
    ):
        MODULE.validate(root)


def test_rejects_masterplan_requirement_drift(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    master_path = root / "machine/ai_master_plan.json"
    master = _load(master_path)
    master["volumes"][0]["requirements"][0] += " changed"
    _write(master_path, master)

    with pytest.raises(
        MODULE.ImplementationNotesError,
        match="requirements is stale versus masterplan",
    ):
        MODULE.validate(root)


def test_rejects_wrong_depth_pass_placement(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    path, payload = _first_dossier_file(root)
    payload["dossiers"][0]["depth_pass"] = "DP-999-999"
    _write(path, payload)

    with pytest.raises(
        MODULE.ImplementationNotesError,
        match="depth-pass drift",
    ):
        MODULE.validate(root)


def test_rejects_dossier_generated_for_old_masterplan_version(
    tmp_path: Path,
) -> None:
    root = _fixture(tmp_path)
    path, payload = _first_dossier_file(root)
    payload["generated_from_master_plan"] = "old"
    _write(path, payload)

    with pytest.raises(
        MODULE.ImplementationNotesError,
        match="master-plan version drift",
    ):
        MODULE.validate(root)


def test_rejects_semantically_hollow_level(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    path, payload = _first_dossier_file(root)
    level = payload["dossiers"][0]["implementation_levels"][7]
    level["implementation_notes"] = [
        "This implementation has extensive controls and detailed procedures "
        "for operational quality, consistency, safety and correctness.",
        "The subsystem documents behavior, dependencies, ownership and "
        "acceptance expectations with sufficient narrative depth.",
    ]
    level["acceptance"] = [
        "The implementation is reviewed in CI and produces deterministic "
        "results for its declared operating envelope.",
        "Operators can inspect its state and verify completion using the "
        "normal release workflow and evidence package.",
    ]
    _write(path, payload)

    with pytest.raises(
        MODULE.ImplementationNotesError,
        match="missing required concept family",
    ):
        MODULE.validate(root)


def test_rejects_missing_october_2026_non_negotiable(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    path = root / "machine/enterprise_ai_implementation_notes_index.json"
    payload = _load(path)
    payload["october_2026_non_negotiables"] = [
        (
            "Performance claims require representative workloads and "
            "resource-pressure evidence."
            if "p95/p99" in row
            else row
        )
        for row in payload["october_2026_non_negotiables"]
    ]
    _write(path, payload)

    with pytest.raises(
        MODULE.ImplementationNotesError,
        match="p95/p99",
    ):
        MODULE.validate(root)
