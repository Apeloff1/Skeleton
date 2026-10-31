"""Read-only CLI for exhaustive original studio source continuity evidence."""
from __future__ import annotations

import argparse
import json

from skeleton.ai.game_builder.studio_ecosystem_cohort_audit import (
    audit_all_studio_sources,
)
from skeleton.ai.game_builder.studio_ecosystem_continuity import audit_catalog_continuity


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", help="Audit one registered source project")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.project:
        result = audit_catalog_continuity(args.project)
        valid = result["source_consistent"]
    else:
        result = audit_all_studio_sources()
        valid = result["source_consistent"]
    print(json.dumps(result, sort_keys=True,
                     separators=(",", ":") if args.json else None))
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
