"""Exact token protocol and host fixtures; not native hardware qualification."""
import asyncio
from dataclasses import replace
import hashlib
import json
import os
import struct
import threading
from types import SimpleNamespace

import pytest

from skeleton.ai.runtime.inference.gguf_token_bridge import (
    GgufTokenBridgeModel, _Frame, _pack_ids, _text, _compatible,
)
from skeleton.ai.runtime.inference.llama_cpp import LlamaCppConfig, LlamaCppRuntimeError
from skeleton.ai.runtime.inference.local import LocalInferenceRequest
from skeleton.ai.runtime.inference.deployment import (
    LocalModelDeployment, LocalModelDeploymentError, create_local_model_deployment,
)
from skeleton.context.pre_delivery_guard import (
    GuardedLocalInference, TrustedContextSnapshot, ReviewVerdict, merkle_root, request_parts,
)
from skeleton.context.sealed_sandwich import SealedContextIntegrityError

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX bridge custody required")


def test_binary_frames_deny_truncation_trailing_bytes_and_invalid_ids():
    frame = _Frame(b"SKG1" + _pack_ids((0, 124, 2**31-1)) + _text("Å".encode()))
    assert frame.ids() == (0, 124, 2**31-1)
    assert frame.text() == "Å"
    frame.finish()
    for raw in (b"", b"SKG2", b"SKG1\x01", b"SKG1" + struct.pack("<I", 2**31)):
        with pytest.raises(LlamaCppRuntimeError):
            _Frame(raw).ids()
    with pytest.raises(LlamaCppRuntimeError):
        _Frame(b"SKG1x").finish()
    with pytest.raises(LlamaCppRuntimeError):
        _Frame(b"SKG1" + _text(b"\xff")).text()
    for tokens in ((True,), (-1,), (2**31,), ("1",)):
        with pytest.raises(LlamaCppRuntimeError):
            _pack_ids(tokens)


def test_unsupported_configuration_does_not_silently_degrade():
    config = LlamaCppConfig(executable="/bridge", model_path="/model", context_size=1024, gpu_layers=0)
    _compatible(config)
    for fields in ({"gpu_layers": 1}, {"temperature": 0.5}, {"threads": 257},
                   {"batch_size": 8193}, {"output_framing": "llama_completion_eog"},
                   {"context_size": None}):
        with pytest.raises((ValueError, LlamaCppRuntimeError)):
            _compatible(replace(config, **fields))


def fixture(tmp_path):
    model = tmp_path / "tiny.gguf"
    model.write_bytes(struct.pack("<4sIQQ", b"GGUF", 3, 2, 1)
        + struct.pack("<Q", len(b"general.architecture")) + b"general.architecture"
        + struct.pack("<I", 8) + struct.pack("<Q", 5) + b"llama" + b"fixture")
    # Deterministic transport fixture, deliberately NOT a native model.
    helper = tmp_path / "bridge"
    helper.write_text("""#!/usr/bin/env python3
import pathlib, struct, sys
op, model, source, target, ctx, threads, batch, completion = sys.argv[1:]
raw = pathlib.Path(source).read_bytes()
assert raw[:4] == b'SKG1'
n = struct.unpack_from('<I', raw, 4)[0]
def ids(seq):
    return struct.pack('<I', len(seq)) + struct.pack('<' + 'I'*len(seq), *seq)
def text(raw):
    return struct.pack('<I', len(raw)) + raw
if op == 'encode':
    reply = ids(raw[8:8+n])
elif op == 'roundtrip':
    reply = ids(raw[8:8+n]) + text(raw[8:8+n])
elif op == 'decode':
    reply = text(bytes(struct.unpack_from('<'+'I'*n, raw, 8)))
else:
    prompt = raw[8:8+n]
    count = struct.unpack_from('<I', raw, 8+n)[0]
    admitted = struct.unpack_from('<'+'I'*count, raw, 12+n)
    assert tuple(prompt) == admitted
    answer = b'ok'
    reply = struct.pack('<I', 0) + ids(admitted) + ids(answer) + text(answer)
pathlib.Path(target).write_bytes(b'SKG1' + reply)
""", encoding="utf-8")
    helper.chmod(0o700)
    config = LlamaCppConfig(executable=str(helper), model_path=str(model), model_id="jeeves",
        context_size=1024, timeout_seconds=10, gpu_layers=0)
    return GgufTokenBridgeModel(config), helper, model


