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
    p.add_argument("--prompt", action="append", required=True)
    p.add_argument("--slots", type=int, default=2)
    p.add_argument("--context-per-slot", type=int, required=True)
    p.add_argument("--gpu-layers", type=int, required=True)
    p.add_argument("--max-memory-bytes", type=int, required=True)
    p.add_argument("--flash-attention", choices=("auto","on","off"), default="auto")
    p.add_argument("--max-new-tokens", type=int, default=32)
    p.add_argument("--repeats", type=int, choices=(1,2,3), default=2)
    a = p.parse_args(argv)
    deployment = LocalModelDeployment.load(a.manifest, expected_sha256=a.manifest_sha256)
    model = LlamaCppModel(deployment.llama_cpp_config(rehash_artifacts_each_run=True))
    if model.model_digest != deployment.execution_model_sha256:
        raise RuntimeError("manifest model identity changed")
    policy = ResidentBatchPolicy(a.slots, a.context_per_slot, a.gpu_layers,
                                 a.max_memory_bytes, flash_attention=a.flash_attention)
    with ResidentGGUFBatch(model, a.server, a.server_sha256, policy,
                           runtime_libraries=tuple(tuple(item.split("=",1)) for item in a.server_library)) as session:
        for _ in range(a.repeats):
            print(json.dumps(session.generate(a.prompt, max_new_tokens=a.max_new_tokens), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
