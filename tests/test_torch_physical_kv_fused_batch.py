"""Real Torch CPU fixtures; optional CUDA fixture is never counted as mandatory GPU evidence."""
import pytest

torch = pytest.importorskip("torch")

from skeleton.cortex.transformer import TinyTransformer
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.runtime_contracts import (
    BatchGenerationRequest, DevicePolicy, GenerationConfig, RuntimeContractError,
)


def runtime(device="torch-cpu"):
    model = TinyTransformer({"a", "b", "c"}, dim=8, ctx=8, n_heads=2, n_layers=2, d_ff=12, seed=2)
    return NativeLLMRuntime(model, device_policy=DevicePolicy(requested=device, allow_fallback=False))


@pytest.mark.parametrize("device", ["torch-cpu", pytest.param("cuda", marks=pytest.mark.skipif(
    not torch.cuda.is_available(), reason="CUDA unavailable"))])
def test_physical_kv_offload_restore(device):
    rt = runtime(device)
    accel = rt.model._accel
    first = accel.logits_window([1, 2, 3])
    before = accel.kv_reserved_bytes
    receipt = accel.offload_decode_cache("tenant-A/session", max_host_bytes=1024**2,
                                          require_gpu=device == "cuda")
    assert receipt["resident_bytes"] == 0 and receipt["released_resident_bytes"] == before
    assert accel.host_kv_bytes == receipt["host_bytes"] > 0
    with pytest.raises(PermissionError):
        accel.restore_decode_cache(receipt["lease"], "other", max_device_bytes=1024**2)
    restored = accel.restore_decode_cache(receipt["lease"], "tenant-A/session", max_device_bytes=1024**2)
    assert restored["tokens"] == 3 and restored["remaining_host_bytes"] == 0
    assert accel.logits_window([1, 2, 3]) == first
    with pytest.raises(PermissionError):
        accel.restore_decode_cache(receipt["lease"], "tenant-A/session", max_device_bytes=1024**2)
    reference = accel.logits([1, 2, 3, 1])
    assert accel.logits_window([1, 2, 3, 1]) == pytest.approx(reference, abs=1e-5)


def test_host_byte_limit_preserves_active_cache():
    accel = runtime().model._accel
    accel.logits_window([1, 2])
    with pytest.raises(MemoryError):
        accel.offload_decode_cache("scope", max_host_bytes=1, require_gpu=False)
    assert accel.cached_tokens == (1, 2) and accel.host_kv_bytes == 0


@pytest.mark.parametrize("device", ["torch-cpu", pytest.param("cuda", marks=pytest.mark.skipif(
    not torch.cuda.is_available(), reason="CUDA unavailable"))])
def test_batched_gpu_tensor_graph_matches_serial_rows(device):
    accel = runtime(device).model._accel
    windows = [[1, 2, 3], [3, 2, 1]]
    actual = accel.logits_fused_batch(windows, max_workspace_bytes=1024**2, require_gpu=device == "cuda")
    for row, window in zip(actual, windows):
        assert row == pytest.approx(accel.logits(window), abs=1e-5)
    assert accel.cached_tokens == ()
    with pytest.raises(MemoryError):
        accel.logits_fused_batch(windows, max_workspace_bytes=1, require_gpu=device == "cuda")


def test_fused_generation_produces_canonical_results():
    rt = runtime()
    config = GenerationConfig(max_new_tokens=2, temperature=0, use_cache=False)
    reqs = [BatchGenerationRequest("first", "a b", config),
            BatchGenerationRequest("second", "b a", config)]
    serial = rt.generate_batch(reqs)
    fused = rt.generate_fused_batch(reqs, max_workspace_bytes=1024**2, require_gpu=False)
    assert [r.request_id for r in fused] == ["first", "second"]
    assert [r.result.generated_ids for r in fused] == [r.result.generated_ids for r in serial]
    assert [r.result.output_digest for r in fused] == [r.result.output_digest for r in serial]
    with pytest.raises(RuntimeContractError, match="cannot fall back"):
        rt.generate_fused_batch(reqs, max_workspace_bytes=1024**2)

@pytest.mark.skipif(__import__("os").name != "posix", reason="POSIX encrypted spill custody")
def test_encrypted_disk_spill_and_restore(tmp_path):
    from cryptography.exceptions import InvalidTag
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    accel = runtime().model._accel
    original = accel.logits_window([1, 2, 3])
    lease = accel.offload_decode_cache("scope", max_host_bytes=1024**2, require_gpu=False)["lease"]
    with pytest.raises(MemoryError):
        accel.spill_host_kv(lease, "scope", root, max_disk_bytes=1)
    written = accel.spill_host_kv(lease, "scope", root, max_disk_bytes=1024**2)
    assert written["remaining_host_bytes"] == 0 and accel.disk_kv_bytes > 0
    path = next(root.iterdir())
    assert path.stat().st_size == written["disk_bytes"]
    encrypted = path.read_bytes()
    path.write_bytes(encrypted[:-1] + bytes([encrypted[-1] ^ 1]))
    with pytest.raises(InvalidTag):
        accel.reload_disk_kv(lease, "scope", max_host_bytes=1024**2)
    assert accel.host_kv_bytes == 0 and accel.disk_kv_bytes == written["disk_bytes"]
    path.write_bytes(encrypted)
    loaded = accel.reload_disk_kv(lease, "scope", max_host_bytes=1024**2)
    assert loaded["remaining_disk_bytes"] == 0 and not list(root.iterdir())
    accel.restore_decode_cache(lease, "scope", max_device_bytes=1024**2)
    assert accel.logits_window([1, 2, 3]) == original
