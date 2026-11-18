"""Plan a local llama.cpp/GGUF deployment without loading or executing a model.

Supply reviewed geometry or opt in to supported GGUF metadata extraction.
This tool has no network access, downloads, subprocesses or external providers.
The resulting figures are conservative RAM estimates, not guarantees.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
import os
import stat
from pathlib import Path
from typing import Sequence

from skeleton.ai.runtime.inference.llama_cpp import (
    ConsumerHardwareBudget,
    LlamaCppConfig,
    LlamaCppRuntimeError,
    detect_consumer_hardware_budget,
    estimate_gqa_kv_bytes_per_token,
    inspect_gguf,
    _serving_metadata,
    plan_consumer_llama_cpp,
)

MIB = 1024 ** 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True, help="existing local GGUF model")
    parser.add_argument("--layers", type=int)
    parser.add_argument("--query-heads", type=int)
    parser.add_argument("--kv-heads", type=int)
    parser.add_argument("--key-head-dim", type=int)
    parser.add_argument("--value-head-dim", type=int)
    parser.add_argument("--key-bytes", type=int, default=2, help="actual K KV element width")
    parser.add_argument("--value-bytes", type=int, default=2, help="actual V KV element width")
    parser.add_argument("--auto-geometry", action="store_true", help="read supported dense attention geometry from GGUF")
    parser.add_argument("--context-ladder", type=int, nargs="+", help="additional context targets, estimates only")
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


# Deliberately narrow allowlist: hybrid, recurrent, MLA and unknown models
# cannot be described by the uniform GQA formula solely from these fields.
_AUTO_GQA = frozenset({"llama", "qwen2", "qwen2moe"})
_GEOMETRY_FIELDS = ("layers", "query_heads", "kv_heads", "key_head_dim", "value_head_dim")


def _stat_snapshot(path: Path) -> tuple[int, ...]:
    observed = path.lstat()
    if not stat.S_ISREG(observed.st_mode):
        raise LlamaCppRuntimeError("GGUF planning requires a regular nonsymlink file")
    return (observed.st_dev, observed.st_ino, observed.st_size,
            observed.st_mtime_ns, observed.st_ctime_ns)


def _geometry(args: argparse.Namespace, path: Path, header: object):
    manual = {name: getattr(args, name) for name in _GEOMETRY_FIELDS}
    automatic = getattr(args, "auto_geometry", False)
    if not automatic:
        if any(value is None for value in manual.values()):
            raise ValueError("provide all five geometry fields or --auto-geometry")
        return manual, None, "operator"
    if any(value is not None for value in manual.values()):
        raise ValueError("automatic and manual geometry cannot be mixed")
    metadata = _serving_metadata(path, header)
    if metadata.architecture not in _AUTO_GQA:
        raise LlamaCppRuntimeError("architecture requires explicit reviewed attention geometry")
    heads = metadata.head_count
    key = metadata.key_length
    if key is None and heads and metadata.embedding_length and metadata.embedding_length % heads == 0:
        key = metadata.embedding_length // heads
    values = dict(layers=metadata.block_count, query_heads=heads,
                  kv_heads=metadata.head_count_kv, key_head_dim=key,
                  value_head_dim=metadata.value_length or key)
    # Missing KV head count is not assumed to be MHA; require explicit evidence.
    if any(value is None for value in values.values()) or metadata.context_length is None:
        raise LlamaCppRuntimeError("GGUF lacks complete supported attention geometry")
    return values, metadata.context_length, "gguf_metadata"


def _ladder(args: argparse.Namespace, config: LlamaCppConfig,
            hardware: ConsumerHardwareBudget, model_size: int,
            model_context: int | None) -> list[dict[str, object]]:
    targets = getattr(args, "context_ladder", None) or [args.context]
    if len(targets) > 32 or any(type(t) is not int or not 128 <= t <= 1_048_576 for t in targets):
        raise ValueError("context ladder requires at most 32 targets in [128, 1048576]")
    rows = []
    for target in sorted(set(targets)):
        capped = min(target, model_context) if model_context is not None else target
        try:
            plan = plan_consumer_llama_cpp(
                replace(config, context_size=capped),
                replace(hardware, target_context_tokens=capped), model_bytes=model_size,
            )
        except LlamaCppRuntimeError:
            rows.append({"target_tokens": target, "status": "not_fit"})
            continue
        effective = plan.configuration.context_size
        rows.append({"target_tokens": target, "status": "estimated_fit" if effective == target else "clamped",
                     "context_tokens": effective, "estimated_total_bytes": plan.estimated_total_bytes,
                     "remaining_ram_bytes": hardware.ram_bytes - plan.estimated_total_bytes,
                     "model_context_clamped": capped < target})
    return rows


def plan_from_args(args: argparse.Namespace) -> dict[str, object]:
    path = Path(args.model).expanduser()
    if path.is_symlink():
        raise LlamaCppRuntimeError("refusing symlinked GGUF model path")
    # Planning is advisory, not activation. Reject obvious replacement and
    # symlink ancestry; the canonical runtime still rehashes before dispatch.
    lexical = Path(os.path.abspath(path))
    if lexical.resolve(strict=True) != lexical:
        raise LlamaCppRuntimeError("refusing symlinked GGUF ancestry")
    before = _stat_snapshot(path)
    header = inspect_gguf(path)
    _serving_metadata(path, header).require_single_file(header)
    model_size = before[2]
    geometry, model_context, geometry_source = _geometry(args, path, header)
    if type(args.context) is not int or not 128 <= args.context <= 1_048_576:
        raise ValueError("context outside supported planner bounds")
    effective_target = min(args.context, model_context) if model_context is not None else args.context
    kv_per_token = estimate_gqa_kv_bytes_per_token(
        **geometry,
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
        context_size=effective_target,
        threads=args.threads,
        batch_size=args.batch,
        gpu_layers=args.gpu_layers,
    )
    hardware = detect_consumer_hardware_budget(
        kv_bytes_per_token=kv_per_token,
        target_context_tokens=effective_target,
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
    ladder = _ladder(args, config, hardware, model_size, model_context)
    if _stat_snapshot(path) != before or lexical.resolve(strict=True) != lexical:
        raise LlamaCppRuntimeError("GGUF changed during advisory planning")
    return {
        "schema": "skeleton.consumer-gguf-plan.v1",
        "model": {
            "path": str(path),
            "gguf_version": header.version,
            "bytes": model_size,
            "kv_bytes_per_token": kv_per_token,
            "geometry_source": geometry_source,
            "geometry": geometry,
            "declared_context_tokens": model_context,
        },
        "hardware": {
            "available_ram_bytes": hardware.ram_bytes,
            "physical_cpu_cores": hardware.physical_cpu_cores,
        },
        "admission": {
            "context_tokens": chosen.context_size,
            "context_clamped": chosen.context_size < args.context,
            "requested_context_tokens": args.context,
            "model_context_clamped": effective_target < args.context,
            "decode_threads": chosen.threads,
            "prefill_batch_tokens": chosen.batch_size,
            "gpu_layers": chosen.gpu_layers,
            "reserved_os_ram_bytes": admission.reserved_ram_bytes,
            "reserved_kv_bytes": admission.reserved_kv_bytes,
            "estimated_total_bytes": admission.estimated_total_bytes,
        },
        "context_ladder": ladder,
        "qualification": "advisory_estimate_only",
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
