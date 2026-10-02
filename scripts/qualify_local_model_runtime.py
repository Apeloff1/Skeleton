#!/usr/bin/env python3
"""Qualify an operator-owned standalone local model deployment manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from skeleton.ai.runtime.inference.deployment import (
    LocalModelDeploymentError,
    qualify_local_model_deployment_sync,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--prompt",
        default="Respond with a short offline readiness acknowledgement.",
    )
    parser.add_argument("--max-output-tokens", type=int, default=32)
    args = parser.parse_args(argv)
    try:
        receipt = qualify_local_model_deployment_sync(
            args.manifest,
            prompt=args.prompt,
            max_output_tokens=args.max_output_tokens,
        )
    except (LocalModelDeploymentError, OSError, ValueError, TypeError) as exc:
        print(f"Local model qualification rejected: {exc}", file=sys.stderr)
        return 2
    encoded = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
