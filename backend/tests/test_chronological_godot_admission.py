"""Chronological Godot admission regressions; no external binary is launched."""
import asyncio
import hashlib
from pathlib import Path

import pytest

from gameforge.godot_engine import binary as module


@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "require_execution_allowed", lambda _: True)
    monkeypatch.delenv("GODOT_SHA256", raising=False)
    monkeypatch.delenv("GODOT_FINGERPRINT", raising=False)
    path = tmp_path / "godot"
    path.write_bytes(b"test engine")
    path.chmod(0o700)
    return module.GodotBinary(path, "env")


def test_full_pin_before_launch(engine, monkeypatch):
    monkeypatch.setenv("GODOT_SHA256", "0" * 64)
    async def forbidden(*args, **kwargs):
        pytest.fail("mismatched executable launched")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", forbidden)
    with pytest.raises(PermissionError, match="mismatch"):
        asyncio.run(engine.probe())


def test_guard_does_not_mutate_permissions(engine, monkeypatch):
    engine.path.chmod(0o600)
    before = engine.path.stat().st_mode
    monkeypatch.setattr(module, "require_execution_allowed", lambda _: False)
    with pytest.raises(PermissionError):
        engine.prepare_execution()
    assert engine.path.stat().st_mode == before


def test_full_pin_and_identity(engine, monkeypatch):
    digest = hashlib.sha256(engine.path.read_bytes()).hexdigest()
    monkeypatch.setenv("GODOT_SHA256", digest)
    admission = engine.prepare_execution()
    assert admission.sha256 == digest
    assert admission.integrity == "verified"
    engine.path.write_bytes(b"replaced engine content")
    with pytest.raises(RuntimeError, match="changed"):
        admission.assert_current()


def test_sample_pin_does_not_claim_full_verification(engine, monkeypatch):
    monkeypatch.setenv("GODOT_FINGERPRINT", engine.fingerprint())
    assert engine.prepare_execution().integrity == "unchecked"


def test_failed_override_never_falls_through(engine, monkeypatch):
    monkeypatch.setenv("GODOT_BINARY", str(engine.path.parent / "missing"))
    assert module._candidate([]) is None


def test_full_pin_detects_middle_byte_change(engine, monkeypatch):
    raw = b"a" * (3 * module._HASH_CHUNK)
    engine.path.write_bytes(raw)
    monkeypatch.setenv("GODOT_SHA256", hashlib.sha256(raw).hexdigest())
    sample = engine.fingerprint()
    engine.path.write_bytes(raw[:module._HASH_CHUNK] + b"b" + raw[module._HASH_CHUNK + 1:])
    assert engine.fingerprint() == sample
    with pytest.raises(PermissionError, match="SHA-256 mismatch"):
        engine.prepare_execution()


def test_pipeline_check_arguments_are_strings(tmp_path):
    from routes.godot_engine import _resolve_within
    assert str(_resolve_within(tmp_path, "main.gd", "script")).endswith("main.gd")
