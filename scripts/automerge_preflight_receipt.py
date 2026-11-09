"""Publish bounded fail-closed auto-merge preflight evidence before any mutation."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Sequence


STAGES = (
    "protection-unverified",
    "protection-disabled",
    "reconciliation-incomplete",
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", choices=STAGES, required=True)
    args = parser.parse_args(argv)

    # These variables are trusted workflow configuration, not PR-controlled data.
    target = Path(os.environ["AUTOMERGE_REPORT_PATH"])
    report = {
        "schema": "skeleton.automerge.preflight.v1",
        "stage": args.state,
        "decision": "not_certified",
        "repository": os.environ["GITHUB_REPOSITORY"],
        "default_branch": os.environ["AUTOMERGE_DEFAULT_BRANCH"],
        "run_id": os.environ["GITHUB_RUN_ID"],
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".pending")
    temporary.write_text(
        json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
