"""Run repeated actual native llama.cpp batches from an explicitly pinned local deployment."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from skeleton.ai.runtime.inference.deployment import LocalModelDeployment
from skeleton.ai.runtime.inference.llama_cpp import LlamaCppModel
from skeleton.ai.runtime.inference.resident_gguf_batch import ResidentBatchPolicy, ResidentGGUFBatch


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--manifest-sha256", required=True)
    p.add_argument("--server", type=Path, required=True)
    p.add_argument("--server-sha256", required=True)
    p.add_argument("--server-library", action="append", default=[], metavar="NAME=SHA256")
    p.add_argument("--prompt-file", type=Path, action="append", required=True)
    p.add_argument("--spill-root", type=Path)
    p.add_argument("--slot-spill-bytes", type=int, default=0)
    p.add_argument("--spill-roundtrip", action="store_true")
    p.add_argument("--slots", type=int, default=2)
    p.add_argument("--context-per-slot", type=int, required=True)
    p.add_argument("--gpu-layers", type=int, required=True)
    p.add_argument("--max-memory-bytes", type=int, required=True)
    p.add_argument("--flash-attention", choices=("auto","on","off"), default="auto")
    p.add_argument("--prefill-threads", type=int)
    p.add_argument("--numa", choices=("distribute","isolate","numactl"))
    p.add_argument("--split-mode", choices=("none","layer","row"))
    p.add_argument("--tensor-split", type=int, nargs="+", default=[])
    p.add_argument("--main-gpu", type=int)
    p.add_argument("--cpu-moe-layers", type=int, default=0)
    p.add_argument("--moe-cache-mib", type=int, default=0)
    p.add_argument("--cpu-ffn-layers", type=int, default=0)
    p.add_argument("--batch-tokens", type=int, default=512)
    p.add_argument("--microbatch-tokens", type=int, default=128)
    p.add_argument("--max-new-tokens", type=int, default=32)
    p.add_argument("--repeats", type=int, choices=(1,2,3), default=2)
    a = p.parse_args(argv)
    deployment = LocalModelDeployment.load(a.manifest, expected_sha256=a.manifest_sha256)
    model = LlamaCppModel(deployment.llama_cpp_config(rehash_artifacts_each_run=True))
    if model.model_digest != deployment.execution_model_sha256:
        raise RuntimeError("manifest model identity changed")
    if not 2 <= len(a.prompt_file) <= a.slots:
        p.error("2..slots prompt files required")
    prompts = []
    for source in a.prompt_file:
        if source.is_symlink() or not source.is_file():
            p.error("regular local prompt files required")
        with source.open("rb") as handle:
            raw = handle.read(1024**2+1)
        if not 1 <= len(raw) <= 1024**2:
            p.error("prompt file outside bounds")
        prompts.append(raw.decode("utf-8"))
    if a.spill_roundtrip and not a.slot_spill_bytes:
        p.error("spill roundtrip requires explicit private spill configuration")
    policy = ResidentBatchPolicy(a.slots, a.context_per_slot, a.gpu_layers,
                                 a.max_memory_bytes, flash_attention=a.flash_attention,
                                 slot_spill_bytes=a.slot_spill_bytes,
                                 prefill_threads=a.prefill_threads, numa=a.numa,
                                 split_mode=a.split_mode, tensor_split=tuple(a.tensor_split),
                                 main_gpu=a.main_gpu, cpu_moe_layers=a.cpu_moe_layers,
                                 moe_cache_mib=a.moe_cache_mib, cpu_ffn_layers=a.cpu_ffn_layers,
                                 batch_tokens=a.batch_tokens, microbatch_tokens=a.microbatch_tokens)
    with ResidentGGUFBatch(model, a.server, a.server_sha256, policy,
                           runtime_libraries=tuple(tuple(item.split("=",1)) for item in a.server_library),
                           spill_root=a.spill_root) as session:
        for iteration in range(a.repeats):
            print(json.dumps(session.generate(prompts, max_new_tokens=a.max_new_tokens,
                reuse_cache=a.spill_roundtrip and iteration > 0), allow_nan=False))
            if a.spill_roundtrip:
                print(json.dumps(session.spill_slot(0), allow_nan=False))
                print(json.dumps(session.restore_slot(0), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
