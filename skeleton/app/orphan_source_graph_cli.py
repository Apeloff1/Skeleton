"""Read-only source graph and ordered orphan-recovery candidate campaign."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from skeleton.app.orphan_source_graph import GraphBudget, GraphError, analyze
from skeleton.app.orphan_cli_audit import ScanBudget, _ReadBudget


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--entry", action="append", default=[])
    parser.add_argument("--max-entries", type=int, default=250_000)
    parser.add_argument("--max-modules", type=int, default=65_536)
    parser.add_argument("--max-file-bytes", type=int, default=2 * 1024 * 1024)
    parser.add_argument("--max-total-bytes", type=int, default=256 * 1024 * 1024)
    parser.add_argument("--max-edges", type=int, default=1_000_000)
    parser.add_argument("--max-components", type=int, default=256)
    parser.add_argument("--machine-ownership", action="store_true",
                        help="Observe the fixed repository machine/ai_file_tree.json declaration")
    parser.add_argument("--component-offset", type=int, default=0)
    parser.add_argument("--expected-plan-digest")
    parser.add_argument("--expected-inventory-digest")
    args = parser.parse_args(argv)
    try:
        budget = GraphBudget(args.max_entries, args.max_modules,
                             args.max_file_bytes, args.max_total_bytes,
                             args.max_edges, args.max_components)
        ownership = None
        if args.machine_ownership:
            root = args.root.resolve(strict=True)
            machine = root / "machine"
            if machine.is_symlink() or not machine.is_dir():
                raise GraphError("machine ownership directory unavailable")
            reader = _ReadBudget(ScanBudget(max_file_bytes=8 * 1024 * 1024,
                                            max_total_bytes=8 * 1024 * 1024))
            ownership = reader.read(machine / "ai_file_tree.json")
        result = analyze(args.root, extra_roots=args.entry, budget=budget,
                         ownership_raw=ownership, component_offset=args.component_offset,
                         expected_plan_digest=args.expected_plan_digest,
                         expected_inventory_digest=args.expected_inventory_digest)
    except (GraphError, ValueError, OSError, KeyError, SyntaxError) as exc:
        print(json.dumps({"error": type(exc).__name__,
                          "source_inventory_complete": False}), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["source_inventory_complete"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
