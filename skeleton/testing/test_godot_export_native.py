"""Engine-backed GF-D certification against the pinned Godot binary.

Skipped unless ``GODOT_BIN`` points at an executable Godot 4.7.2 build, so the
offline suite never claims native coverage it did not run.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from skeleton.godot_export import binary, certify, version

FIXTURES = Path(__file__).parent / "fixtures" / "godot_export"
GODOT = os.environ.get(binary.ENV_BINARY, "")

pytestmark = pytest.mark.skipif(not (GODOT and Path(GODOT).is_file() and os.access(GODOT, os.X_OK)),
                                reason="GODOT_BIN not set to an executable Godot binary")


def test_native_headless_import_and_check_only(tmp_path):
    root = tmp_path / "good"
    shutil.copytree(FIXTURES / "good", root)
    rep = certify.certify(root, certify.Options(godot=GODOT, timeout=240))
    by = {r.case_id: r for r in rep.results}
    if not by["GFB-01"].passed:
        pytest.skip(f"GODOT_BIN is not the pinned {binary.DEFAULT_PIN_VERSION}: {by['GFB-01'].detail}")
    assert rep.ship, rep.to_markdown()
    for cid in ("GFD-01", "GFD-02", "GFD-03", "GFD-04", "GFD-05"):
        assert by[cid].passed, rep.to_markdown()
    assert (root / ".godot").is_dir()


def test_native_check_only_catches_parse_error(tmp_path):
    root = tmp_path / "good"
    shutil.copytree(FIXTURES / "good", root)
    (root / "scripts" / "game.gd").write_text("extends Node\n\nfunc _ready(:\n\tpass\n")
    rep = certify.certify(root, certify.Options(godot=GODOT, timeout=240))
    by = {r.case_id: r for r in rep.results}
    v = version.parse(by["GFB-01"].detail["actual"]) if by["GFB-01"].passed else None
    if v is None:
        pytest.skip("GODOT_BIN is not the pinned engine")
    assert not by["GFD-04"].passed, rep.to_markdown()
    assert not rep.ship
