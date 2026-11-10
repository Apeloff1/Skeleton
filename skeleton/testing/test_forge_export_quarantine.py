"""Godot native export selective recovery: fail closed without device evidence."""
from __future__ import annotations
import os
import pytest
from skeleton.forge import export as ex
from skeleton.forge.eras import compile_era
from skeleton.forge.godot_emit import emit_godot


def emitted():
    return emit_godot(compile_era("extraction_now"), title="quarantine")


def test_invalid_native_output_budgets_fail_before_engine(tmp_path):
    for kw in ({"timeout":float("nan")},{"timeout":float("inf")},{"timeout":0},
               {"boot_frames":True},{"boot_frames":100001}):
        with pytest.raises(ValueError):
            ex.export_build(emitted(),tmp_path,**kw)


@pytest.mark.skipif(os.name != "posix",reason="POSIX no-follow output boundary")
def test_symlinked_output_parent_and_existing_project_denied(tmp_path,monkeypatch):
    monkeypatch.setattr(ex,"resolve_binary",lambda binary=None:("/bin/true","fake",False))
    other=tmp_path/"other"
    other.mkdir()
    linked=tmp_path/"linked"
    linked.symlink_to(other,target_is_directory=True)
    with pytest.raises(OSError):
        ex.export_build(emitted(),linked/"artifacts")
    out=tmp_path/"real"
    (out/"project").mkdir(parents=True)
    with pytest.raises(ValueError, match="no clobber"):
        ex.export_build(emitted(),out)


@pytest.mark.skipif(os.name != "posix",reason="POSIX no-follow output boundary")
def test_import_nonzero_without_log_error_is_failure(tmp_path,monkeypatch):
    monkeypatch.setattr(ex,"resolve_binary",lambda binary=None:("/bin/true","fake",False))
    monkeypatch.setattr(ex,"_run",lambda *args:(22,"",False))
    result=ex.export_build(emitted(),tmp_path/"out")
    assert result["status"]=="failed" and result["reason"]=="import"
    assert result["passed"] is False and result["release_certified"] is False


@pytest.mark.skipif(os.name != "posix",reason="POSIX no-follow output boundary")
def test_fake_symlinked_native_artifact_never_passes(tmp_path):
    real=tmp_path/"real"
    real.write_bytes(b"binary")
    linked=tmp_path/"linked"
    linked.symlink_to(real)
    assert not ex._regular_output(linked)
    with pytest.raises(ValueError):
        ex._artifact_digest(linked)


@pytest.mark.skipif(os.name != "posix", reason="POSIX no-follow output boundary")
def test_digest_denies_same_size_rewrite_during_stream(tmp_path, monkeypatch):
    target = tmp_path / "artifact.pck"
    target.write_bytes(b"a" * 8192)
    original_read = os.read
    modified = [False]

    def rewriting_read(fd, count):
        chunk = original_read(fd, count)
        if chunk and not modified[0]:
            modified[0] = True
            with target.open("r+b") as out:
                out.seek(0)
                out.write(b"b" * 8192)
            before = target.stat()
            os.utime(target, ns=(before.st_atime_ns, before.st_mtime_ns + 2_000_000_000))
        return chunk

    with monkeypatch.context() as scope:
        scope.setattr(ex.os, "read", rewriting_read)
        with pytest.raises(ValueError, match="changed"):
            ex._artifact_digest(target)
    assert modified[0] is True


@pytest.mark.skipif(os.name != "posix", reason="POSIX no-follow output boundary")
def test_digest_denies_path_replacement_after_open(tmp_path, monkeypatch):
    target = tmp_path / "artifact.pck"
    removed = tmp_path / "old.pck"
    replacement = tmp_path / "new.pck"
    target.write_bytes(b"a" * 8192)
    replacement.write_bytes(b"b" * 8192)
    original_read = os.read
    replaced = [False]

    def replacing_read(fd, count):
        chunk = original_read(fd, count)
        if chunk and not replaced[0]:
            replaced[0] = True
            os.replace(target, removed)
            os.replace(replacement, target)
        return chunk

    with monkeypatch.context() as scope:
        scope.setattr(ex.os, "read", replacing_read)
        with pytest.raises(ValueError, match="artifact changed during hashing"):
            ex._artifact_digest(target)
    assert replaced[0] is True


def test_duplicate_and_nonstring_presets_fail_before_binary_lookup(tmp_path):
    for presets in (("Linux", "Linux"), (None,), (0,), (["Linux"],)):
        with pytest.raises(ValueError, match="presets"):
            ex.export_build(emitted(), tmp_path, presets=presets)
