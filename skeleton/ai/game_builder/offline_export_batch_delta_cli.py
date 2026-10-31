"""Offline source-bound comparison of two independently pinned game cohorts."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .offline_export_batch import OfflineBatchVerificationError
from .offline_export_batch_delta import compare_export_batches


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--left-root", required=True)
    parser.add_argument("--left-index-sha256", required=True)
    parser.add_argument("--right-root", required=True)
    parser.add_argument("--right-index-sha256", required=True)
    parser.add_argument("--trusted-local-operator", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = compare_export_batches(
            args.left_root, args.right_root,
            left_index_sha256=args.left_index_sha256,
            right_index_sha256=args.right_index_sha256,
            authorized=args.trusted_local_operator,
        )
    except (OfflineBatchVerificationError, PermissionError, OSError) as exc:
        print(json.dumps({
            "verified": False, "error": type(exc).__name__,
            "reason": str(exc)[:200],
        }, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main"]
