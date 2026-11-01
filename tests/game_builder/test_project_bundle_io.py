import json

import pytest

from backend.core.save_envelope import SaveCodec
from backend.core.tenant_storage_boundary import tenant_storage_namespace
from skeleton.ai.game_builder.project_bundle import bundle_io as bio
from skeleton.ai.game_builder.project_bundle.manifest import BUNDLE_SCHEMA_VERSION, BundleError
from skeleton.ai.game_builder.project_bundle.project_save import ProjectSaver
from skeleton.kernel.game_save_plane import GameSavePlane

CODEC = SaveCodec(BUNDLE_SCHEMA_VERSION)


def test_export_is_deterministic_and_imports(ws, saver):
    saver.save_project(ws, "hero", label="ship")
    raw = bio.export_bundle(saver, "hero", CODEC)
    assert raw == bio.export_bundle(saver, "hero", CODEC)
    other = ProjectSaver(GameSavePlane())
    m = bio.import_bundle(raw, CODEC, other)
    assert m.file_map() == saver.load("hero").manifest.file_map() and m.label == "ship"
    assert other.load("hero").files == saver.load("hero").files


def test_tamper_and_limits_rejected(saver):
    saver.save_files("hero", "platformer", {"a.md": "abc"})
    raw = bio.export_bundle(saver, "hero", CODEC)
    with pytest.raises(BundleError):
        bio.import_bundle(raw.replace("abc", "abd"), CODEC, ProjectSaver(GameSavePlane()))
    with pytest.raises(BundleError):
        bio.import_bundle("x" * (bio.MAX_BUNDLE_BYTES + 1), CODEC, ProjectSaver(GameSavePlane()))


def test_zip_slip_member_rejected_even_with_valid_envelope(saver):
    saver.save_files("hero", "platformer", {"a.md": "abc"})
    payload = CODEC.decode(bio.export_bundle(saver, "hero", CODEC)).payload
    payload["manifest"]["files"][0]["path"] = "../../etc/passwd"
    payload["manifest"].pop("content_digest")
    with pytest.raises(BundleError):
        bio.import_bundle(CODEC.encode(payload), CODEC, ProjectSaver(GameSavePlane()))
    for bad in ("/abs.md", "a\\b.md", ".hidden", "a/../b.md", "",
                "a//b.md", "a/./b.md", "a/b.md/"):
        with pytest.raises(BundleError):
            bio.safe_member_path(bad)


def test_tenant_path_write_read(tmp_path, saver):
    saver.save_files("hero", "platformer", {"a.md": "abc"})
    p = bio.bundle_path(tmp_path, "tenant-one", "hero", tenant_storage_namespace)
    assert tmp_path.resolve() in p.parents and p.name == "hero.gfbundle.json"
    assert p != bio.bundle_path(tmp_path, "tenant-two", "hero", tenant_storage_namespace)
    raw = bio.export_bundle(saver, "hero", CODEC)
    bio.write_bundle(p, raw)
    assert bio.read_bundle(p) == raw
    with pytest.raises(BundleError):
        bio.bundle_path(tmp_path, "t", "../x", tenant_storage_namespace)
    with pytest.raises(BundleError):
        bio.bundle_path(tmp_path, "t", "hero", lambda t, purpose: "../../escape")
    assert json.loads(raw)["version"] == BUNDLE_SCHEMA_VERSION
