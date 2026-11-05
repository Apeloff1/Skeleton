"""Offline atlas editor CSP and lease regression contracts."""
from __future__ import annotations

import os
import pytest

from skeleton.jeeves.worlds.atlas import AtlasStore, propose_atlas, review_atlas
from skeleton.jeeves.worlds.atlas_editor import render_editor
from skeleton.jeeves.worlds.world_canon import CanonError, WorldStore, digest, propose


def world():
    return propose(
        world_id="atlasui", premise="A coastal original story.",
        protagonist="Nia", region="Coast", goal="Reach the tower.",
    )


def test_offline_editor_escapes_untrusted_source_and_enforces_csp():
    source = world()
    spec = propose_atlas(source, "Original coastal atlas.")
    spec["regions"][0]["name"] = "</script><img src=x onerror=alert(1)>"
    output = render_editor(spec, source).decode()
    assert "Content-Security-Policy" in output
    assert "script-src 'sha256-" in output
    assert "connect-src 'none'" in output
    assert "Original region atlas editor" in output
    assert "<img src=x" not in output
    assert "\\u003c/script>" in output
    assert "Export source JSON" in output
    assert "Load JSON edits" in output


def test_approved_atlas_is_not_editable_in_browser():
    source = world()
    spec = review_atlas(
        propose_atlas(source, "Map coast."),
        source, "Reviewed the coast.",
    )
    with pytest.raises(CanonError, match="atlas_editor_requires_draft"):
        render_editor(spec, source)


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored custody")
def test_editor_write_is_source_leased_and_operator_only(tmp_path):
    source = world()
    WorldStore(tmp_path).publish(source, create=True)
    store = AtlasStore(tmp_path)
    spec = store.propose("atlasui", "Map coast.")
    lease = store.save("atlasui", spec, expected_world_digest=digest(source), create=True)
    editor = store.editor("atlasui", expected_atlas_digest=lease)
    path = tmp_path / editor["html_file"]
    assert path.is_file()
    assert editor["atlas_digest"] == lease
    with pytest.raises(CanonError, match="atlas_stale_edit"):
        store.editor("atlasui", expected_atlas_digest="0" * 64)
    revised = dict(source)
    revised["scenes"] = [dict(s) for s in source["scenes"]]
    revised["scenes"][0]["narrative"] = "Revised coast."
    WorldStore(tmp_path).publish(revised, expected_digest=digest(source))
    with pytest.raises(CanonError, match="atlas_source_lease_mismatch"):
        store.editor("atlasui", expected_atlas_digest=lease)


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored custody")
def test_editor_respects_world_lock(tmp_path):
    source = world()
    WorldStore(tmp_path).publish(source, create=True)
    store = AtlasStore(tmp_path)
    spec = store.propose("atlasui", "Map coast.")
    lease = store.save("atlasui", spec, expected_world_digest=digest(source), create=True)
    (tmp_path / "atlasui.lock").write_text("busy")
    with pytest.raises(CanonError, match="lease_busy"):
        store.editor("atlasui", expected_atlas_digest=lease)
