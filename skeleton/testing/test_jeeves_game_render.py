"""Concrete early/fixed/programmable reference rendering via existing Jeeves engine."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from skeleton.developer.game_cli import run_game_cli
from skeleton.jeeves.game_console_assets import decode_png


def workspace(tmp_path):
    root = tmp_path / "reference-game"
    assert run_game_cli(["init", "reference-game", "--dir", str(tmp_path)])["ok"]
    return root


def scene(root):
    scene = {
        "schema": "skeleton.game.reference_scene.v1",
        "width": 64, "height": 48, "near": 0.1, "far": 20,
        "fov_y_deg": 70,
        "triangles": [{
            "object_id": "original-three-dimensional-art",
            "material": 1, "shader": "fixed", "shader_phase": 0,
            "vertices": [[-0.8, -0.7, 2.0], [0.8, -0.7, 2.0],
                         [0.0, 0.9, 2.0]],
        }],
    }
    path = root / "design" / "reference_scene.json"
    path.write_text(json.dumps(scene), encoding="utf-8")
    return path


@pytest.mark.parametrize("console,pipeline", [
    ("dos_pc", "software_painter"),
    ("ps1", "fixed_function"),
    ("ps2", "programmable"),
])
def test_original_scene_renders_actual_reference_pixels(tmp_path, console, pipeline):
    root = workspace(tmp_path)
    source = scene(root)
    args = ["jeeves", "render-reference", "--project", str(root),
            "--target", console, "--source", "design/reference_scene.json",
            "--output", "assets/3d_preview.png"]
    planned = run_game_cli(args + ["--dry-run"])
    assert planned["ok"], planned
    assert not (root / "assets" / "3d_preview.png").exists()
    rendered = run_game_cli(args)
    assert rendered["ok"], rendered
    assert rendered["pipeline"] == pipeline
    assert rendered["measured_reference_render"] is True
    assert rendered["rasterized_triangles"] > 0
    assert rendered["covered_pixels"] > 0
    assert rendered["console_hardware_fidelity_qualified"] is False
    assert rendered["production_qualified"] is False
    w, h, rgba = decode_png((root / "assets" / "3d_preview.png").read_bytes())
    assert (w, h) == (64, 48)
    assert any(x for i, x in enumerate(rgba) if i % 4 != 3)
    assert source.is_file()
    assert not run_game_cli(args)["ok"]


def test_unsupported_2d_or_modern_hardware_does_not_pretend_to_rasterize(tmp_path):
    root = workspace(tmp_path)
    scene(root)
    for console in ("nes", "ps5", "fictional_console"):
        result = run_game_cli([
            "jeeves", "render-reference", "--project", str(root),
            "--target", console, "--source", "design/reference_scene.json",
            "--output", "assets/frame.png",
        ])
        assert not result["ok"]
        assert not (root / "assets" / "frame.png").exists()


@pytest.mark.parametrize("mutate", [
    lambda data: data.update({"triangles": []}),
    lambda data: data["triangles"][0].update({"shader": ["unsafe"]}),
    lambda data: data["triangles"][0].update({"material": -1}),
    lambda data: data["triangles"][0].update({"vertices": [[0, 0, 1]]}),
    lambda data: data.update({"width": 9999}),
    lambda data: data.update({"near": 200}),
])
def test_invalid_scene_input_rejected_before_writing_files(tmp_path, mutate):
    root = workspace(tmp_path)
    path = scene(root)
    data = json.loads(path.read_text(encoding="utf-8"))
    mutate(data)
    path.write_text(json.dumps(data), encoding="utf-8")
    result = run_game_cli([
        "jeeves", "render-reference", "--project", str(root),
        "--target", "ps1", "--source", "design/reference_scene.json",
        "--output", "assets/rejected.png",
    ])
    assert not result["ok"], result
    assert not (root / "assets" / "rejected.png").exists()
