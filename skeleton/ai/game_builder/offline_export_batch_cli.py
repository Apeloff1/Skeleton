"""Operator-only read-only verification of a pinned offline game export batch."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .offline_export_batch import OfflineBatchVerificationError, verify_export_batch


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, help="Batch root containing batch.json")
    parser.add_argument("--expected-index-sha256", required=True,
                        help="Independent SHA-256 pin for canonical batch.json")
    parser.add_argument("--trusted-local-operator", action="store_true")
    args = parser.parse_args(argv)
    try:
        receipt = verify_export_batch(
            args.root, expected_index_sha256=args.expected_index_sha256,
            authorized=args.trusted_local_operator,
        )
    except (OfflineBatchVerificationError, PermissionError, OSError) as exc:
        print(json.dumps({
            "verified": False, "error": type(exc).__name__,
            "reason": str(exc)[:200],
        }, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main"]
