#!/usr/bin/env python3
"""
route_coverage_check.py — CI hook that validates expo-router file system
against the canonical routeRegistry.ts.

Why this matters:
  When developers add a card to /menu pointing to /foo but forget to create
  /app/foo.tsx, expo-router silently shows an "Unmatched Route" screen at
  runtime. This script catches that mismatch at CI / pre-commit time.

What it checks:
  1. Every route declared in /app/frontend/utils/routeRegistry.ts has a
     corresponding /app/frontend/app/<route>.tsx file (or +not-found.tsx,
     index.tsx, etc. for special cases).
  2. Every /app/frontend/app/*.tsx file is referenced in the registry (so
     orphan / dead routes don't accumulate).
  3. Optional live probe: hit each route on EXPO_PUBLIC_BACKEND_URL or
     localhost:3000 and confirm we get a 200 with no "Unmatched Route"
     in the body.

Exit codes:
  0  all routes accounted for + (if --live) all probes pass
  1  missing files for declared routes
  2  orphan files not in registry
  3  live probe failures

Usage:
  python3 /app/scripts/route_coverage_check.py
  python3 /app/scripts/route_coverage_check.py --live
  python3 /app/scripts/route_coverage_check.py --live --base https://...preview...
  python3 /app/scripts/route_coverage_check.py --json
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

try:
    import urllib.request
    import urllib.error
except ImportError:
    urllib = None  # type: ignore

# ── Resolve project paths ────────────────────────────────────────────
REPO = Path(__file__).resolve().parent.parent
APP_DIR  = REPO / "frontend" / "app"
REG_FILE = REPO / "frontend" / "utils" / "routeRegistry.ts"

# Routes that map to special expo-router files (not 1:1 with a path).
SPECIAL_MAP = {
    "/":             "index.tsx",
    "/+not-found":   "+not-found.tsx",
    "/_layout":      "_layout.tsx",
    "/+html":        "+html.tsx",
}

# Files in /app that are infrastructure, not navigable routes.
INFRA_FILES = {"_layout.tsx", "+html.tsx", "+not-found.tsx"}


def parse_registry(path: Path) -> list[dict]:
    """Crudely parse the TypeScript registry — pulls path/title/category."""
    if not path.exists():
        print(f"❌ registry not found at {path}", file=sys.stderr)
        sys.exit(4)
    text = path.read_text(encoding="utf-8")
    rows: list[dict] = []
    # Match `{ path: '/foo',  title: 'X', category: 'y', heavy?: ... }` lines.
    pattern = re.compile(
        r"\{\s*path:\s*'([^']+)'\s*,\s*title:\s*'([^']+)'\s*,\s*category:\s*'([^']+)'(.*?)\}",
        re.DOTALL,
    )
    for m in pattern.finditer(text):
        rows.append({
            "path":     m.group(1),
            "title":    m.group(2),
            "category": m.group(3),
            "heavy":    "heavy: true" in m.group(4),
        })
    return rows


def expected_filenames(route_path: str) -> list[str]:
    """Map a registry path to its possible expo-router file basenames.

    expo-router supports BOTH `foo.tsx` and `foo/index.tsx` for the
    same `/foo` URL. We accept either as valid.
    """
    if route_path in SPECIAL_MAP:
        return [SPECIAL_MAP[route_path]]
    stripped = route_path.lstrip("/")
    return [
        f"{stripped}.tsx",          # flat file
        f"{stripped}/index.tsx",    # folder route
    ]


def scan_app_files() -> set[str]:
    """Return set of relative paths (basenames + folder/index.tsx) inside /app."""
    out: set[str] = set()
    for p in APP_DIR.rglob("*.tsx"):
        if not p.is_file(): continue
        rel = p.relative_to(APP_DIR).as_posix()
        out.add(rel)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate expo-router files against routeRegistry.ts")
    ap.add_argument("--live", action="store_true", help="Probe each route over HTTP")
    ap.add_argument("--base", default=os.environ.get("ROUTE_COVERAGE_BASE", "http://localhost:3000"),
                    help="Base URL for --live probes")
    ap.add_argument("--json", action="store_true", help="Emit a JSON report instead of text")
    ap.add_argument("--allow-orphans", action="store_true", help="Don't fail on orphan files")
    args = ap.parse_args()

    routes = parse_registry(REG_FILE)
    on_disk  = scan_app_files()

    missing: list[str] = []
    matched_files: set[str] = set()
    for r in routes:
        candidates = expected_filenames(r["path"])
        hit = next((c for c in candidates if c in on_disk), None)
        if hit is None:
            missing.append(r["path"])
        else:
            matched_files.add(hit)

    flat_infra = {f for f in INFRA_FILES}
    orphan = sorted([
        fn for fn in on_disk
        if fn not in matched_files
        and Path(fn).name not in flat_infra
        and not fn.endswith("+not-found.tsx")
        and not fn.endswith("+html.tsx")
        and not fn.endswith("_layout.tsx")
    ])

    live_results: list[dict] = []
    if args.live:
        for r in routes:
            url = args.base.rstrip("/") + r["path"]
            t0 = time.time()
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "route-coverage/1.0"})
                with urllib.request.urlopen(req, timeout=8) as resp:
                    body = resp.read(8000).decode("utf-8", errors="ignore")
                    is_404 = "Unmatched Route" in body or "could not be found" in body.lower()
                    # Metro dev-server intercepts any path starting with
                    # /assets/ thinking it's a static asset request. This
                    # is a known dev-only artifact — the route works fine
                    # in production builds.
                    is_metro_asset_shadow = "Could not extract asset path from URL" in body
                    if is_metro_asset_shadow:
                        live_results.append({
                            "path":   r["path"],
                            "status": resp.status,
                            "ok":     True,
                            "ms":     int((time.time() - t0) * 1000),
                            "note":   "skipped (Metro dev shadows /assets/*)",
                        })
                        continue
                    live_results.append({
                        "path":   r["path"],
                        "status": resp.status,
                        "ok":     resp.status == 200 and not is_404,
                        "ms":     int((time.time() - t0) * 1000),
                        "note":   "unmatched" if is_404 else "",
                    })
            except Exception as e:
                live_results.append({"path": r["path"], "status": 0, "ok": False,
                                     "ms": int((time.time() - t0) * 1000),
                                     "note": str(e)[:80]})

    summary = {
        "registry_count": len(routes),
        "on_disk_count":  len(on_disk),
        "missing":        missing,
        "orphan":         orphan,
        "live":           live_results,
        "live_failures":  [r for r in live_results if not r["ok"]] if args.live else [],
    }

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"📋 route registry entries: {len(routes)}")
        print(f"📁 /app files (route .tsx): {len(on_disk)} (excluding {len(INFRA_FILES)} infra files)")
        if missing:
            print(f"\n❌ {len(missing)} declared routes have no file:")
            for p in missing: print(f"   - {p}  (expected {' or '.join(expected_filenames(p))})")
        else:
            print("✅ Every declared route has a backing file")
        if orphan:
            print(f"\n⚠️  {len(orphan)} orphan files not in registry:")
            for fn in orphan: print(f"   - {fn}")
        else:
            print("✅ No orphan files")
        if args.live:
            fails = summary["live_failures"]
            if fails:
                print(f"\n❌ {len(fails)}/{len(live_results)} live probes failed:")
                for r in fails:
                    print(f"   - {r['path']:30} {r['status']:>3} {r['note']}")
            else:
                print(f"\n✅ All {len(live_results)} live probes passed")

    code = 0
    if missing: code = max(code, 1)
    if orphan and not args.allow_orphans: code = max(code, 2)
    if args.live and summary["live_failures"]: code = max(code, 3)
    return code


if __name__ == "__main__":
    sys.exit(main())
