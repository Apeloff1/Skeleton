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



def test_bundle_read_rejects_hardlinked_source_alias(tmp_path):
    import os

    outside = tmp_path / "unrelated-tenant.json"
    outside.write_text('{"private":"other tenant"}', encoding="utf-8")
    alias = tmp_path / "hero.gfbundle.json"
    try:
        os.link(outside, alias)
    except (OSError, NotImplementedError):
        pytest.skip("hard links unavailable on this filesystem")
    with pytest.raises(BundleError, match="hard-linked"):
        bio.read_bundle(alias)
    assert outside.read_text(encoding="utf-8") == '{"private":"other tenant"}'



def test_bundle_read_rejects_fifo_without_waiting_for_writer(tmp_path):
    import os

    if not hasattr(os, "mkfifo") or not hasattr(os, "O_NOFOLLOW"):
        pytest.skip("POSIX FIFO and nofollow unavailable")
    fifo = tmp_path / "blocked.gfbundle.json"
    os.mkfifo(fifo)
    with pytest.raises(BundleError, match="regular file"):
        bio.read_bundle(fifo)


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


def test_bundle_io_rejects_symlinked_ancestor(tmp_path):
    root = tmp_path / "real"
    root.mkdir()
    link = tmp_path / "redirect"
    try:
        link.symlink_to(root, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink unavailable")
    target = link / "hero.gfbundle.json"
    with pytest.raises(BundleError):
        bio.write_bundle(target, '{"safe":true}')
    (root / "hero.gfbundle.json").write_text('{"safe":true}')
    with pytest.raises(BundleError):
        bio.read_bundle(target)


def test_bundle_atomic_publication_holds_parent_descriptor_during_swap(tmp_path, monkeypatch):
    """Replacing the path to a parent cannot redirect the held rename."""
    import os

    root = tmp_path / "tenant"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    target = root / "hero.gfbundle.json"
    original_rename = bio.os.rename
    changed = [False]

    def swap_parent(src, dst, **kwargs):
        if not changed[0] and kwargs.get("src_dir_fd") is not None:
            changed[0] = True
            root.rename(tmp_path / "retired")
            root.symlink_to(outside, target_is_directory=True)
        return original_rename(src, dst, **kwargs)

    monkeypatch.setattr(bio.os, "rename", swap_parent)
    bio.write_bundle(target, '{"safe":true}')
    assert changed[0]
    assert (tmp_path / "retired" / target.name).read_text() == '{"safe":true}'
    assert not (outside / target.name).exists()
    with pytest.raises(BundleError):
        bio.read_bundle(target)


def test_bundle_import_rejects_signed_but_malformed_payload_shape(saver):
    for malformed in (
        {"manifest": {}},
        {"manifest": {}, "sections": {}, "receipts": {}},
        {"manifest": {}, "sections": {"files": []}, "receipts": {}},
    ):
        raw = CODEC.encode(malformed)
        with pytest.raises(BundleError, match="payload shape"):
            bio.import_bundle(raw, CODEC, ProjectSaver(GameSavePlane()))


def test_bundle_rejects_invalid_utf8_before_filesystem_publication(tmp_path, saver):
    bad = '{"text":"\ud800"}'  # unpaired surrogate is not valid UTF-8
    target = tmp_path / "hero.gfbundle.json"
    with pytest.raises(BundleError, match="UTF-8"):
        bio.write_bundle(target, bad)
    assert not target.exists()
    with pytest.raises(BundleError, match="UTF-8"):
        bio.import_bundle(bad, CODEC, saver)


def test_bundle_receipt_flood_is_rejected_before_store_allocation(saver, monkeypatch):
    saver.save_files("hero", "platformer", {"a.md": "abc"})
    payload = CODEC.decode(bio.export_bundle(saver, "hero", CODEC)).payload
    payload["receipts"]["receipts"].append(dict(payload["receipts"]["receipts"][0]))

    def forbidden_allocation(cls, state):
        raise AssertionError("unbounded receipt state was allocated")

    monkeypatch.setattr(bio.ChunkReceiptStore, "from_state", classmethod(forbidden_allocation))
    with pytest.raises(BundleError, match="receipt count mismatch"):
        bio.import_bundle(CODEC.encode(payload), CODEC, ProjectSaver(GameSavePlane()))


def test_bundle_receipts_reject_cross_file_and_noncanonical_chunk_authority(saver):
    import copy

    saver.save_files("hero", "platformer", {"a.md": "abc"})
    original = CODEC.decode(bio.export_bundle(saver, "hero", CODEC)).payload
    for change, message in (
        (lambda p: p["receipts"]["receipts"][0]["body"].update(path="other.md"),
         "identity or size"),
        (lambda p: p["receipts"]["receipts"][0]["body"].update(index=True),
         "identity or size"),
        (lambda p: p["sections"]["files"]["a.md"].update(chunks=["a.md#999"]),
         "noncanonical"),
        (lambda p: p["receipts"]["receipts"][0].update(chunk_id="other.md#0"),
         "duplicate or unknown"),
    ):
        payload = copy.deepcopy(original)
        change(payload)
        with pytest.raises(BundleError, match=message):
            bio.import_bundle(CODEC.encode(payload), CODEC, ProjectSaver(GameSavePlane()))


def test_bundle_receipt_chunk_size_and_declared_utf8_bytes_are_verified(saver):
    saver.save_files("hero", "platformer", {"a.md": "a" * (bio.CHUNK_CHARS + 1)})
    payload = CODEC.decode(bio.export_bundle(saver, "hero", CODEC)).payload
    payload["receipts"]["receipts"][0]["body"]["text"] += "z"
    with pytest.raises(BundleError, match="identity or size"):
        bio.import_bundle(CODEC.encode(payload), CODEC, ProjectSaver(GameSavePlane()))

    saver.save_files("other", "platformer", {"a.md": "abc"})
    payload = CODEC.decode(bio.export_bundle(saver, "other", CODEC)).payload
    payload["manifest"]["files"][0]["bytes"] = 4
    payload["manifest"].pop("content_digest")
    payload["sections"]["files"]["a.md"]["bytes"] = 4
    with pytest.raises(BundleError, match="byte count mismatch"):
        bio.import_bundle(CODEC.encode(payload), CODEC, ProjectSaver(GameSavePlane()))


def test_bundle_codec_faults_fail_closed_without_publishing(saver):
    """Malformed injected codec failures must never become partial imports."""
    class ThrowingCodec:
        def __init__(self, error):
            self.error = error

        def decode(self, raw):
            raise self.error

    class BrokenPayloadCodec:
        def decode(self, raw):
            class Broken:
                @property
                def payload(self):
                    raise RuntimeError("private codec diagnostic")
            return Broken()

    for codec in (ThrowingCodec(RuntimeError("private secret")),
                  ThrowingCodec(TypeError("bad adapter")), BrokenPayloadCodec()):
        with pytest.raises(BundleError, match="bundle envelope failed integrity check"):
            bio.import_bundle("{}", codec, saver)
    assert saver.next_sequence("hero") == 1


def test_bundle_path_refuses_namespace_purpose_aliases(tmp_path):
    for bad_purpose in ("..", ".", "other_data", "game_project_bundles:.."):
        def forged(tenant, *, purpose):
            return "tenant:" + "a" * 24 + ":" + bad_purpose

        with pytest.raises(BundleError, match="namespace shape or purpose"):
            bio.bundle_path(tmp_path, "tenant-one", "hero", forged)
