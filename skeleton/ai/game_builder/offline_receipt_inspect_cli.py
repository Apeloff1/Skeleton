"""Inspect an independently pinned canonical offline game verification receipt."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .offline_receipt_inspection import ReceiptInspectionError, inspect_verified_receipt


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--trusted-local-operator", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = inspect_verified_receipt(
            args.receipt, expected_sha256=args.expected_sha256,
            authorized=args.trusted_local_operator,
        )
    except (ReceiptInspectionError, PermissionError, OSError) as exc:
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
