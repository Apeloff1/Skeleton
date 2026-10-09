"""python -m ai_tree_fill status"""

from __future__ import annotations

import sys

from ai_tree_fill.conductor import export_json, probe_all


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    cmd = args[0] if args else "status"
    if cmd not in {"status", "probe", "export"}:
        print("usage: python -m ai_tree_fill status|probe|export", file=sys.stderr)
        return 2
    report = export_json(probe_all())
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
