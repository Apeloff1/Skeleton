"""Make a tiny deterministic native checkpoint for installer integration tests.

NOT a trained language model, not an AI quality benchmark, and never bundled
as assistant weights. This fixture verifies frozen local inference wiring.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.runtime.inference.artifact import write_local_model_artifact
from skeleton.ai.runtime.inference.native_runtime import NativeRuntimeLocalModel
from skeleton.cortex.transformer import TinyTransformer


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if not args.output.parent.is_dir() or args.output.exists():
        parser.error("output must be a new file in an existing directory")
    model = TinyTransformer(
        vocab=("system:", "user:", "assistant:", "hello", "world", "answer"),
        dim=8, ctx=64, seed=41, n_heads=2, n_layers=2, d_ff=16,
    )
    receipt = write_local_model_artifact(
        NativeRuntimeLocalModel(NativeLLMRuntime(model)), args.output,
    )
    if receipt.model_digest == "" or args.output.stat().st_size == 0:
        raise RuntimeError("offline test checkpoint was not written correctly")
    print("Synthetic installer-acceptance checkpoint created")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
