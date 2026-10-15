#!/usr/bin/env python3
"""Verify a completed or paused native playthrough's local checkpoint ledger.

This checks cryptographic integrity and sequencing, not ROM rights, hardware
accuracy, runtime attestation or an actual game-clear result.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main(argv: list[str] | None = None) -> int:
    from skeleton.jeeves.game_emulator_playthrough import audit_native_playthrough_directory
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = audit_native_playthrough_directory(args.checkpoint_dir)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (ValueError, OSError, RuntimeError) as exc:
        print(json.dumps({
            "status": "native_playthrough_audit_rejected",
            "reason": str(exc)[:512], "game_completion_verified": False,
        }), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
