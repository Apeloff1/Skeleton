#!/usr/bin/env python3
"""Build and optionally self-test Skeleton's local Assembly accelerator."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from skeleton.native import AsmVectorAccelerator


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--cc", default=None, help="compiler command; defaults to $CC or cc")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    preflight = AsmVectorAccelerator.preflight(
        compiler=args.cc,
        cache_dir=args.output_dir,
    )
    library = AsmVectorAccelerator.build(
        output_dir=args.output_dir,
        compiler=args.cc,
    )
    payload: dict[str, object] = {
        "architecture": preflight.architecture,
        "compiler": preflight.compiler,
        "library": str(library),
        "abi_version": 1,
        "self_test": "not-requested",
    }

    if args.self_test:
        accelerator = AsmVectorAccelerator(library)
        left = [1.0, -2.0, 3.5, 4.0, 0.25, 9.0, -7.0]
        right = [2.0, 5.0, -1.5, 2.0, 8.0, -3.0, 6.0]
        dot = accelerator.dot_f32(left, right)
        l2 = accelerator.l2_sq_f32(left, right)
        expected_dot = sum(a * b for a, b in zip(left, right))
        expected_l2 = sum((a - b) ** 2 for a, b in zip(left, right))
        if not math.isclose(dot, expected_dot, rel_tol=1e-5, abs_tol=1e-5):
            raise SystemExit(f"dot self-test failed: {dot} != {expected_dot}")
        if not math.isclose(l2, expected_l2, rel_tol=1e-5, abs_tol=1e-5):
            raise SystemExit(f"L2 self-test failed: {l2} != {expected_l2}")
        payload["self_test"] = "passed"

    if args.json_output:
        print(json.dumps(payload, sort_keys=True))
    else:
        for key, value in payload.items():
            print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
