from __future__ import annotations

import json
from pathlib import Path

from scripts.check_asset_budget_schema import (
    AXES,
    COMPLEXITY_UNITS,
    CONFLICT_DOMAIN,
    DIMENSION_UNITS,
    DOCUMENT_FIELDS,
    KINDS,
    SCHEMA_VERSION,
    TASK_ID,
    main,
    validate_asset_budget,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER = REPO_ROOT / "scripts" / "check_asset_budget_schema.py"

CATALOG_IDENTITY_FIELDS = (
    "sha256",
    "content_digest",
    "lineage",
    "license",
    "spdx",
    "origin",
    "rights_holder",
    "duplicates",
    "assets",
)
DISPLAY_BACKEND_FIELDS = (
    "godot",
    "unity",
    "gpu",
    "vulkan",
    "opengl",
    "draw_calls",
    "vram_bytes",
    "shader",
    "mesh_lod",
)


def _axis_memory(**overrides):
    payload = {"bytes": 1_048_576, "evidence_refs": ["assets.spec.budget_evidence:memory"]}
    payload.update(overrides)
    return payload


def _axis_disk(**overrides):
    payload = {"bytes": 262_144, "evidence_refs": ["assets.spec.budget_evidence:disk"]}
    payload.update(overrides)
    return payload


def _axis_dimension(**overrides):
    payload = {
        "width": 512,
        "height": 512,
        "depth": 1,
        "unit": "texel",
        "evidence_refs": ["assets.spec.budget_evidence:dimension"],
    }
    payload.update(overrides)
    return payload


def _axis_duration(**overrides):
    payload = {"milliseconds": 0, "evidence_refs": ["assets.spec.budget_evidence:duration"]}
    payload.update(overrides)
    return payload


def _axis_complexity(**overrides):
    payload = {
        "value": 4096,
        "unit": "element",
        "evidence_refs": ["assets.spec.budget_evidence:complexity"],
    }
    payload.update(overrides)
    return payload


def _doc(**overrides):
    payload = {
        "schema_version": SCHEMA_VERSION,
        "asset_id": "hero-idle-raster",
        "kind": "raster",
        "memory": _axis_memory(),
        "disk": _axis_disk(),
        "dimension": _axis_dimension(),
        "duration": _axis_duration(),
        "complexity": _axis_complexity(),
    }
    payload.update(overrides)
    return payload


def test_schema_identity_is_stable() -> None:
    assert TASK_ID == "reserve-S070-asset-budget-schema"
    assert CONFLICT_DOMAIN == "assets.spec.budget_evidence"
    assert SCHEMA_VERSION == 1
    assert AXES == ("memory", "disk", "dimension", "duration", "complexity")
    assert DOCUMENT_FIELDS == {"schema_version", "asset_id", "kind", *AXES}
    assert KINDS == (
        "raster",
        "audio",
        "video",
        "geometry",
        "animation",
        "volume",
        "document",
    )
    assert DIMENSION_UNITS == ("texel", "sample", "voxel", "pixel")
    assert COMPLEXITY_UNITS == ("primitive", "sample", "element")
    errors = validate_asset_budget(["bad"])
    assert errors and errors[0].startswith("asset-budget ")


def test_schema_is_budget_evidence_not_catalog_identity() -> None:
    for field in CATALOG_IDENTITY_FIELDS:
        assert field not in DOCUMENT_FIELDS
    source = CHECKER.read_text(encoding="utf-8")
    for token in (
        '"sha256"',
        '"content_digest"',
        '"lineage"',
        '"spdx"',
        '"rights_holder"',
        '"duplicates"',
    ):
        assert token not in source
    assert CHECKER.name == "check_asset_budget_schema.py"
    assert (REPO_ROOT / "tests" / "test_asset_budget_schema.py").is_file()


def test_schema_axes_are_backend_neutral() -> None:
    for field in DISPLAY_BACKEND_FIELDS:
        assert field not in DOCUMENT_FIELDS
    source = CHECKER.read_text(encoding="utf-8")
    for token in (
        '"godot"',
        '"unity"',
        '"gpu"',
        '"vulkan"',
        '"opengl"',
        '"draw_calls"',
        '"vram_bytes"',
        '"shader"',
        '"mesh_lod"',
    ):
        assert token not in source


def test_valid_document_has_no_violations() -> None:
    assert validate_asset_budget(_doc()) == []
    assert validate_asset_budget(
        _doc(
            kind="audio",
            asset_id="footstep",
            memory=_axis_memory(bytes=0),
            disk=_axis_disk(bytes=0),
            dimension=_axis_dimension(width=44100, height=2, depth=1, unit="sample"),
            duration=_axis_duration(milliseconds=250),
            complexity=_axis_complexity(value=0, unit="sample"),
        )
    ) == []


def test_all_closed_kinds_are_accepted() -> None:
    for kind in KINDS:
        assert validate_asset_budget(_doc(kind=kind, asset_id=f"{kind}-asset")) == []


def test_unknown_fields_fail_closed() -> None:
    errors = validate_asset_budget(_doc(severity="high", extras=[]))
    assert any("asset-budget unknown field" in item for item in errors)
    assert any("severity" in item for item in errors)
    assert any("extras" in item for item in errors)


def test_catalog_identity_fields_fail_closed() -> None:
    errors = validate_asset_budget(
        _doc(sha256="abc", lineage=[], license="CC0", duplicates=[])
    )
    assert any("asset-budget unknown field" in item for item in errors)
    for field in ("sha256", "lineage", "license", "duplicates"):
        assert any(field in item for item in errors)


def test_display_backend_fields_fail_closed() -> None:
    errors = validate_asset_budget(
        _doc(godot="4.3", gpu="vendor", draw_calls=12, vram_bytes=4096)
    )
    assert any("asset-budget unknown field" in item for item in errors)
    for field in ("godot", "gpu", "draw_calls", "vram_bytes"):
        assert any(field in item for item in errors)


def test_nested_unknown_axis_fields_fail_closed() -> None:
    errors = validate_asset_budget(
        _doc(
            memory=_axis_memory(vram_bytes=2048),
            dimension=_axis_dimension(draw_calls=3),
        )
    )
    unknown = [item for item in errors if "asset-budget unknown field" in item]
    assert any("memory" in item and "vram_bytes" in item for item in unknown)
    assert any("dimension" in item and "draw_calls" in item for item in unknown)


def test_missing_axes_fail_closed() -> None:
    document = _doc()
    del document["memory"]
    del document["complexity"]
    errors = validate_asset_budget(document)
    assert any("asset-budget missing_value field" in item for item in errors)
    assert any("memory" in item for item in errors)
    assert any("complexity" in item for item in errors)


def test_wrong_types_fail_closed() -> None:
    errors = validate_asset_budget(
        _doc(
            schema_version=True,
            memory=_axis_memory(bytes="1024"),
            disk=_axis_disk(bytes=False),
            dimension=_axis_dimension(width=512.5, height=None, depth=True),
            duration=_axis_duration(milliseconds=1.5),
            complexity=_axis_complexity(value=True),
        )
    )
    assert any("asset-budget unknown schema_version" in item for item in errors)
    type_errors = [item for item in errors if "asset-budget unknown type" in item]
    assert len(type_errors) >= 7
    for path in (
        "memory.bytes",
        "disk.bytes",
        "dimension.width",
        "dimension.height",
        "dimension.depth",
        "duration.milliseconds",
        "complexity.value",
    ):
        assert any(path in item for item in type_errors)


def test_negative_values_fail_closed() -> None:
    errors = validate_asset_budget(
        _doc(
            memory=_axis_memory(bytes=-1),
            disk=_axis_disk(bytes=-2),
            dimension=_axis_dimension(width=-3, height=-4, depth=-5),
            duration=_axis_duration(milliseconds=-6),
            complexity=_axis_complexity(value=-7),
        )
    )
    negatives = [item for item in errors if "asset-budget unknown negative" in item]
    assert len(negatives) == 7


def test_unknown_kind_fails_closed() -> None:
    errors = validate_asset_budget(_doc(kind="godot_scene"))
    assert any("asset-budget unknown kind" in item for item in errors)
    assert any("godot_scene" in item for item in errors)


def test_unknown_units_fail_closed() -> None:
    errors = validate_asset_budget(
        _doc(
            dimension=_axis_dimension(unit="ndc"),
            complexity=_axis_complexity(unit="draw_calls"),
        )
    )
    assert any("asset-budget unknown dimension_unit" in item for item in errors)
    assert any("asset-budget unknown complexity_unit" in item for item in errors)
    assert any("ndc" in item for item in errors)
    assert any("draw_calls" in item for item in errors)


def test_missing_and_blank_evidence_fail_closed() -> None:
    empty = validate_asset_budget(_doc(memory=_axis_memory(evidence_refs=[])))
    assert any("asset-budget missing_value evidence_refs" in item for item in empty)
    blank = validate_asset_budget(_doc(disk=_axis_disk(evidence_refs=["", "  "])))
    assert any("asset-budget unknown evidence_ref" in item for item in blank)
    not_list = validate_asset_budget(
        _doc(duration=_axis_duration(evidence_refs="assets.spec.budget_evidence"))
    )
    assert any("asset-budget missing_value evidence_refs" in item for item in not_list)


def test_wrong_schema_version_fails_closed() -> None:
    errors = validate_asset_budget(_doc(schema_version=2))
    assert any("asset-budget unknown schema_version" in item for item in errors)


def test_non_object_root_fails_closed() -> None:
    errors = validate_asset_budget(["not", "an", "object"])
    assert errors == ["asset-budget unknown root_type: asset budget document must be an object"]


def test_blank_asset_id_fails_closed() -> None:
    errors = validate_asset_budget(_doc(asset_id="   "))
    assert any("asset-budget missing_value asset_id" in item for item in errors)


def test_non_object_axis_fails_closed() -> None:
    errors = validate_asset_budget(_doc(memory="huge", dimension=12))
    assert any("asset-budget unknown axis_type" in item for item in errors)
    assert any("memory" in item for item in errors)
    assert any("dimension" in item for item in errors)


def test_cli_accepts_valid_fixture(tmp_path: Path, capsys) -> None:
    path = tmp_path / "asset-budget.json"
    path.write_text(json.dumps(_doc()), encoding="utf-8")
    assert main([str(path)]) == 0
    assert "Asset-budget schema v1 accepted" in capsys.readouterr().out


def test_cli_rejects_invalid_document(tmp_path: Path, capsys) -> None:
    path = tmp_path / "asset-budget.json"
    path.write_text(json.dumps(_doc(memory=_axis_memory(bytes=-1), extra=True)), encoding="utf-8")
    assert main([str(path)]) == 1
    stderr = capsys.readouterr().err
    assert "Asset-budget schema validation failed:" in stderr
    assert "asset-budget unknown negative" in stderr
    assert "asset-budget unknown field" in stderr


def test_cli_rejects_unreadable_json(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not-json", encoding="utf-8")
    try:
        main([str(path)])
    except SystemExit as exc:
        assert "asset-budget unreadable json" in str(exc)
    else:
        raise AssertionError("unreadable JSON must fail closed")


def test_not_wired_into_quality_gates() -> None:
    quality_gates = (REPO_ROOT / "scripts" / "quality-gates.sh").read_text(encoding="utf-8")
    assert "check_asset_budget_schema.py" not in quality_gates
    assert "test_asset_budget_schema.py" not in quality_gates