def test_host_transport_roundtrip_and_consumption_receipt(tmp_path):
    model, _, _ = fixture(tmp_path)
    request = LocalInferenceRequest(prompt="Å test", max_output_tokens=8)
    prepared = model.prepare_input(request)
    assert model.decode_ids(prepared.token_sequence) == request.rendered_input
    result = model.infer_prepared(request, threading.Event(), prepared)
    assert result.text == "ok" and result.input_tokens == prepared.input_tokens
    assert result.output_tokens == 2
    assert len(result.execution_receipt_digest) == 64
    assert model.execution_snapshot()["active_processes"] == 0
    assert model.execution_snapshot()["exact_token_admission"] is True
    with pytest.raises((ValueError, LlamaCppRuntimeError)):
        model.infer_prepared(request, threading.Event(), replace(prepared, token_sequence=(1,)))


def test_physical_consumed_ids_and_output_echo_must_match(tmp_path, monkeypatch):
    model, _, _ = fixture(tmp_path)
    request = LocalInferenceRequest(prompt="test", max_output_tokens=8)
    prepared = model.prepare_input(request)
    actual = model._invoke
    for consumed, answer, text in (((1,), (111, 107), b"ok"),
                                   (prepared.token_sequence, (111, 107), b"NO")):
        def forged(operation, payload, **kwargs):
            if operation == "generate":
                return _Frame(b"SKG1" + struct.pack("<I", 0) + _pack_ids(consumed)
                              + _pack_ids(answer) + _text(text))
            return actual(operation, payload, **kwargs)
        with monkeypatch.context() as m:
            m.setattr(model, "_invoke", forged)
            with pytest.raises(LlamaCppRuntimeError):
                model.infer_prepared(request, threading.Event(), prepared)


def test_deployment_dispatch_never_allows_unguarded_bridge(tmp_path):
    _, helper, model = fixture(tmp_path)
    path = tmp_path / "manifest.json"
    loaded = create_local_model_deployment(path, executable_path=helper, model_path=model,
        runtime_profile="gguf-exact-token-bridge", context_size=1024, model_id="jeeves")
    assert loaded.runtime_kind == "llama.cpp-token-bridge-v1"
    assert LocalModelDeployment.load(path).runtime_kind == loaded.runtime_kind
    assert json.loads(path.read_text())["runtime_kind"] == loaded.runtime_kind
    with pytest.raises(LocalModelDeploymentError, match="activation denied"):
        loaded.adapter()


def test_pinned_helper_mutation_is_denied(tmp_path):
    model, helper, _ = fixture(tmp_path)
    helper.write_text("changed")
    with pytest.raises(LlamaCppRuntimeError):
        model.encode_ids("private")


def test_guard_rejects_alternate_prepared_token_vector_before_dispatch():
    class Engine:
        model = SimpleNamespace(requires_exact_guard_tokens=True)
        calls = 0
        def prepare_input(self, request, **kwargs):
            return SimpleNamespace(token_sequence=(1, 2, 3))
        async def generate(self, request, **kwargs):
            self.calls += 1
            return SimpleNamespace(text="must not be released")

    request = LocalInferenceRequest(prompt="hello", instructions="policy")
    snapshot = TrustedContextSnapshot(
        merkle_root(request_parts(request)), hashlib.sha256(b"policy").hexdigest(),
        1, "tenant", "thread",
    )
    engine = Engine()
    guard = GuardedLocalInference(
        engine, reviewer=lambda text, digest: ReviewVerdict(True, digest, "reviewer", "allow"),
        tokenize=lambda text: tuple(text.encode()), detokenize=lambda ids: bytes(ids).decode(),
    )
    with pytest.raises(SealedContextIntegrityError, match="prepared native IDs"):
        asyncio.run(guard.generate(request, snapshot=snapshot, tenant_scope_id="tenant"))
    assert engine.calls == 0


