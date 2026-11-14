"""Cold verify every file in a private original-source Jeeves capsule.

The verifier never opens the GGUF, invokes Git, executes code, or writes a
project file. Use the full digest receipts from the private publish action.
"""
from __future__ import annotations

import sys


def main(argv=None) -> int:
    from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_capsule_verifier_cli import (
        main as verify,
    )
    return verify(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
