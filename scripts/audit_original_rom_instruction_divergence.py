"""Explicit operator entrypoint for real original-ROM CPU divergence evidence.

No external ROM download or automatic CI trigger; creates new private report.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from skeleton.jeeves.game_rom_instruction_divergence import (
    InstructionDivergenceConfig,
    compare_original_rom_instruction_branches,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-file", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--instruction-count", type=int, default=2048)
    parser.add_argument("--sample-stride", type=int, default=8)
    parser.add_argument("--max-cycles-per-branch", type=int, default=131072)
    parser.add_argument("--actions", nargs="+", default=["idle", "a", "right", "a_right"])
    args = parser.parse_args(argv)
    try:
        if args.evidence_file.exists() or args.evidence_file.is_symlink():
            raise ValueError("source CPU divergence receipt must use a new private file")
        if not args.evidence_file.parent.is_dir():
            raise ValueError("CPU divergence report parent directory must exist")
        config = InstructionDivergenceConfig(
            seed=args.seed,
            instruction_count=args.instruction_count,
            sample_stride=args.sample_stride,
            max_cycles_per_branch=args.max_cycles_per_branch,
            action_subset=tuple(args.actions),
        )
        result = compare_original_rom_instruction_branches(config)
        payload = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
        if len(payload) > 8 * 1024 * 1024:
            raise ValueError("source CPU divergence report exceeds bounded capacity")
        fd = os.open(
            args.evidence_file,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        with os.fdopen(fd, "wb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        print(json.dumps({
            "status": "original_source_cpu_instruction_replays_identical",
            "actual_original_cpu_instructions": result["real_source_instruction_executions"],
            "measured_active_control_branches": len(result["paired_replay_verified_differences"]),
            "source_evidence_file": str(args.evidence_file),
            "report_digest": result["report_digest"],
            "production_jeeves_weight_updates": 0,
        }, sort_keys=True))
        return 0
    except (ValueError, TypeError, OSError, RuntimeError) as exc:
        print(json.dumps({
            "status": "source_instruction_divergence_rejected",
            "error": str(exc)[:600],
            "production_jeeves_weight_updates": 0,
        }, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
