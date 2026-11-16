"""Explicit local operator interface for multi-cohort replay qualification."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .offline_portfolio import PortfolioBudget, PortfolioError, verify_portfolio
from .offline_receipt_publication import (
    ReceiptPublicationError, preflight_receipt_destination, publish_verified_receipt,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--expected-index-sha256", required=True)
    parser.add_argument("--trusted-local-operator", action="store_true")
    parser.add_argument("--max-cohorts", type=int, default=64)
    parser.add_argument("--max-packages", type=int, default=2048)
    parser.add_argument("--max-verified-bytes", type=int,
                        default=PortfolioBudget().verified_bytes)
    parser.add_argument("--receipt-output")
    args = parser.parse_args(argv)
    try:
        budget = PortfolioBudget(args.max_cohorts, args.max_packages, args.max_verified_bytes)
        if args.receipt_output:
            preflight_receipt_destination(args.receipt_output,
                protected_roots=(args.root,), authorized=args.trusted_local_operator)
        result = verify_portfolio(args.root, expected_index_sha256=args.expected_index_sha256,
                                  authorized=args.trusted_local_operator, budget=budget)
        if args.receipt_output:
            publish_verified_receipt(result, args.receipt_output,
                protected_roots=(args.root,), authorized=args.trusted_local_operator)
    except (PortfolioError, ReceiptPublicationError, PermissionError, OSError) as exc:
        print(json.dumps({"verified": False, "error": type(exc).__name__}), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
