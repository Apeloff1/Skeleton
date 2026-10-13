"""Plan a local llama.cpp/GGUF deployment without loading or executing a model.

All attention geometry must be provided from the model's published metadata.
This tool has no network access, downloads, subprocesses or external providers.
The resulting figures are conservative RAM estimates, not guarantees.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
from typing import Sequence

from skeleton.ai.runtime.inference.llama_cpp import (
    ConsumerHardwareBudget,
    LlamaCppConfig,
    LlamaCppRuntimeError,
    detect_consumer_hardware_budget,
    estimate_gqa_kv_bytes_per_token,
    inspect_gguf,
    plan_consumer_llama_cpp,
)

MIB = 1024 ** 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True, help="existing local GGUF model")
    parser.add_argument("--layers", type=int, required=True)
    parser.add_argument("--query-heads", type=int, required=True)
    parser.add_argument("--kv-heads", type=int, required=True)
    parser.add_argument("--key-head-dim", type=int, required=True)
    parser.add_argument("--value-head-dim", type=int, required=True)
    parser.add_argument("--key-bytes", type=int, default=2, help="actual K KV element width")
    parser.add_argument("--value-bytes", type=int, default=2, help="actual V KV element width")
    parser.add_argument("--context", type=int, default=4096)
    parser.add_argument("--threads", type=int)
    parser.add_argument("--batch", type=int)
    parser.add_argument("--gpu-layers", type=int, default=0)
    parser.add_argument("--ram-mib", type=int, help="available, not total machine RAM")
    parser.add_argument("--cpu-cores", type=int, help="known physical core count")
    parser.add_argument("--reserve-mib", type=int, default=512)
    parser.add_argument("--scratch-mib", type=int, default=512)
    parser.add_argument("--prefill-batch", type=int, default=256)
    parser.add_argument("--max-threads", type=int, default=16)
    return parser


def plan_from_args(args: argparse.Namespace) -> dict[str, object]:
    path = Path(args.model).expanduser()
    if path.is_symlink():
        raise LlamaCppRuntimeError("refusing symlinked GGUF model path")
    header = inspect_gguf(path)
    model_size = path.stat().st_size
    kv_per_token = estimate_gqa_kv_bytes_per_token(
        layers=args.layers,
        query_heads=args.query_heads,
        kv_heads=args.kv_heads,
        key_head_dim=args.key_head_dim,
        value_head_dim=args.value_head_dim,
        key_bytes_per_element=args.key_bytes,
        value_bytes_per_element=args.value_bytes,
    )
    for name in ("reserve_mib", "scratch_mib", "prefill_batch", "max_threads"):
        value = getattr(args, name)
        if isinstance(value, bool) or not isinstance(value, int) or (
            value < 0 if name in {"reserve_mib", "scratch_mib"} else value <= 0
        ):
            raise ValueError(f"{name} must be a bounded non-negative/positive integer")

    # The executable is only a configuration placeholder. No executable is
    # discovered or launched while planning, and it is never downloaded.
    config = LlamaCppConfig(
        executable="llama-cli",
        model_path=str(path),
        context_size=args.context,
        threads=args.threads,
        batch_size=args.batch,
        gpu_layers=args.gpu_layers,
    )
    hardware = detect_consumer_hardware_budget(
        kv_bytes_per_token=kv_per_token,
        target_context_tokens=args.context,
        available_ram_bytes=args.ram_mib * MIB if args.ram_mib is not None else None,
        physical_cpu_cores=args.cpu_cores,
    )
    hardware = replace(
        hardware,
        reserve_bytes=args.reserve_mib * MIB,
        runtime_scratch_bytes=args.scratch_mib * MIB,
        max_decode_threads=args.max_threads,
        prefill_batch_tokens=args.prefill_batch,
    )
    admission = plan_consumer_llama_cpp(
        config, hardware, model_bytes=model_size
    )
    chosen = admission.configuration
    return {
        "schema": "skeleton.consumer-gguf-plan.v1",
        "model": {
            "path": str(path),
            "gguf_version": header.version,
            "bytes": model_size,
            "kv_bytes_per_token": kv_per_token,
        },
        "hardware": {
            "available_ram_bytes": hardware.ram_bytes,
            "physical_cpu_cores": hardware.physical_cpu_cores,
        },
        "admission": {
            "context_tokens": chosen.context_size,
            "context_clamped": admission.context_clamped,
            "decode_threads": chosen.threads,
            "prefill_batch_tokens": chosen.batch_size,
            "gpu_layers": chosen.gpu_layers,
            "reserved_os_ram_bytes": admission.reserved_ram_bytes,
            "reserved_kv_bytes": admission.reserved_kv_bytes,
            "estimated_total_bytes": admission.estimated_total_bytes,
        },
        "notes": (
            "Conservative RAM-only estimate; GPU VRAM, runtime allocator "
            "overheads and backing-file mappings require separate verification"
        ),
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = plan_from_args(args)
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
