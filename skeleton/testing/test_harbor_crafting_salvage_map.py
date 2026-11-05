"""Original source-bound map rendering, fog-of-war, assets and replay custody."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from skeleton.game.gameplay.harbor_crafting import HarborError, digest
from skeleton.game.gameplay.harbor_crafting_salvage import build_salvage
from skeleton.game.gameplay.harbor_crafting_salvage_assets import salvage_asset_manifest
from skeleton.game.gameplay.harbor_crafting_salvage_assets_authoring import (
    edit_salvage_assets, verify_salvage_assets_revision,
)
from skeleton.game.gameplay.harbor_crafting_salvage_map import (
    render_salvage_map, verify_salvage_map,
)
from skeleton.testing.test_harbor_crafting_salvage import inputs, actions

FIXTURES = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures"


def assets():
    return json.loads((FIXTURES / "harbor_lantern_quay_salvage_assets.json").read_text())


def test_fog_of_war_replay_and_earned_full_map():
    source, board = inputs()
    start = build_salvage(source, board, [])
    partial = render_salvage_map(start, assets())
    assert any("?" in row for row in verify_salvage_map(partial))
    with pytest.raises(HarborError, match="earned rescue"):
        render_salvage_map(start, assets(), reveal=True)
    full = render_salvage_map(build_salvage(source, board, actions()), assets(), reveal=True)
    assert all("?" not in row for row in verify_salvage_map(full))
    assert any("@" in row for row in full["frame"])
    assert salvage_asset_manifest(assets(), source, board)["asset_count"] == 9


def test_assets_authoring_preview_and_duplicate_glyph_rejection():
    source, board = inputs()
    before = assets()
    report = build_salvage(source, board, [])
    revision = edit_salvage_assets(source, board, before,
                                  [{"op": "set-glyph", "id": "site", "value": "X"}],
                                  expected_assets_digest=digest(before),
                                  preview_report=report)
    assert verify_salvage_assets_revision(revision)["glyphs"]["site"] == "X"
    assert revision["preview_before"] != revision["preview_after"]
    with pytest.raises(HarborError):
        edit_salvage_assets(source, board, before,
                            [{"op": "set-glyph", "id": "site", "value": "#"}],
                            expected_assets_digest=digest(before))


def test_resealed_map_frame_forgery_rejected():
    source, board = inputs()
    view = render_salvage_map(build_salvage(source, board, []), assets())
    damaged = deepcopy(view)
    damaged["frame"][1] = "@" * len(damaged["frame"][1])
    damaged["map_digest"] = digest({k: v for k, v in damaged.items()
                                     if k != "map_digest"})
    with pytest.raises(HarborError):
        verify_salvage_map(damaged)
