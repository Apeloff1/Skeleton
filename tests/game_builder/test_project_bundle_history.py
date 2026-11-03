import pytest

from skeleton.ai.game_builder.project_bundle.history import ProjectHistory
from skeleton.ai.game_builder.project_bundle.manifest import BundleError

from .conftest import edit


def test_versions_labels_and_rollback(ws, saver):
    h = ProjectHistory(saver)
    saver.save_project(ws, "hero", label="first")
    edit(ws, "hero", "game/readme.md", "# v2\n")
    saver.save_project(ws, "hero")
    assert [v.sequence for v in h.versions("hero")] == [1, 2]
    assert h.find_label("hero", "first") == 1
    h.label("hero", 2, "beta")
    assert h.find_label("hero", "beta") == 3
    out = h.rollback("hero", 1, workspace=ws, human_approved=True, authorized=True)
    assert out["new_head"] == 4 and out["files_match"] and out["workspace"]["written"] == ["game/readme.md"]
    assert h.sequences("hero") == (1, 2, 3, 4)
    with pytest.raises(BundleError):
        h.find_label("hero", "nope")


def test_rollback_without_approval_does_not_touch_workspace(ws, saver):
    h = ProjectHistory(saver)
    saver.save_project(ws, "hero")
    edit(ws, "hero", "game/readme.md", "# v2\n")
    before = h.sequences("hero")
    with pytest.raises(PermissionError):
        h.rollback("hero", 1, workspace=ws)
    assert h.sequences("hero") == before  # No unauthorized head publication.
    with pytest.raises(PermissionError):
        h.rollback("hero", 1, workspace=ws, authorized=True, human_approved=False)
    assert h.sequences("hero") == before
    with pytest.raises(PermissionError):
        h.rollback("hero", 1, workspace=ws, authorized=False, human_approved=True)
    assert h.sequences("hero") == before
    assert ws.read("current", "hero", "game/readme.md")["content"] == "# v2\n"
