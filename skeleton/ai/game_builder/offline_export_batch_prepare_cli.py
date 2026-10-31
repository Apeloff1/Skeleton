"""Trusted local authoring of a non-overwriting offline game cohort index."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .offline_export_batch import OfflineBatchVerificationError
from .offline_export_batch_prepare import prepare_export_batch


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--package", action="append", required=True,
                        metavar="PROJECT_ID:PACKAGE_DIR:RELEASE_SHA256",
                        help="Independently pinned original exported game")
    parser.add_argument("--trusted-local-operator", action="store_true")
    args = parser.parse_args(argv)
    try:
        entries = []
        for item in args.package:
            parts = item.split(":")
            if len(parts) != 3:
                raise OfflineBatchVerificationError("package requires ID:DIR:PIN")
            entries.append({
                "project_id": parts[0],
                "package_dir": parts[1],
                "release_sha256": parts[2],
            })
        receipt = prepare_export_batch(
            args.root, entries=entries, authorized=args.trusted_local_operator,
        )
    except (OfflineBatchVerificationError, PermissionError, OSError) as exc:
        print(json.dumps({
            "prepared": False, "error": type(exc).__name__,
            "reason": str(exc)[:200],
        }, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main"]
