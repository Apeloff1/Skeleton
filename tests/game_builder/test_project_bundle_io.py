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
    for bad in ("/abs.md", "a\\b.md", ".hidden", "a/../b.md", ""):
        with pytest.raises(BundleError):
            bio.safe_member_path(bad)


def test_bundle_write_cannot_follow_predictable_temp_symlink(tmp_path):
    victim = tmp_path / "unrelated.txt"
    victim.write_text("private original", encoding="utf-8")
    target = tmp_path / "hero.gfbundle.json"
    predictable = target.with_name(target.name + ".tmp")
    try:
        predictable.symlink_to(victim)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable on this platform")

    bio.write_bundle(target, '{"safe":true}')
    assert victim.read_text(encoding="utf-8") == "private original"
    assert bio.read_bundle(target) == '{"safe":true}'
    assert predictable.is_symlink()


def test_bundle_read_refuses_symlink_and_same_size_rewrite(tmp_path, monkeypatch):
    import os

    target = tmp_path / "hero.gfbundle.json"
    target.write_text('{"safe":true}', encoding="utf-8")
    link = tmp_path / "redirect.gfbundle.json"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable on this platform")
    with pytest.raises(BundleError):
        bio.read_bundle(link)

    if not hasattr(os, "O_NOFOLLOW"):
        return
    original_read = bio.os.read
    changed = [False]

    def mutate_after_read(fd, size):
        block = original_read(fd, size)
        if block and not changed[0]:
            changed[0] = True
            before = os.fstat(fd)
            with target.open("r+b") as writer:
                writer.seek(2)
                writer.write(b"X")
                writer.flush()
                os.fsync(writer.fileno())
            os.utime(target, ns=(before.st_atime_ns, before.st_mtime_ns))
        return block

    monkeypatch.setattr(bio.os, "read", mutate_after_read)
    with pytest.raises(BundleError, match="changed during descriptor read"):
        bio.read_bundle(target)
    assert changed[0]


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
