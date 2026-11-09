"""JSON/YAML materialise verification — files + CodeVerifier gate (+ repair)."""
from __future__ import annotations

import json

import pytest

# Import Forge first so forge↔intelligence circular imports resolve.
from skeleton.forge.universal import Forge
from skeleton.kernel.errors import MaterialisationError
from skeleton.organism.quality_state import load_quality


def _bp(tmp_path, name: str = "JsonYamlGate"):
    forge = Forge(root=tmp_path)
    bp = forge.new_blueprint(name)
    forge.instantiate(bp, "player", "player")
    return forge, bp


def test_materialise_json_emits_file_and_accepts(tmp_path):
    forge, bp = _bp(tmp_path, "JsonAccept")
    out = forge.materialise(bp, target="json", repair=False)
    assert out["file_count"] == 1
    assert "JsonAccept.json" in out["files"]
    raw = out["files"]["JsonAccept.json"]
    parsed = json.loads(raw)
    assert parsed["name"] == "JsonAccept"
    assert parsed["blueprint_id"] == bp.blueprint_id
    assert out["verification"]["accepted"] is True
    assert out["verification"]["score"] >= 0.7
    assert out["verification"]["reason"] == "accepted"
    assert out["verification"]["quality"]["metadata"]["target"] == "json"
    assert "verify_loop" not in out
    rows = load_quality(root=tmp_path)
    assert rows and rows[-1]["surface"] == "forge"
    assert rows[-1]["accepted"] is True


def test_materialise_yaml_emits_file_and_accepts(tmp_path):
    forge, bp = _bp(tmp_path, "YamlAccept")
    out = forge.materialise(bp, target="yaml", repair=False)
    assert out["file_count"] == 1
    assert "YamlAccept.yaml" in out["files"]
    text = out["files"]["YamlAccept.yaml"]
    import yaml

    parsed = yaml.safe_load(text)
    assert parsed["name"] == "YamlAccept"
    assert out["verification"]["accepted"] is True
    assert out["verification"]["score"] >= 0.7
    assert out["verification"]["quality"]["metadata"]["target"] == "yaml"
    rows = load_quality(root=tmp_path)
    assert rows and rows[-1]["accepted"] is True


def test_materialise_json_rejects_broken_encode(tmp_path, monkeypatch):
    forge, bp = _bp(tmp_path, "JsonFail")

    def bad_encode(artefact, *, target, name):
        return {f"{name}.json": "{not-valid-json"}

    monkeypatch.setattr(
        "skeleton.forge.structured_verify.encode_structured_files",
        bad_encode,
    )
    # Also patch the import site used inside materialise's else branch.
    monkeypatch.setattr(
        "skeleton.forge.universal.encode_structured_files",
        bad_encode,
        raising=False,
    )
    with pytest.raises(MaterialisationError) as exc:
        forge.materialise(bp, target="json", repair=False)
    assert "json" in str(exc.value).lower() or "failed verification" in str(exc.value)
    assert "verification" in exc.value.context
    assert exc.value.context["verification"]["accepted"] is False
    assert exc.value.context["verification"]["reason"] == "parse_error"
    rows = load_quality(root=tmp_path)
    assert rows and rows[-1]["accepted"] is False


def test_materialise_json_repair_reencodes_until_green(tmp_path, monkeypatch):
    forge, bp = _bp(tmp_path, "JsonRepair")
    calls = {"n": 0}
    real_encode = None

    from skeleton.forge import structured_verify as sv

    real_encode = sv.encode_structured_files

    def flaky_encode(artefact, *, target, name):
        calls["n"] += 1
        if calls["n"] == 1:
            return {f"{name}.json": "{broken"}
        return real_encode(artefact, target=target, name=name)

    monkeypatch.setattr(sv, "encode_structured_files", flaky_encode)
    out = forge.materialise(bp, target="json", repair=True, max_rounds=3)
    assert out["verification"]["accepted"] is True
    assert "verify_loop" in out
    assert out["verify_loop"]["trace"]["rounds"] >= 1
    assert out["files"]["JsonRepair.json"]
    json.loads(out["files"]["JsonRepair.json"])
    assert calls["n"] >= 2
    assert out.get("repairs") or out.get("repair")
