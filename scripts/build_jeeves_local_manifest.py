#!/usr/bin/env python3
"""Pin an existing owned llama.cpp executable + GGUF as Jeeves's ONLY model.

Jeeves is the application-facing deployment identity. The weight source
remains the actual supplied GGUF; this does NOT train, rename or certify
new foundation-model weights. Model and executable are hashed and validated
by the existing canonical deployment authority. No download/network work.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skeleton.ai.runtime.inference.deployment import (
    LocalModelDeployment,
    LocalModelDeploymentError,
    create_local_model_deployment,
)


def prepare_manifest(
    destination: Path,
    *,
    executable: Path,
    model: Path,
    profile: str = "qwen3-completion-chat",
    context_size: int = 4096,
    threads: int | None = None,
    gpu_layers: int = 0,
) -> dict[str, object]:
    """Publish one create-only pin; re-read it from canonical custody."""
    if profile not in ("raw", "llama-completion-chat", "qwen3-completion-chat"):
        raise ValueError("Jeeves requires an explicitly supported local text generation profile")
    destination = destination.expanduser().absolute()
    if destination.exists() or destination.is_symlink():
        raise LocalModelDeploymentError("Jeeves model manifest already exists; choose another name")
    prepared = create_local_model_deployment(
        destination,
        executable_path=executable,
        model_path=model,
        model_id="jeeves",
        context_size=context_size,
        threads=threads,
        gpu_layers=gpu_layers,
        runtime_profile=profile,
    )
    loaded = LocalModelDeployment.load(destination)
    if (
        loaded.model_id != "jeeves" or loaded.model_sha256 != prepared.model_sha256
        or loaded.executable_sha256 != prepared.executable_sha256
        or loaded.manifest_digest != prepared.manifest_digest
    ):
        raise LocalModelDeploymentError("Jeeves manifest did not retain its pinned model/runtime identity")
    return {
        "ok": True,
        "model_id": "jeeves",
        "provider": "local",
        "manifest": str(destination),
        "manifest_sha256": loaded.manifest_digest,
        "model_sha256": loaded.model_sha256,
        "runtime_sha256": loaded.executable_sha256,
        "network_required": False,
        "inference_verified": False,
        "underlying_weights_retrained": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True, help="existing owned and licensed GGUF")
    parser.add_argument("--executable", type=Path, required=True, help="existing local llama.cpp CLI executable")
    parser.add_argument("--output", type=Path, required=True, help="new manifest file in an existing private model directory")
    parser.add_argument(
        "--profile", choices=("raw", "llama-completion-chat", "qwen3-completion-chat"),
        default="qwen3-completion-chat", help="verified local prompt protocol (Qwen3 by default)",
    )
    parser.add_argument("--context", type=int, default=4096)
    parser.add_argument("--threads", type=int)
    parser.add_argument("--gpu-layers", type=int, default=0)
    args = parser.parse_args(argv)
    try:
        result = prepare_manifest(
            args.output, executable=args.executable, model=args.model,
            profile=args.profile, context_size=args.context,
            threads=args.threads, gpu_layers=args.gpu_layers,
        )
    except (OSError, ValueError, TypeError, LocalModelDeploymentError):
        # Filesystem exception messages may contain private paths; redact.
        print(json.dumps({"ok": False, "error": "The supplied local model/runtime files could not be safely pinned."}), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
