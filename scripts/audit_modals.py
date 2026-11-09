#!/usr/bin/env python3
"""
audit_modals.py — Detect unused legacy Modal components.

Why this matters:
  As the modal→native-route migration progresses, the old
  /features/<Name>/<Name>Modal.tsx files stick around as dead code.
  This script lists which ones are still imported anywhere in /app
  vs. which are pure orphans that can be safely deleted.

What it does:
  1. Walks /app/frontend/features and /app/frontend/components
     finding every *Modal*.tsx file.
  2. For each, greps the rest of /app/frontend for `import { XModal }`
     or `<XModal` usages outside the file itself.
  3. Reports orphans (0 usages) and lightly-used (1 usage = only the
     native route wrapper).

Usage:
  python3 /app/scripts/audit_modals.py
  python3 /app/scripts/audit_modals.py --json
  python3 /app/scripts/audit_modals.py --delete-orphans  # interactive
"""
from __future__ import annotations
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO    = Path(__file__).resolve().parent.parent
FRONT   = REPO / "frontend"
FEATURES = FRONT / "features"
COMPONENTS = FRONT / "components"


def find_modal_files() -> list[Path]:
    out: list[Path] = []
    for root in (FEATURES, COMPONENTS):
        if root.exists():
            out.extend(p for p in root.rglob("*Modal*.tsx") if p.is_file())
    return out


def grep_count(needle: str, exclude: Path) -> tuple[int, list[str]]:
    """Count usages of `needle` across /app/frontend, excluding the modal file itself."""
    try:
        res = subprocess.run(
            ["grep", "-rl", "--include=*.tsx", "--include=*.ts", needle, str(FRONT)],
            capture_output=True, text=True, timeout=20,
        )
    except Exception as e:
        return 0, [f"grep failed: {e}"]
    files = [f for f in res.stdout.strip().split("\n") if f and Path(f).resolve() != exclude.resolve()]
    return len(files), files


def main() -> int:
    ap = argparse.ArgumentParser(description="Find unused Modal components")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--delete-orphans", action="store_true",
                    help="Interactively delete orphan modal files (0 usages)")
    args = ap.parse_args()

    modals = find_modal_files()
    report: list[dict] = []
    for mp in modals:
        name = mp.stem  # e.g. "BibleModal"
        import_n, import_files  = grep_count(f"import.*{name}", mp)
        jsx_n, _                = grep_count(f"<{name}[ />]", mp)
        usages = max(import_n, jsx_n)
        report.append({
            "file":         str(mp.relative_to(REPO)),
            "name":         name,
            "usages":       usages,
            "imports":      import_n,
            "jsx_mounts":   jsx_n,
            "import_files": [str(Path(f).relative_to(REPO)) for f in import_files[:5]],
        })

    report.sort(key=lambda r: (r["usages"], r["name"]))

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        orphans = [r for r in report if r["usages"] == 0]
        light   = [r for r in report if r["usages"] == 1]
        heavy   = [r for r in report if r["usages"] > 1]
        print(f"🔍 Scanned {len(modals)} Modal components\n")
        print(f"❌ {len(orphans):>3} ORPHAN (0 usages — safe to delete)")
        for r in orphans:
            print(f"   - {r['file']}")
        print()
        print(f"🟡 {len(light):>3} ROUTE-ONLY (1 usage — only the native route wrapper)")
        for r in light:
            print(f"   - {r['file']}  imports: {', '.join(r['import_files'])}")
        print()
        print(f"✅ {len(heavy):>3} ACTIVELY USED ({sum(r['usages'] for r in heavy)} total usages)")

    if args.delete_orphans:
        orphans = [r for r in report if r["usages"] == 0]
        if not orphans:
            print("\nNo orphans to delete.")
            return 0
        print(f"\n🗑  About to delete {len(orphans)} orphan modal files.")
        ok = input("Proceed? [y/N] ").strip().lower()
        if ok != "y":
            print("Aborted.")
            return 0
        for r in orphans:
            try:
                Path(REPO / r["file"]).unlink()
                print(f"   ✓ deleted {r['file']}")
            except Exception as e:
                print(f"   ✗ {r['file']}: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
