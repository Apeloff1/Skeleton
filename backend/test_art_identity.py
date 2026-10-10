"""Deterministic tests for Art Director visual identity pass."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from core import art_identity as ai  # noqa: E402
from gameforge.godot_engine import scenes  # noqa: E402


def test_load_tokens_has_brand_and_lighting():
    toks = ai.load_tokens()
    assert toks["colors"]["brand"].upper() == "#8B5CF6"
    assert "key" in toks["lighting"]
    assert "player" in toks["materials"]


def test_apply_art_pass_injects_lights_and_marker():
    bare = scenes.platformer_scene.__wrapped__() if hasattr(scenes.platformer_scene, "__wrapped__") else None
    # Call the raw builder via SCENE_BUILDERS to avoid double-apply.
    raw = scenes.SCENE_BUILDERS["platformer"]()
    assert "ArtIdentityMarker" not in raw
    lit = ai.apply_art_pass(raw, template="platformer")
    assert "ArtIdentityMarker" in lit
    assert "ArtKeyLight" in lit
    assert "ArtRimLight" in lit
    assert "modulate = Color(\"#2E1B5B\")" in lit or "modulate = Color(\"#2e1b5b\")" in lit.lower()
    # Idempotent
    assert ai.apply_art_pass(lit, template="platformer") == lit


def test_critique_rejects_bare_node2d():
    bare = (
        '[gd_scene load_steps=1 format=3]\n'
        '[node name="Main" type="Node2D"]\n'
    )
    report = ai.critique(bare)
    assert report["passed"] is False
    assert report["silhouette_ok"] is False
    assert any("bare" in f or "missing" in f for f in report["fails"])


def test_critique_accepts_art_passed_platformer():
    raw = scenes.SCENE_BUILDERS["platformer"]()
    lit = ai.apply_art_pass(raw, template="platformer")
    report = ai.critique(lit)
    assert report["passed"] is True, report["fails"]
    assert report["silhouette_ok"] and report["readable"] and report["consistent"]


def test_render_scene_applies_art_pass():
    text = scenes.render_scene("topdown")
    assert "ArtIdentityMarker" in text
    assert "ArtKeyLight" in text
    report = ai.critique(text)
    assert report["passed"] is True, report["fails"]


def test_off_palette_color_fails_consistent():
    raw = scenes.SCENE_BUILDERS["empty"]()
    lit = ai.apply_art_pass(raw, template="empty")
    tainted = lit.replace("#8B5CF6", "#FF00FF", 1)
    report = ai.critique(tainted)
    assert report["consistent"] is False
    assert report["passed"] is False
