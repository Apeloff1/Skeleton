"""Native binary bootstrap for an embedded, audited Python game archive.

This script is NOT the game and must not import the whole Skeleton repo.
A platform-local PyInstaller build bundles the exact standalone .pyz
generated from audited source files as data and a private Python runtime.

The packaging pipeline is intentionally separate from the fast game
validation suite. A binary is unsigned until a release authority signs it.
"""
from __future__ import annotations

from pathlib import Path
import runpy
import sys


def main() -> int:
    if not getattr(sys, "frozen", False):
        raise SystemExit(
            "This bootstrap must be frozen with PyInstaller. For development, "
            "use python -m skeleton.game.generation.original_world_product_cli."
        )
    asset_root = Path(getattr(sys, "_MEIPASS", ""))
    bundled = asset_root / "original-world-studio.pyz"
    if not bundled.is_file():
        raise SystemExit("Missing embedded original-world game archive")
    if bundled.is_symlink() or bundled.stat().st_size > 16 * 1024 * 1024:
        raise SystemExit("Unsafe or oversized embedded game archive")
    # run_path on the validated Python ZIP archive invokes its __main__ and
    # keeps the vendored game's imports isolated from unrelated Skeleton code.
    sys.argv[0] = str(bundled)
    runpy.run_path(str(bundled), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
