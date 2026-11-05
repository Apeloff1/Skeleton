import pytest

from skeleton.ai.game_builder.project_bundle import migrations as mg
from skeleton.ai.game_builder.project_bundle.manifest import BUNDLE_SCHEMA_VERSION, BundleError
from skeleton.ai.game_builder.project_bundle.project_save import ProjectSaver, slot_for
from skeleton.kernel.game_save_plane import GameSavePlane, SavePlaneError

LEGACY = {"sections": {"workspace": {"project": "hero", "genre": "platformer",
                                     "files": {"project.json": "{}", "game/readme.md": "# hi"}},
                       "gameplay": {"schema": 7, "hp": 3}}}


def plane_with_v0(state):
    plane = GameSavePlane()
    plane.store.save(GameSavePlane.COMPONENT_PREFIX + slot_for("hero"), 1, state)
    return plane


def test_legacy_v0_upgrades_and_leaves_gameplay_untouched():
    plane = plane_with_v0(LEGACY)
    with pytest.raises(SavePlaneError):
        plane.restore(slot_for("hero"))  # no migration registered yet
    mg.install_bundle_migrations(plane)
    v = ProjectSaver(plane).load("hero")
    assert v.files == {"game/readme.md": "# hi", "project.json": "{}"}
    assert v.manifest.label == "legacy-v0" and v.sections["gameplay"] == {"schema": 7, "hp": 3}


def test_non_bundle_v0_state_passes_through():
    state = {"sections": {"gameplay": {"hp": 1}}}
    assert mg.upgrade_legacy_workspace(state) is state


def test_too_new_rejected():
    plane = plane_with_v0({"schema_version": 99, "sections": {}})
    with pytest.raises(SavePlaneError):
        plane.restore(slot_for("hero"))
    with pytest.raises(BundleError):
        mg.check_bundle_schema({"bundle": {"bundle_schema_version": BUNDLE_SCHEMA_VERSION + 1}})


def test_malformed_legacy_and_double_install():
    with pytest.raises(BundleError):
        mg.upgrade_legacy_workspace({"sections": {"workspace": {"project": "hero"}}})
    plane = GameSavePlane()
    mg.install_bundle_migrations(plane)
    with pytest.raises(SavePlaneError):
        mg.install_bundle_migrations(plane)
