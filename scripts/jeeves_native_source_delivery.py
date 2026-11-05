"""Review and deliver saved Jeeves GGUF source with no inference or Git.

One private strict JSON request on stdin; do not put model source or
owner-private absolute project paths on argv.
"""
from __future__ import annotations

import sys


def main(argv=None) -> int:
    from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_native_source_delivery_cli import (
        main as private_source_main,
    )
    return private_source_main(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
