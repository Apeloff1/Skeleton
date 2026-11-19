#!/usr/bin/env python3
"""Generate the installed-surface atlas from the Expo app directory.

Every public Expo route becomes one record. Route groups such as `(account)`
are stripped from the URL. Layouts, HTML shells and parameterised segments are
not fake static links. A route is an orphan when the product catalog does not
already name it as a navigation action.

Run with no arguments to rewrite ``frontend/src/product/surfaceAtlas.ts``.
``--check`` exits 1 when the checked-in atlas has drifted.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "frontend" / "app"
CATALOG = ROOT / "frontend" / "src" / "product" / "productCatalog.ts"
MENU = ROOT / "frontend" / "app" / "menu.tsx"
OUTPUT = ROOT / "frontend" / "src" / "product" / "surfaceAtlas.ts"

ROUTE_PAIR = re.compile(
    r"navigationId:\s*['\"]([^'\"]+)['\"]\s*,\s*href:\s*['\"]([^'\"]+)['\"]"
)
MENU_CARD = re.compile(
    r"title:\s*'((?:\\'|[^'])*)'\s*,\s*desc:\s*'((?:\\'|[^'])*)'"
    r"[\s\S]*?route:\s*'([^']+)'"
)
DOC = re.compile(r"/\*\*([\s\S]*?)\*/")

LEARN = (
    "academy", "class", "learning", "learn", "quiz", "flashcard", "education",
    "language", "math", "physics", "reading", "curriculum", "study", "masterclass",
    "knowledge", "rosetta", "bible", "immersive", "daily-challenge", "challenge",
    "discourse", "notes", "pomodoro", "reference", "lang-recommend", "my-classes",
    "jeeves", "crawler", "mirror", "ai-chat", "ai-models", "agent",
)
PLAY = (
    "playable", "playground", "game-factory", "game-kb", "tournament",
    "leaderboard", "achievement", "trophy", "champion", "gallery",
    "worlds-gallery", "multiplayer", "music", "scorecard", "top", "zaibatsu",
    "collections",
)
OPERATE = (
    "ops", "health", "telemetry", "scheduler", "settings", "dashboard",
    "command-center", "mission-control", "audit", "boot-log", "safe-mode",
    "feature-flag", "marketplace", "profile", "sign-in", "account", "thermal",
    "perf", "liveops", "control-plane", "swarm", "organism", "vault", "storage",
    "offline", "certificate", "anti-cheat", "hub", "menu", "surfaces", "welcome",
    "search", "operation", "app", "capability", "product",
)


def public_href(relative: Path) -> str | None:
    parts: list[str] = []
    for part in relative.parts:
        if part.startswith("(") and part.endswith(")"):
            continue
        if part.startswith("_") or part.startswith("+"):
            return None
        parts.append(part)
    if not parts:
        return None
    last = parts[-1]
    if last.startswith("index."):
        parts = parts[:-1]
    else:
        stem = Path(last).stem
        if "[" in stem or stem.startswith("_") or stem.startswith("+"):
            return None
        parts[-1] = stem
    if any("[" in part or part.startswith("_") or part.startswith("+") for part in parts):
        return None
    if not parts:
        return "/"
    return "/" + "/".join(parts)


def collect_routes(root: Path = ROOT) -> list[str]:
    app = root / "frontend" / "app"
    found: list[str] = []
    if not app.is_dir():
        return found
    for path in sorted(app.rglob("*")):
        if not path.is_file() or path.suffix not in {".tsx", ".ts", ".jsx", ".js"}:
            continue
        href = public_href(path.relative_to(app))
        if href is None:
            continue
        found.append(href)
    if len(found) != len(set(found)):
        dupes = sorted({item for item in found if found.count(item) > 1})
        raise SystemExit(f"duplicate public routes: {', '.join(dupes)}")
    return found


def catalog_hrefs(root: Path = ROOT) -> set[str]:
    catalog = root / "frontend" / "src" / "product" / "productCatalog.ts"
    if not catalog.is_file():
        return set()
    text = catalog.read_text(encoding="utf-8")
    return {href.split("?", 1)[0] for _nav, href in ROUTE_PAIR.findall(text)}


def menu_copy(root: Path = ROOT) -> dict[str, tuple[str, str]]:
    menu = root / "frontend" / "app" / "menu.tsx"
    if not menu.is_file():
        return {}
    text = menu.read_text(encoding="utf-8")
    copy: dict[str, tuple[str, str]] = {}
    for title, desc, route in MENU_CARD.findall(text):
        copy[route] = (title.replace("\\'", "'"), desc.replace("\\'", "'"))
    return copy


def _segment_hit(segment: str, token: str) -> bool:
    if segment == token or segment.startswith(token + "-"):
        return True
    return len(token) >= 5 and segment.startswith(token)


def pillar_for(href: str) -> str:
    segments = [part.lower() for part in href.strip("/").split("/") if part]
    groups = (("learn", LEARN), ("play", PLAY), ("operate", OPERATE))
    for name, tokens in groups:
        for segment in segments:
            if any(_segment_hit(segment, token.strip("/").lower()) for token in tokens):
                return name
    return "create"


_ACRONYMS = {"ai": "AI", "api": "API", "cs": "CS", "npc": "NPC", "qa": "QA", "ui": "UI", "pc": "PC"}


def title_from_href(href: str) -> str:
    slug = href.strip("/").split("/")[-1] or "home"
    slug = re.sub(r"([a-z])([A-Z])", r"\1 \2", slug)
    slug = slug.replace("-", " ").replace("_", " ")
    words = []
    for part in slug.split():
        words.append(_ACRONYMS.get(part.lower(), part.capitalize()))
    return " ".join(words)


def file_for_href(root: Path, href: str) -> Path | None:
    app = root / "frontend" / "app"
    for path in app.rglob("*"):
        if not path.is_file() or path.suffix not in {".tsx", ".ts", ".jsx", ".js"}:
            continue
        if public_href(path.relative_to(app)) == href:
            return path
    return None


def file_blurb(root: Path, href: str) -> str:
    path = file_for_href(root, href)
    if path is None:
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")[:1600]
    match = DOC.search(text)
    if not match:
        return ""
    line = " ".join(match.group(1).replace("*", " ").split())
    if 24 <= len(line) <= 180 and "http" not in line.lower():
        return line.rstrip(".") + "."
    return ""


def navigation_id(href: str) -> str:
    body = href.strip("/").lower() or "home"
    body = re.sub(r"[^a-z0-9/]+", "-", body).strip("-")
    body = body.replace("/", ".")
    return "surface." + body


def build_entries(root: Path = ROOT) -> list[dict[str, object]]:
    linked = catalog_hrefs(root)
    known = menu_copy(root)
    entries: list[dict[str, object]] = []
    for href in collect_routes(root):
        menu = known.get(href)
        title = menu[0] if menu else title_from_href(href)
        description = menu[1] if menu else file_blurb(root, href)
        if not description:
            description = f"Open {title}, installed at {href}."
        entries.append(
            {
                "id": navigation_id(href),
                "href": href,
                "title": title,
                "description": description,
                "pillar": pillar_for(href),
                "orphan": href not in linked,
            }
        )
    entries.sort(key=lambda item: (str(item["pillar"]), str(item["title"]).lower(), str(item["href"])))
    ids = [str(item["id"]) for item in entries]
    if len(ids) != len(set(ids)):
        raise SystemExit("surface navigation ids are not unique")
    return entries


def js_string(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def render(entries: list[dict[str, object]]) -> str:
    lines = [
        "/**",
        " * Installed surface atlas.",
        " *",
        " * Generated by scripts/generate_surface_atlas.py from frontend/app.",
        " * Do not edit by hand. Parameterised routes that need an id, such as",
        " * /gate/:stage, stay out of this list and are reached from their owner.",
        " */",
        "export type SurfacePillar = 'create' | 'play' | 'learn' | 'operate';",
        "",
        "export type InstalledSurface = {",
        "  id: string;",
        "  href: string;",
        "  title: string;",
        "  description: string;",
        "  pillar: SurfacePillar;",
        "  /** True when the product catalog has no navigation action for this href. */",
        "  orphan: boolean;",
        "};",
        "",
        "export const PARAMETERISED_SURFACES = ['/gate/:stage'] as const;",
        "",
        "export const INSTALLED_SURFACES: readonly InstalledSurface[] = [",
    ]
    for item in entries:
        lines.append("  {")
        lines.append(f"    id: {js_string(str(item['id']))},")
        lines.append(f"    href: {js_string(str(item['href']))},")
        lines.append(f"    title: {js_string(str(item['title']))},")
        lines.append(f"    description: {js_string(str(item['description']))},")
        lines.append(f"    pillar: '{item['pillar']}',")
        lines.append(f"    orphan: {'true' if item['orphan'] else 'false'},")
        lines.append("  },")
    lines.extend(
        [
            "];",
            "",
            "export const ORPHAN_SURFACES: readonly InstalledSurface[] = INSTALLED_SURFACES.filter(",
            "  (surface) => surface.orphan,",
            ");",
            "",
            "export function surfacesFor(pillar: SurfacePillar): readonly InstalledSurface[] {",
            "  return INSTALLED_SURFACES.filter((surface) => surface.pillar === pillar);",
            "}",
            "",
        ]
    )
    return "\n".join(lines)


def validate_atlas(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    output = root / "frontend" / "src" / "product" / "surfaceAtlas.ts"
    if not output.is_file():
        return ["missing frontend/src/product/surfaceAtlas.ts"]
    expected = render(build_entries(root))
    actual = output.read_text(encoding="utf-8")
    if actual != expected:
        errors.append("surface atlas is stale; run python scripts/generate_surface_atlas.py")
    routes = collect_routes(root)
    text = actual
    for href in routes:
        needle = f"href: '{href}'"
        if needle not in text:
            errors.append(f"atlas missing {href}")
    gate = root / "frontend" / "app" / "gate" / "[stage].tsx"
    if not gate.is_file():
        errors.append("parameterised /gate/:stage owner is missing")
    elif "PARAMETERISED_SURFACES" not in text or "'/gate/:stage'" not in text:
        errors.append("parameterised /gate/:stage is not recorded")
    surfaces = root / "frontend" / "app" / "surfaces.tsx"
    if not surfaces.is_file():
        errors.append("missing Expo route /surfaces")
    product = root / "frontend" / "app" / "product.tsx"
    if product.is_file() and "INSTALLED_SURFACES" not in product.read_text(encoding="utf-8"):
        errors.append("product home does not search the installed surface atlas")
    return errors


def main() -> int:
    check = "--check" in sys.argv
    entries = build_entries()
    rendered = render(entries)
    if check:
        errors = validate_atlas()
        if errors:
            print(f"surface-atlas: FAIL ({len(errors)})", file=sys.stderr)
            for error in errors:
                print(f"  - {error}", file=sys.stderr)
            return 1
        orphans = sum(1 for item in entries if item["orphan"])
        print(f"surface-atlas: OK ({len(entries)} routes, {orphans} outside the pillar catalog)")
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(rendered, encoding="utf-8")
    orphans = sum(1 for item in entries if item["orphan"])
    print(f"wrote {OUTPUT.relative_to(ROOT)} ({len(entries)} routes, {orphans} orphans)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
