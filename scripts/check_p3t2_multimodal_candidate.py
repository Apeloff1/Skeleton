#!/usr/bin/env python3
"""Validate the multimodal P3-T2 implementation candidate without granting closure."""

from __future__ import annotations

import argparse
import json
import sys

try:
    from scripts.p3t2_candidate_common import MULTIMODAL, P3T2CandidateError, ROOT, validate_candidate
except ModuleNotFoundError:  # direct script execution
    from p3t2_candidate_common import MULTIMODAL, P3T2CandidateError, ROOT, validate_candidate


def validate(root=ROOT, *, head=None):
    return validate_candidate(MULTIMODAL, root, head=head)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--head")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = validate(ROOT, head=args.head)
    except P3T2CandidateError as exc:
        print("multimodal P3-T2 candidate: FAIL: " + str(exc), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print("multimodal P3-T2 candidate: OK (implementation candidate; no closure authority)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
