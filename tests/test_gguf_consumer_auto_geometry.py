"""Advisory auto-geometry and context ceiling regressions."""
import struct

import pytest

from scripts.plan_consumer_gguf import build_parser, plan_from_args
from skeleton.ai.runtime.inference.llama_cpp import LlamaCppRuntimeError


def _string(value):
    encoded = value.encode()
    return struct.pack("<Q", len(encoded)) + encoded


def _model(path, architecture="llama", *, omit=None, context=1024):
    fields = {"general.architecture": architecture,
              f"{architecture}.context_length": context,
              f"{architecture}.embedding_length": 2048,
              f"{architecture}.block_count": 16,
              f"{architecture}.attention.head_count": 16,
              f"{architecture}.attention.head_count_kv": 4}
    if omit:
        fields.pop(f"{architecture}.{omit}")
    payload = bytearray(struct.pack("<4sIQQ", b"GGUF", 3, 1, len(fields)))
    for name, value in fields.items():
        payload += _string(name)
        if isinstance(value, str):
            payload += struct.pack("<I", 8) + _string(value)
        else:
            payload += struct.pack("<II", 4, value)
    path.write_bytes(payload + bytes(2048))
    return path


def _args(path, *extra):
    return build_parser().parse_args([
        "--model", str(path), "--auto-geometry", "--ram-mib", "1024",
        "--cpu-cores", "2", "--reserve-mib", "0", "--scratch-mib", "0",
        "--context", "4096", *extra,
    ])


def test_auto_geometry_clamps_to_native_context(tmp_path):
    path = _model(tmp_path / "model.gguf")
    result = plan_from_args(_args(path, "--context-ladder", "512", "1024", "4096", "512"))
    assert result["qualification"] == "advisory_estimate_only"
    assert result["model"]["geometry_source"] == "gguf_metadata"
    assert result["model"]["kv_bytes_per_token"] == 32768
    assert result["admission"]["context_tokens"] == 1024
    assert result["admission"]["model_context_clamped"]
    assert [row["status"] for row in result["context_ladder"]] == [
        "estimated_fit", "estimated_fit", "clamped",
    ]


@pytest.mark.parametrize("architecture", ["deepseek2", "qwen3next", "mamba", "clip"])
def test_unknown_or_nonuniform_attention_demands_manual_geometry(tmp_path, architecture):
    path = _model(tmp_path / "model.gguf", architecture)
    with pytest.raises(LlamaCppRuntimeError, match="explicit reviewed"):
        plan_from_args(_args(path))


@pytest.mark.parametrize("field", ["attention.head_count_kv", "context_length", "block_count"])
def test_missing_geometry_not_guessed(tmp_path, field):
    path = _model(tmp_path / "model.gguf", omit=field)
    with pytest.raises(LlamaCppRuntimeError, match="lacks complete"):
        plan_from_args(_args(path))


def test_mixed_manual_and_automatic_rejected(tmp_path):
    path = _model(tmp_path / "model.gguf")
    with pytest.raises(ValueError, match="cannot be mixed"):
        plan_from_args(_args(path, "--layers", "16"))


def test_ladder_is_bounded(tmp_path):
    path = _model(tmp_path / "model.gguf")
    with pytest.raises(ValueError, match="context ladder"):
        plan_from_args(_args(path, "--context-ladder", "127"))


def test_symlinked_ancestor_rejected(tmp_path):
    directory = tmp_path / "real"
    directory.mkdir()
    _model(directory / "model.gguf")
    alias = tmp_path / "alias"
    alias.symlink_to(directory, target_is_directory=True)
    with pytest.raises(LlamaCppRuntimeError, match="symlinked"):
        plan_from_args(_args(alias / "model.gguf"))


def test_manual_mode_requires_all_fields(tmp_path):
    path = _model(tmp_path / "model.gguf")
    args = _args(path)
    args.auto_geometry = False
    with pytest.raises(ValueError, match="all five"):
        plan_from_args(args)
