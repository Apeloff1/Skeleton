"""Explicit operator-initiated real-model generation smoke (no mock fallback).

This CLI loads verified installed model bytes, calls a real local llama.cpp
backend, records usage and SHA receipts, and exits. A successful answer is
NOT a benchmark, alignment evaluation, or device/release qualification.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import sys

from .service import activate_model, load_approved_manifest
from .selftest import live_smoke
from ...deployment.install.doctor import inspect_installed_model


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline verified GGUF live generation smoke")
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--context-tokens", type=int, default=2048)
    parser.add_argument("--new-tokens", type=int, default=16)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--gpu-layers", type=int, default=0)
    args = parser.parse_args(argv)
    try:
        installed = inspect_installed_model(args.model_root)
        manifest = load_approved_manifest(args.model_root)
        if installed.model_sha256 != manifest.model_sha256:
            raise ValueError("installed model and manifest disagree")
        with ExitStack() as stack:
            backend = stack.enter_context(activate_model(args.model_root, manifest,
                n_ctx=args.context_tokens, n_threads=args.threads,
                n_gpu_layers=args.gpu_layers))
            result = live_smoke(backend, max_new_tokens=args.new_tokens)
        print(json.dumps(result | {"release_certified": False,
                                   "quality_certified": False,
                                   "real_native_backend": True}, sort_keys=True))
        return 0
    except (RuntimeError, ValueError, OSError, ImportError) as exc:
        # No prompt, private path or traceback from the model reaches stdout.
        print(json.dumps({"status": "blocked", "reason": type(exc).__name__}),
              file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
