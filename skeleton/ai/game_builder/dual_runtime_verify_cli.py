"""Read-only operator verification of an existing offline original game export."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .dual_runtime_verify import (
    DualRuntimeVerificationError, verify_exported_package,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--trusted-local-operator", action="store_true")
    args = parser.parse_args(argv)
    try:
        receipt = verify_exported_package(
            args.package,
            expected_manifest_sha256=args.expected_manifest_sha256,
            authorized=args.trusted_local_operator,
        )
    except (DualRuntimeVerificationError, PermissionError, OSError) as exc:
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