def test_combined_roundtrip_is_one_native_launch(tmp_path):
    model, _, _ = fixture(tmp_path)
    before = model.execution_snapshot()["processes_started"]
    ids, echo = model.roundtrip_ids("Å \U0001f680")
    assert echo == "Å \U0001f680"
    assert ids == tuple(echo.encode())
    assert model.execution_snapshot()["processes_started"] == before + 1


def test_roundtrip_denies_nonidentical_echo(tmp_path, monkeypatch):
    model, _, _ = fixture(tmp_path)
    monkeypatch.setattr(model, "_invoke", lambda *a, **kw: _Frame(
        b"SKG1" + _pack_ids((1,)) + _text(b"foreign")))
    with pytest.raises(LlamaCppRuntimeError, match="round-trip"):
        model.roundtrip_ids("private")


@pytest.mark.skipif(not __import__("sys").platform.startswith("linux"), reason="Linux memfd only")
def test_linux_descriptor_frame_denies_input_mutation_and_seals_response(tmp_path):
    import fcntl
    from skeleton.ai.runtime.inference.gguf_private_transport import private_frame
    model, _, _ = fixture(tmp_path)
    with private_frame(model.runtime_artifact, model.model_artifact, b"SKG1private", lambda: None) as frame:
        assert frame.source.startswith("/proc/self/fd/")
        assert frame.model.startswith("/proc/self/fd/")
        assert list(frame.base.iterdir()) == []
        input_fd = int(frame.source.rsplit("/", 1)[1])
        output_fd = int(frame.target.rsplit("/", 1)[1])
        flags = fcntl.fcntl(input_fd, fcntl.F_GET_SEALS)
        assert flags & fcntl.F_SEAL_WRITE
        with pytest.raises(OSError):
            os.pwrite(input_fd, b"modified", 0)
        os.write(output_fd, b"SKG1")
        assert frame.read(32) == b"SKG1"
        with pytest.raises(OSError):
            os.pwrite(output_fd, b"changed", 0)
    for fd in (input_fd, output_fd):
        with pytest.raises(OSError):
            os.fstat(fd)


@pytest.mark.skipif(not __import__("sys").platform.startswith("linux"), reason="Linux memfd only")
def test_descriptor_rejects_path_replacement_even_with_old_inode_open(tmp_path):
    from skeleton.ai.runtime.inference.gguf_private_transport import private_frame
    model, _, weights = fixture(tmp_path)
    with private_frame(model.runtime_artifact, model.model_artifact, b"SKG1", lambda: None) as frame:
        original = weights.read_bytes()
        replacement = weights.with_suffix(".new")
        replacement.write_bytes(original)
        os.replace(replacement, weights)
        assert open(frame.model, "rb").read() == original
        with pytest.raises(LlamaCppRuntimeError):
            frame.verify(lambda: None)


@pytest.mark.skipif(not __import__("sys").platform.startswith("linux"), reason="Linux memfd only")
def test_memfd_failure_never_downgrades_to_named_frames(tmp_path, monkeypatch):
    from skeleton.ai.runtime.inference.gguf_private_transport import private_frame
    model, _, _ = fixture(tmp_path)
    def unavailable(*args, **kwargs):
        raise OSError("fixture unavailable")
    monkeypatch.setattr(os, "memfd_create", unavailable)
    with pytest.raises(LlamaCppRuntimeError, match="descriptor"):
        with private_frame(model.runtime_artifact, model.model_artifact, b"SKG1", lambda: None):
            pytest.fail("unexpected downgrade")
