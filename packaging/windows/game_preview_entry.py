"""Dedicated zero-network, model-free native 2D game launcher.

PyInstaller builds SkeletonGame.exe directly from this entrypoint.
The game is fully embedded in Python stdlib/Tk: no API key, model weights,
web renderer or proprietary game/console assets.
"""
from __future__ import annotations

from skeleton.app.offline_game_preview import run_game_preview


def main() -> int:
    return run_game_preview()


if __name__ == "__main__":
    raise SystemExit(main())
