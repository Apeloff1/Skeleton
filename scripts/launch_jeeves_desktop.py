"""Start the local Jeeves desktop without a provider or network service.

From the repository root:
    python scripts/launch_jeeves_desktop.py

No model paths, prompts, credentials or identities are accepted on argv.
The user selects the independently installed GGUF through the local window.
"""
from __future__ import annotations

import sys


def main(argv=None) -> int:
    if argv:
        raise SystemExit("Jeeves desktop launcher accepts no private command arguments")
    from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_app import (
        main as desktop_main,
    )
    return desktop_main([])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
