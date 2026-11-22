"""Seal an exact, manually selected private source capsule without model access.

Invoke from the repository root, piping one strictly bounded JSON request.
This launcher does not use subprocess, Git, a hosted model or a network.
"""
from __future__ import annotations

import sys


def main(argv=None) -> int:
    from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_native_capsule_cli import (
        main as private_capsule_main,
    )
    return private_capsule_main(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
