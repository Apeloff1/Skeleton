"""Synthetic split GGUF metadata and real filesystem custody, no native weights."""
import hashlib
import os
import struct

import pytest

from scripts.audit_consumer_gguf_shards import audit_bundle
from skeleton.ai.runtime.inference.llama_cpp import (
    LlamaCppRuntimeError, inspect_gguf, _serving_metadata,
)


def string(value):
    encoded = value.encode()
    return struct.pack("<Q", len(encoded)) + encoded


def shard(path, ordinal, *, count=2, total=3, declared=1):
    fields = [("split.no", 2, ordinal), ("split.count", 2, count),
              ("split.tensors.count", 5, total)]
    payload = bytearray(struct.pack("<4sIQQ", b"GGUF", 3, declared, len(fields)))
    for key, kind, value in fields:
        payload += string(key) + struct.pack("<I", kind)
        payload += struct.pack("<H" if kind == 2 else "<i", value)
    path.write_bytes(payload + bytes(256))
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def pair(tmp_path):
    first = tmp_path / "model-00001-of-00002.gguf"
    second = tmp_path / "model-00002-of-00002.gguf"
    pins = [shard(first, 0), shard(second, 1, declared=2)]
    return first, second, pins


@pytest.mark.skipif(os.name != "posix", reason="descriptor custody is POSIX only")
def test_full_bundle_verified_but_never_activated(pair):
    first, second, pins = pair
    report = audit_bundle(first, pins, max_bytes=4096)
    assert report["activation_authorized"] is False
    assert report["tensor_count"] == 3
    assert report["total_bytes"] == first.stat().st_size + second.stat().st_size
    assert [row["sha256"] for row in report["shards"]] == pins
    assert str(first.parent) not in str(report)


def test_single_file_runtime_denies_split(pair):
    first, _, _ = pair
    header = inspect_gguf(first)
    with pytest.raises(LlamaCppRuntimeError, match="whole-bundle"):
        _serving_metadata(first, header).require_single_file(header)


@pytest.mark.skipif(os.name != "posix", reason="descriptor custody is POSIX only")
@pytest.mark.parametrize("fault", ["digest", "ordinal", "total", "count", "symlink", "hardlink", "budget"])
def test_reject_untrusted_bundle(pair, fault):
    first, second, pins = pair
    budget = 4096
    if fault == "digest":
        pins[1] = "a" * 64
    elif fault == "ordinal":
        pins[1] = shard(second, 0, declared=2)
    elif fault == "total":
        pins[1] = shard(second, 1, declared=2, total=4)
    elif fault == "count":
        pins[1] = shard(second, 1, declared=2, count=3)
    elif fault == "symlink":
        source = second.with_suffix(".real")
        second.rename(source)
        second.symlink_to(source)
    elif fault == "hardlink":
        os.link(second, second.with_suffix(".alias"))
    else:
        budget = first.stat().st_size
    with pytest.raises((ValueError, OSError, LlamaCppRuntimeError)):
        audit_bundle(first, pins, max_bytes=budget)

@pytest.mark.skipif(os.name != "posix", reason="native split custody POSIX only")
def test_native_split_dispatch_uses_first_path_and_full_identity(pair, tmp_path):
    import sys
    import threading
    from skeleton.ai.runtime.inference.llama_cpp import LlamaCppConfig, LlamaCppModel
    from skeleton.ai.runtime.inference.gguf_bundle import split_identity
    from skeleton.ai.runtime.inference.local import LocalInferenceRequest
    first, second, pins = pair
    first.parent.chmod(0o700)
    executable = tmp_path / "fixture-cli"
    # Child verifies companion visibility. Synthetic fixture, not llama.cpp.
    executable.write_text(f"#!{sys.executable}\nimport pathlib,sys\np=pathlib.Path(sys.argv[sys.argv.index('-m')+1])\nassert p.with_name(p.name.replace('00001-of','00002-of')).is_file()\nprint('OK',end='')\n")
    executable.chmod(0o700)
    model = LlamaCppModel(LlamaCppConfig(executable=str(executable), model_path=str(first),
        context_size=128, rehash_artifacts_each_run=True, model_shard_sha256=tuple(pins)))
    assert model.model_digest == split_identity(pins)
    assert model.total_model_bytes == first.stat().st_size + second.stat().st_size
    assert model.infer(LocalInferenceRequest(prompt="test", max_output_tokens=8),
                       threading.Event()).text == "OK"
    second.write_bytes(second.read_bytes() + b"tamper")
    with pytest.raises((ValueError, OSError, LlamaCppRuntimeError)):
        model.assert_identity()


@pytest.mark.skipif(os.name != "posix", reason="native split custody POSIX only")
def test_native_split_requires_private_directory(pair):
    from skeleton.ai.runtime.inference.gguf_bundle import admit_native_bundle
    first, _, pins = pair
    first.parent.chmod(0o755)
    try:
        with pytest.raises(PermissionError, match="owner-private"):
            admit_native_bundle(first, pins)
    finally:
        first.parent.chmod(0o700)
