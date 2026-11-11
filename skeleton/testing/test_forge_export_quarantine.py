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
