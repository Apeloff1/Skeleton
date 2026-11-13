"""Offline scene editor source lease, CSP and injection regression fixtures."""
import os

import pytest

from skeleton.jeeves.worlds.editor import WorldEditorStore, render_editor_html
from skeleton.jeeves.worlds.world_canon import (
    CanonError, WorldStore, digest, propose,
)


def original():
    return propose(world_id="harbor", premise="A navigator discovers a beacon.",
                   protagonist="Sora", region="North Harbor",
                   goal="Restore the beacon.")


def test_offline_editor_is_source_bound():
    world = original()
    html = render_editor_html(world)
    assert digest(world) in html
    assert "default-src 'none'" in html
    assert "connect-src 'none'" in html
    assert "Export reviewed edit" in html
    assert "replace_scene" in html
    assert "innerHTML" not in html
    assert "eval(" not in html


def test_editor_escapes_script_termination_and_markup():
    world = original()
    world["scenes"][0]["narrative"] = "</script><img src=x onerror=alert(1)>"
    html = render_editor_html(world)
    assert "</script><img" not in html
    assert "\\u003c/script>" in html


def test_editor_is_deterministic():
    world = original()
    assert render_editor_html(world) == render_editor_html(world)


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor-anchored custody")
def test_render_and_source_lease(tmp_path):
    root = tmp_path / "private"
    worlds = WorldStore(root)
    world = original()
    current = worlds.publish(world, create=True)
    store = WorldEditorStore(root)
    receipt = store.render("harbor", current)
    assert receipt["source_digest"] == current
    assert (root / receipt["editor_file"]).is_file()
    with pytest.raises(CanonError, match="stale_source"):
        store.render("harbor", "0" * 64)


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor-anchored custody")
def test_world_revision_invalidates_old_editor_lease(tmp_path):
    root = tmp_path / "private"
    worlds = WorldStore(root)
    world = original()
    old = worlds.publish(world, create=True)
    store = WorldEditorStore(root)
    store.render("harbor", old)
    world["scenes"][0]["title"] = "Revised"
    worlds.publish(world, expected_digest=old)
    with pytest.raises(CanonError, match="stale_source"):
        store.render("harbor", old)


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor-anchored custody")
def test_symlink_editor_target_is_replaced_not_followed(tmp_path):
    root = tmp_path / "private"
    worlds = WorldStore(root)
    world = original()
    current = worlds.publish(world, create=True)
    outside = tmp_path / "outside"
    outside.write_text("do not change")
    (root / "harbor.editor.html").symlink_to(outside)
    WorldEditorStore(root).render("harbor", current)
    assert outside.read_text() == "do not change"
    assert not (root / "harbor.editor.html").is_symlink()
