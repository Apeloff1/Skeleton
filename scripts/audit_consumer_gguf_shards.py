"""Operator-only split GGUF artifact audit (no inference)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from skeleton.ai.runtime.inference.gguf_bundle import (
    audit_bundle, _open_directory, _open_file, _identity,
)
from skeleton.ai.runtime.inference.llama_cpp import LlamaCppRuntimeError

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first", type=Path, required=True)
    parser.add_argument("--sha256", action="append", required=True, help="one ordered pin per shard")
    parser.add_argument("--max-bytes", type=int, required=True)
    args = parser.parse_args(argv)
    try:
        result = audit_bundle(args.first, args.sha256, max_bytes=args.max_bytes)
    except (OSError, ValueError, LlamaCppRuntimeError):
        parser.exit(2, "GGUF shard audit rejected: custody, metadata or capacity mismatch\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
