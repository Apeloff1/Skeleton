"""Launch the existing installed local GGUF + SQLite source-work CLI.

All private model roots, project sources, tenant identities and goals enter
only through one strict bounded JSON stdin request, never as shell arguments.

Review first:
    python scripts/jeeves_native_code.py < private-task.json

Execute exactly approved review with explicit native consent:
    python scripts/jeeves_native_code.py --approve-native-generation < private-approved-task.json

Source output is private. Add --emit-private-proposal only to explicitly
disclose it to the caller's stdout, preferably captured in private storage.
"""
from __future__ import annotations

import sys


def main(argv=None) -> int:
    from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_native_code_cli import (
        main as native_main,
    )
    return native_main(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
