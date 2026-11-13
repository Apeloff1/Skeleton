from __future__ import annotations

import os
import hashlib
from pathlib import Path

import pytest

import skeleton.ai.runtime.inference.artifact as artifact_module
from skeleton.ai.runtime.inference.artifact import (
    LocalModelArtifactError,
    load_local_model_artifact,
    write_local_model_artifact,
)
from skeleton.ai.runtime.inference.local import ReferenceNGramModel


def _artifact(tmp_path):
    source = tmp_path / "model.json"
    write_local_model_artifact(ReferenceNGramModel.train(("alpha beta",)), source)
    return source


def test_oversized_sparse_artifact_rejects_before_open_or_read(tmp_path, monkeypatch):
    source = tmp_path / "oversized.json"
    with source.open("wb") as handle:
        handle.truncate(artifact_module._MAX_ARTIFACT_BYTES + 1)

    def forbidden(*args, **kwargs):
        raise AssertionError("oversized file must be rejected before allocation or descriptor open")

    monkeypatch.setattr(artifact_module.os, "open", forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    with pytest.raises(LocalModelArtifactError, match="byte bounds"):
        load_local_model_artifact(source)


@pytest.mark.parametrize("kind", ["directory", "fifo", "symlink", "parent_symlink"])
def test_artifact_nonregular_paths_fail_before_any_content_read(tmp_path, monkeypatch, kind):
    source = _artifact(tmp_path)
    if kind == "directory":
        source = tmp_path
        reason = "regular file"
    elif kind == "fifo":
        if not hasattr(os, "mkfifo"):
            pytest.skip("named pipes unavailable")
        source = tmp_path / "fifo"
        os.mkfifo(source)
        reason = "regular file"
    elif kind == "symlink":
        link = tmp_path / "linked.json"
        link.symlink_to(source)
        source = link
        reason = "symlink"
    else:
        alias = tmp_path / "alias"
        alias.symlink_to(tmp_path, target_is_directory=True)
        source = alias / "model.json"
        reason = "symlink"

    def forbidden(*args, **kwargs):
        raise AssertionError("nonregular artifacts must fail before open/read")

    monkeypatch.setattr(artifact_module.os, "open", forbidden)
    with pytest.raises(LocalModelArtifactError, match=reason):
        load_local_model_artifact(source)


@pytest.mark.parametrize("change", ["grow", "same_size_rewrite", "replace_path", "truncate"])
def test_artifact_identity_change_during_descriptor_read_fails_closed(tmp_path, monkeypatch, change):
    source = _artifact(tmp_path)
    original_read = os.read
    changed = False
    original_size = source.stat().st_size

    def read_and_change(descriptor, size):
        nonlocal changed
        data = original_read(descriptor, size)
        if not changed:
            changed = True
            if change == "grow":
                with source.open("ab") as handle:
                    handle.write(b" ")
            elif change == "same_size_rewrite":
                with source.open("r+b") as handle:
                    handle.write(b" " * original_size)
            elif change == "replace_path":
                replacement = tmp_path / "replacement.json"
                replacement.write_bytes(source.read_bytes())
                os.replace(replacement, source)
            else:
                with source.open("r+b") as handle:
                    handle.truncate(max(1, original_size // 2))
        return data

    monkeypatch.setattr(artifact_module.os, "read", read_and_change)
    with pytest.raises(LocalModelArtifactError, match="changed while reading"):
        load_local_model_artifact(source)


def test_descriptor_read_is_capped_even_when_file_grows(tmp_path, monkeypatch):
    source = _artifact(tmp_path)
    original_size = source.stat().st_size
    real_read = os.read
    consumed = 0

    def growing_read(descriptor, size):
        nonlocal consumed
        data = real_read(descriptor, size)
        consumed += len(data)
        if consumed == original_size:
            with source.open("ab") as handle:
                handle.write(b"x" * (original_size * 5))
        return data

    monkeypatch.setattr(artifact_module.os, "read", growing_read)
    with pytest.raises(LocalModelArtifactError, match="changed while reading"):
        load_local_model_artifact(source)
    assert consumed <= original_size + 1


def test_valid_artifact_uses_descriptor_read_with_identical_receipt(tmp_path, monkeypatch):
    source = _artifact(tmp_path)

    def forbidden(*args, **kwargs):
        raise AssertionError("Path.read_bytes bypasses bounded intake")

    monkeypatch.setattr(Path, "read_bytes", forbidden)
    loaded = load_local_model_artifact(source)
    assert loaded.receipt.artifact_bytes == source.stat().st_size
    assert loaded.model.model_digest == loaded.receipt.model_digest


def test_regular_file_swapped_to_fifo_before_open_does_not_block(tmp_path, monkeypatch):
    if not hasattr(os, "mkfifo") or not hasattr(os, "O_NONBLOCK"):
        pytest.skip("named pipe descriptor flags unavailable")
    source = _artifact(tmp_path)
    original_open = os.open

    def swapped_open(path, flags, *args, **kwargs):
        assert flags & os.O_NONBLOCK
        source.unlink()
        os.mkfifo(source)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(artifact_module.os, "open", swapped_open)
    with pytest.raises(LocalModelArtifactError, match="regular file"):
        load_local_model_artifact(source)


def test_deeply_nested_json_fails_through_artifact_corruption_boundary(tmp_path):
    source = tmp_path / "nested.json"
    source.write_bytes(b"[" * 10000 + b"0" + b"]" * 10000)
    with pytest.raises(LocalModelArtifactError, match="invalid JSON"):
        load_local_model_artifact(source)


def test_regular_file_replaced_before_open_rejects_before_read(tmp_path, monkeypatch):
    source = _artifact(tmp_path)
    replacement = tmp_path / "replacement.json"
    replacement.write_bytes(source.read_bytes())
    original_open = os.open

    def replaced_open(path, flags, *args, **kwargs):
        os.replace(replacement, source)
        return original_open(path, flags, *args, **kwargs)

    def forbidden_read(*args):
        raise AssertionError("a replacement inode must not be read")

    monkeypatch.setattr(artifact_module.os, "open", replaced_open)
    monkeypatch.setattr(artifact_module.os, "read", forbidden_read)
    with pytest.raises(LocalModelArtifactError, match="changed while reading"):
        load_local_model_artifact(source)


def test_pinned_artifact_is_rechecked_after_model_restoration(tmp_path, monkeypatch):
    source = _artifact(tmp_path)
    expected = hashlib.sha256(source.read_bytes()).hexdigest()
    original_restore = artifact_module._payload_model

    def restore_and_replace(payload):
        model = original_restore(payload)
        replacement = tmp_path / "replacement.json"
        replacement.write_bytes(source.read_bytes())
        os.replace(replacement, source)
        return model

    monkeypatch.setattr(artifact_module, "_payload_model", restore_and_replace)
    with pytest.raises(LocalModelArtifactError, match="changed during activation"):
        load_local_model_artifact(source, expected_sha256=expected)


def test_descriptor_closes_when_bounded_read_fails(tmp_path, monkeypatch):
    source = _artifact(tmp_path)
    original_close = os.close
    closed = []

    def fail_read(*args):
        raise OSError("read interrupted")

    def record_close(descriptor):
        closed.append(descriptor)
        return original_close(descriptor)

    monkeypatch.setattr(artifact_module.os, "read", fail_read)
    monkeypatch.setattr(artifact_module.os, "close", record_close)
    with pytest.raises(LocalModelArtifactError, match="unavailable"):
        load_local_model_artifact(source)
    assert len(closed) == 1
