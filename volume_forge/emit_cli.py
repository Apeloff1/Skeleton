"""Emit CLI. Census overwrites the writer estimate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from volume_forge.census import write_ledger
from volume_forge.emitter import emit_tree

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    args = parser.parse_args()
    estimate = emit_tree(args.out)
    census = write_ledger(args.out, args.ledger)
    print(json.dumps({"estimate": estimate, "census": {k: census[k] for k in ("files", "lines", "bytes")}}))

if __name__ == "__main__":
    main()
