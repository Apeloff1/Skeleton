#!/usr/bin/env python3
"""Fail closed on broken navigation targets exposed by the consolidated product UI.

Only validates literal navigation actions; governed operations remain separate.
No packages, web requests, app boot, or model inference are needed.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = Path("frontend/src/product/productCatalog.ts")
ROUTE = re.compile(r"navigationId:\s*['\"]([^'\"]+)['\"]\s*,\s*href:\s*['\"]([^'\"]+)['\"]")
SHORTCUTS = re.compile(r"export const PRODUCT_HOME_SHORTCUT_IDS\s*=\s*\[([\s\S]*?)\]\s*as const;")
LITERAL = re.compile(r"['\"]([^'\"]+)['\"]")
IMPORTS = re.compile(
    r"(?:\bfrom\s*|\bimport\s*\(\s*|\brequire\s*\(\s*)['\"](\.[^'\"\n]+)['\"]"
)
SUFFIXES = (".tsx", ".ts", ".jsx", ".js", ".json", ".web.tsx", ".native.tsx", ".ios.tsx", ".android.tsx")
SURFACES = (
    "frontend/app/product.tsx",
    "frontend/app/capability.tsx",
    "frontend/app/jeeves-hub.tsx",
    "frontend/app/studio.tsx",
    "frontend/app/snowball.tsx",
    "frontend/app/settings/index.tsx",
    "frontend/app/settings/jeeves.tsx",
    "frontend/features/Jeeves/ChatWorkspace.tsx",
    "frontend/features/Jeeves/GovernedChatWorkspace.tsx",
    "frontend/features/Jeeves/WorkspaceController.ts",
    "frontend/state/settingsStore.ts",
    "frontend/src/product/productCatalog.ts",
)


def page_exists(root: Path, href: str) -> bool:
    if not re.fullmatch(r"/[a-zA-Z0-9/_-]+", href) or "//" in href or ".." in href:
        return False
    stem = root / "frontend" / "app" / href.lstrip("/")
    return any(stem.with_suffix(ext).is_file() for ext in (".tsx", ".ts", ".jsx", ".js")) or any(
        (stem / ("index" + ext)).is_file() for ext in (".tsx", ".ts", ".jsx", ".js")
    )


def module_exists(source: Path, target: str) -> bool:
    stem = source.parent / target
    if stem.is_file():
        return True
    return any(Path(str(stem) + ext).is_file() for ext in SUFFIXES) or any(
        (stem / ("index" + ext)).is_file() for ext in SUFFIXES
    )


def validate(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    catalog_path = root / CATALOG
    if not catalog_path.is_file():
        return ["missing canonical product catalog"]
    text = catalog_path.read_text(encoding="utf-8")
    actions = ROUTE.findall(text)
    if not actions:
        errors.append("product catalog has no literal navigation actions")
    seen: set[str] = set()
    for nav_id, href in actions:
        if nav_id in seen:
            errors.append(f"duplicate navigation identifier: {nav_id}")
        seen.add(nav_id)
        if not page_exists(root, href):
            errors.append(f"{nav_id}: missing Expo route {href}")
    shortcuts = SHORTCUTS.search(text)
    if shortcuts is None:
        errors.append("missing product home shortcut declaration")
    else:
        for nav_id in LITERAL.findall(shortcuts.group(1)):
            if nav_id not in seen:
                errors.append(f"orphaned home shortcut: {nav_id}")
    for relpath in SURFACES:
        path = root / relpath
        if not path.is_file():
            errors.append(f"missing UI surface: {relpath}")
            continue
        content = path.read_text(encoding="utf-8")
        for target in IMPORTS.findall(content):
            if not module_exists(path, target):
                errors.append(f"{relpath}: missing local import {target}")
    return errors


def main() -> int:
    errors = validate()
    if errors:
        print(f"product-surfaces: FAIL ({len(errors)} issue(s))", file=sys.stderr)
        for error in errors[:80]:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print("product-surfaces: OK (navigation routes, shortcut IDs and core UI imports)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
