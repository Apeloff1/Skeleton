"""Source-only wrapper for the owner-private Jeeves native proposal CLI.

Read one strict JSON request through stdin. Model/source paths, generated
code, secrets and task descriptions must not be placed on argv.
"""
from __future__ import annotations

import sys


def main(argv=None) -> int:
    from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_native_proposal_cli import (
        main as native_escrow_main,
    )
    return native_escrow_main(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
