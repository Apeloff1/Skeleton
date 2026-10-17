"""Operator-only, zero-shell native cartridge build qualification CLI."""
from __future__ import annotations

import argparse
import json

from .studio_build_qualification import (
    NativeBuildQualificationError, adapter_catalog, qualify_native_build,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", action="store_true")
    parser.add_argument("--project")
    parser.add_argument("--target")
    parser.add_argument("--output")
    parser.add_argument("--output-symbols", help="new .sym output next to RGBDS ROM (GB/GBC only)")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=45)
    parser.add_argument("--authorize-local-build", action="store_true")
    args = parser.parse_args(argv)
    if args.catalog:
        print(json.dumps(adapter_catalog(), sort_keys=True))
        return 0
    if not args.project or not args.target:
        parser.error("--project and --target are required unless --catalog is selected")
    try:
        result = qualify_native_build(
            args.project, args.target,
            authorized=args.authorize_local_build,
            execute=args.execute,
            output=args.output, output_symbols=args.output_symbols,
            timeout_seconds=args.timeout_seconds,
        )
    except (NativeBuildQualificationError, PermissionError, OSError) as exc:
        print(json.dumps({"qualified": False, "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result.as_receipt(), sort_keys=True))
    return 0 if (result.binary_built if args.execute else
                 result.toolchain_available) else 1


if __name__ == "__main__":
    raise SystemExit(main())
